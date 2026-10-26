#!/usr/bin/env python3
"""Generate command-latch stimuli only; no attached hardware access."""
import argparse
from pathlib import Path
from hp13210_flag_diagnostics import abs_image

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 0o76000


def program(loop=False):
    # LDA/JMP use current-page addressing (page 076000).
    # The held test's JMP makes accidental CONTINUE repeat, never execute data.
    literal = ORIGIN+5 if loop else ORIGIN+6
    rows = [(0o103100, 'CLF 0', 'Disable CPU interrupts'),
            (0o106715, 'CLC 15', 'Clear command-channel control once'),
            (0o062000 | (literal & 0o1777), f'LDA {literal:06o}', 'Load command pattern'),
            (0o102615, 'OTA 15', 'Write command latch; no STC')]
    if not loop:
        rows.append((0o102000, 'HLT 00', 'Checkpoint only; inspect FPGA command register'))
    rows += [(0o026002, f'JMP {ORIGIN+2:06o}', 'Repeat until operator stops'),
             (0o030000, 'OCT 030000', 'Seek opcode, drive 0; no seek is started')]
    return rows


def check(rows, loop):
    """Check control flow and output values, not electrical timing/readback."""
    words = [r[0] for r in rows]
    pc = ORIGIN
    a = 0
    output = []
    for _ in range(100):
        w = words[pc-ORIGIN]; pc += 1
        if w in (0o103100, 0o106715):
            continue
        if w & 0o176000 == 0o062000:
            a = words[(ORIGIN | (w & 0o1777))-ORIGIN]
        elif w == 0o102615:
            output.append(a)
        elif w == 0o026002:
            pc = ORIGIN+2
        elif w == 0o102000:
            assert not loop and pc == ORIGIN+5 and output == [0o030000]
            return
        else:
            raise AssertionError(f'Unexpected instruction {w:06o}')
    assert loop and len(output) > 20 and set(output) == {0o030000}


def generate(folder):
    folder.mkdir(parents=True, exist_ok=True)
    for loop in (False, True):
        name = 'command-latch-loop' if loop else 'command-latch-hold'
        rows = program(loop)
        check(rows, loop)
        listing = ['Address Word   Instruction       Meaning (all numbers octal)']
        asm = ['* Generated command-latch stimulus; all numbers octal.', f'      ORG {ORIGIN:o}B']
        for i, (word, instruction, comment) in enumerate(rows):
            listing.append(f'{ORIGIN+i:06o}  {word:06o} {instruction:16s} {comment}')
            asm.append(f'      {instruction:16s} {comment}')
        asm.append('      END')
        (folder/(name+'.lst')).write_text('\n'.join(listing)+'\n')
        (folder/(name+'.asm')).write_text('\n'.join(asm)+'\n')
        (folder/(name+'.abs')).write_bytes(abs_image([r[0] for r in rows], origin=ORIGIN))
    print('Generated command-latch hold and loop; instruction-flow checks passed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'diagnostics/hp13210/programs')
    generate(parser.parse_args().output)
