#!/usr/bin/env python3
"""Run the unpatched DSN151302 memory image on independent SIMH HP2100.

The default executable is the HP maintainer's supported Release 32. Start at
P2000 using the existing configured checkpoint, bypassing tape loading only.
Uses four disposable disks. Checks steps34/35/46 and section1, not the full diagnostic.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simh', type=Path, default=ROOT/'build/reference/hp2100-release32/hp2100')
    parser.add_argument('--memory', type=Path,
                        default=ROOT/'build/hp2116-seek-validation/recovery/section1.hex')
    parser.add_argument('--out', type=Path, default=ROOT/'build/check-step34/simh-confirmation')
    args = parser.parse_args()
    executable, checkpoint, out = args.simh.resolve(), args.memory.resolve(), args.out.resolve()
    memory = [int(word, 16) for word in checkpoint.read_text().split()]
    if len(memory) != 32768 or memory[0o126] != 0o151302:
        parser.error('Expected the configured 32KW DSN151302 checkpoint')
    if memory[0o4031] != 0o060334 or memory[0o1543] != 0o125513:
        parser.error('Unexpected revision: breakpoint addresses must be rechecked')
    out.mkdir(parents=True, exist_ok=True)
    before = {'simh': digest(executable), 'memory': digest(checkpoint)}
    results = []
    for case in ('step34', 'step35', 'step46', 'section1'):
        folder = out/case
        folder.mkdir(exist_ok=True)
        commands = ['set cpu 2116', 'set cpu 32K', 'set cpu EAU',
                    'set cpu loaderenable', 'set tty sc=16', 'set tty 7b',
                    'set tbg sc=13', 'set dpd enabled', 'set dpc enabled',
                    'set dpc 13210A']
        commands += [f'attach -n dpc{i} {folder}/scratch{i}.disc' for i in range(4)]
        commands += ['reset']
        commands += [f'deposit {address:o} {word:o}' for address, word in enumerate(memory)
                     if address >= 2]
        commands += ['deposit A 0', 'deposit B 0',
                     'deposit S '+('1000' if case == 'section1' else '0')]
        if case != 'section1':
            start, end = {'step34': ('4013','4031'),
                          'step35': ('4031','4047'),
                          'step46': ('4240','4302')}[case]
            commands += [f'break {start}', 'go 2000', 'examine P,A,B,S',
                         'examine dma1 cw1,cw2,cw3,flg,ctl',
                         f'set debug {folder}/debug.log', 'set cpu debug=instr;reg',
                         'set dpd debug=iobus', 'set dpc debug=iobus',
                         f'nobreak {start}', f'break {end}', 'continue']
        else:
            commands += ['go 2000']
        commands += ['examine P,A,B,S', 'examine 156', 'examine 240',
                     'examine dma1 cw1,cw2,cw3,flg,ctl', 'show dpc', 'exit']
        command_file = folder/'run.ini'
        command_file.write_text('\n'.join(commands)+'\n')
        with (folder/'console.log').open('w') as log:
            result = subprocess.run([str(executable), str(command_file)], cwd=ROOT,
                                    stdin=subprocess.DEVNULL, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=60)
        console = (folder/'console.log').read_text()
        passed = result.returncode == 0 and '156:\t000000' in console
        entry = {'case': case, 'returncode': result.returncode}
        if case == 'step34':
            trace = (folder/'debug.log').read_text()
            check = trace.split('>>DPC iobus: Received data 060000 with signals IOO', 1)[1]
            check = check.split('>>DPC iobus: Received data 000000 with signals IOO', 1)[0]
            transfers = sum(line.startswith('>>DPD iobus: Received') and 'IOI' in line
                            for line in check.splitlines())
            passed &= ('P:\t04031' in console and transfers == 128
                       and '01543  125513' in trace and 'CW3:\t000000' in console)
            entry['check_data_inputs'] = transfers
        elif case == 'step35':
            trace = (folder/'debug.log').read_text()
            read = trace.split('>>DPC iobus: Received data 020000 with signals IOO', 1)[1]
            read = read.split('>>DPC iobus: Received data 000000 with signals IOO', 1)[0]
            transfers = sum(line.startswith('>>DPD iobus: Received') and 'IOI' in line
                            for line in read.splitlines())
            passed &= ('P:\t04047' in console and '240:\t020001' in console
                       and transfers == 30 and 'IOI | CLC | EDT' in read)
            entry.update({'read_data_inputs': transfers, 'status_octal': '020001',
                          'final_dma_clc_seen': 'IOI | CLC | EDT' in read})
        elif case == 'step46':
            trace = (folder/'debug.log').read_text()
            writes = trace.split('>>DPC iobus: Received data 010000 with signals IOO')[1:]
            # Each first word is preloaded before the command. The remaining
            # 1023 arrive after it; six thirds fill the two cylinder tracks.
            words = [sum(line.startswith('>>DPD iobus: Received') and 'IOO' in line
                         for line in part.split('>>DPC iobus: Received data 000000 with signals IOO')[0].splitlines())
                     for part in writes]
            passed &= ('P:\t04302' in console and '240:\t000000' in console
                       and words == [1023]*6)
            entry.update({'write_words_after_command': words,
                          'preloaded_words_per_command': 1, 'status_octal':'000000'})
        else:
            passed &= '102011 (HLT 11)' in console and '102001 (HLT 1)' not in console
        entry.update({'pass': bool(passed), 'console_sha256': digest(folder/'console.log'),
                      'commands_sha256': digest(command_file)})
        results.append(entry)
        print(f'{case}: {"PASS" if passed else "FAIL"}')
    unchanged = before == {'simh': digest(executable), 'memory': digest(checkpoint)}
    receipt = {'sources': before, 'sources_unchanged': unchanged,
               'diagnostic_patched': False, 'hardware_programmed': False,
               'cpu': '2116, 32KW, EAU', 'controller': '13210A, SC22/23',
               'start': 'P2000; configured memory checkpoint', 'results': results,
               'full_diagnostic_pass': False}
    (out/'result.json').write_text(json.dumps(receipt, indent=2)+'\n')
    if not unchanged or not all(item['pass'] for item in results):
        raise SystemExit('SIMH comparison failed; inspect evidence')


if __name__ == '__main__':
    main()
