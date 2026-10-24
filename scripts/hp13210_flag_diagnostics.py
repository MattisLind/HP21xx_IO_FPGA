#!/usr/bin/env python3
"""Generate small HP 2100 flag-only programs; never access attached hardware."""
from pathlib import Path
import argparse
import json

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 0o2000
DATA_SC = 0o14
COMMAND_SC = 0o15
OPCODES = {'NOP': 0, 'HLT': 0o102000, 'STF': 0o102100,
           'CLF': 0o103100, 'SFC': 0o102200, 'SFS': 0o102300,
           'CLC': 0o107700}


class Program:
    def __init__(self):
        self.rows = []
        self.labels = {}
        self.errors = {}

    def label(self, name):
        self.labels[name] = ORIGIN + len(self.rows)

    def emit(self, op, arg=0, comment=''):
        self.rows.append((op, arg, comment))

    def fail(self, number, description):
        self.errors[f'{number:02o}'] = description
        self.emit('HLT', number, description)

    def words(self):
        result = []
        for index, (op, arg, _) in enumerate(self.rows):
            if op == 'JMP':
                address = self.labels[arg]
                pc = ORIGIN + index
                if address < 1024:
                    word = 0o024000 | address
                elif address // 1024 == pc // 1024:
                    word = 0o026000 | (address & 1023)
                else:
                    raise ValueError('Jump outside the current page')
            else:
                word = OPCODES[op] | arg
            result.append(word)
        return result

    def flag(self, op, channel, delay=0):
        self.emit(op, channel)
        for _ in range(delay):
            self.emit('NOP', comment='Extra settling time after flag operation')

    def expect(self, op, channel, should_skip, number, description):
        self.emit(op, channel)
        if should_skip:
            self.fail(number, description)
        else:
            label = f'T{number:02o}'
            self.emit('JMP', label)
            self.fail(number, description)
            self.label(label)

    def basic(self, channel, base, delay=0):
        self.flag('CLF', channel, delay)
        self.expect('SFC', channel, True, base+1, f'SFC {channel:02o} did not skip after CLF')
        self.expect('SFS', channel, False, base+2, f'SFS {channel:02o} skipped after CLF')
        self.flag('STF', channel, delay)
        self.expect('SFS', channel, True, base+3, f'SFS {channel:02o} did not skip after STF')
        self.expect('SFC', channel, False, base+4, f'SFC {channel:02o} skipped after STF')


def programs():
    result = {}
    for channels, name, delay in [((DATA_SC,), f'flags-{DATA_SC:02o}', 0),
                                   ((COMMAND_SC,), f'flags-{COMMAND_SC:02o}', 0),
                                   ((DATA_SC, COMMAND_SC), 'flags-both', 0),
                                   ((DATA_SC, COMMAND_SC), 'flags-both-delay', 4)]:
        p = Program()
        p.emit('CLF', 0, 'Disable CPU interrupts; not restored on exit')
        for channel in channels:
            p.emit('CLC', channel, 'Disable this interface control/interrupt request')
        for channel in channels:
            p.basic(channel, 0 if channel == DATA_SC else 0o10, delay)
        if len(channels) == 2:
            for op, ch in [('CLF', DATA_SC), ('CLF', COMMAND_SC), ('STF', DATA_SC)]:
                p.flag(op, ch, delay)
            p.expect('SFS', COMMAND_SC, False, 0o21, f'STF {DATA_SC:02o} also set flag {COMMAND_SC:02o}')
            p.expect('SFS', DATA_SC, True, 0o22, f'Flag {DATA_SC:02o} missing during isolation check')
            p.flag('CLF', DATA_SC, delay)
            p.flag('STF', COMMAND_SC, delay)
            p.expect('SFS', DATA_SC, False, 0o23, f'STF {COMMAND_SC:02o} also set flag {DATA_SC:02o}')
            p.expect('SFS', COMMAND_SC, True, 0o24, f'Flag {COMMAND_SC:02o} missing during isolation check')
        for channel in channels:
            p.flag('CLF', channel)
        p.emit('HLT', 0, 'PASS: all checks complete; do not continue beyond this halt')
        result[name] = p
    for channel in [DATA_SC, COMMAND_SC]:
        p = Program()
        p.emit('CLF', 0, 'Disable interrupts')
        p.emit('CLC', channel)
        p.label('RPT')
        p.emit('CLF', channel)
        p.emit('SFC', channel)
        p.fail(1, 'Missing skip with flag clear')
        p.emit('JMP', 'RPT', 'Runs until operator HALT or failure')
        result[f'scope-clear-{channel:02o}'] = p
    return result


def run_model(words, fault=None, limit=1000):
    """Instruction-flow check only; does not model HP electrical/ENF timing."""
    flags = {DATA_SC: False, COMMAND_SC: False}
    pc = ORIGIN
    for _ in range(limit):
        word = words[pc-ORIGIN]
        current = pc
        pc += 1
        if word == 0:
            continue
        if word & 0o174000 == 0o024000:
            pc = (word & 1023) | ((current & ~1023) if word & 1024 else 0)
            continue
        channel = word & 63
        opcode = word & ~63
        if opcode == OPCODES['HLT']:
            return channel
        if opcode in (OPCODES['CLF'], OPCODES['STF']):
            if channel in flags:
                flags[channel] = opcode == OPCODES['STF']
                if fault == 'cross-coupled':
                    flags[COMMAND_SC if channel == DATA_SC else DATA_SC] = flags[channel]
        elif opcode in (OPCODES['SFC'], OPCODES['SFS']):
            flag = flags[channel]
            if fault == 'flag-stuck-set': flag = True
            if fault == 'flag-stuck-clear': flag = False
            skip = flag if opcode == OPCODES['SFS'] else not flag
            if fault == 'no-skf': skip = False
            if fault == 'skf-stuck-asserted': skip = True
            if skip: pc += 1
        elif opcode != OPCODES['CLC']:
            raise ValueError(f'Unsupported instruction {word:06o}')
    return None


def abs_image(words):
    image = bytearray(32)  # Blank leader, followed by HP count/address/data/checksum.
    for index in range(0, len(words), 64):
        block = words[index:index+64]
        address = ORIGIN + index
        values = [len(block) << 8, address] + block + [sum(block, address) & 65535]
        for value in values:
            image.extend(value.to_bytes(2, 'big'))
    image.extend(bytes(128))
    return image


def generate(folder):
    folder.mkdir(parents=True, exist_ok=True)
    summary = {}
    for name, p in programs().items():
        words = p.words()
        looping = name.startswith('scope-')
        assert run_model(words) == (None if looping else 0)
        assert run_model(words, 'no-skf') == (0o11 if name == f'flags-{COMMAND_SC:02o}' else 1)
        asm = ['* Generated by scripts/hp13210_flag_diagnostics.py; all numbers octal.',
               '      ORG 2000B']
        listing = ['Address Word   Instruction       Meaning (all numbers octal)']
        labels = {address: name for name, address in p.labels.items()}
        for index, (op, arg, comment) in enumerate(p.rows):
            address = ORIGIN+index
            operand = (arg if op == 'JMP' else (f'{arg:02o}B' if op != 'NOP' else ''))
            asm.append(f'{labels.get(address, ""):5s} {op:3s} {operand!s:14s} {comment}')
            display_arg = f'{p.labels[arg]:06o}' if op == 'JMP' else f'{arg:02o}'
            listing.append(f'{address:06o}  {words[index]:06o} {op:4s} {display_arg:6s} {comment}')
        asm.append('      END')
        (folder/(name+'.asm')).write_text('\n'.join(asm)+'\n')
        (folder/(name+'.lst')).write_text('\n'.join(listing)+'\n')
        (folder/(name+'.abs')).write_bytes(abs_image(words))
        summary[name] = {'start_octal': '002000', 'words': len(words),
                         'success': 'operator stops loop' if looping else 'HLT 00',
                         'error_halts_octal': p.errors}
    (folder/'manifest.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(f'Generated {len(summary)} programs in {folder}; instruction-flow checks pass.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'diagnostics/hp13210/programs')
    generate(parser.parse_args().output)
