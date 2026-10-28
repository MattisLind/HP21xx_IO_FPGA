#!/usr/bin/env python3
"""Trace DSN151302 step 34 without modifying diagnostic memory or hardware.

Requires a compiled hp2116_transfer_timing.py experiment in --cpu-dir. Uses
its SV backend, not the STM32 C++ firmware. Records the executed instruction
path and source hashes; an observed E13 is evidence of failure, never a pass.
This traces our backend's missing CHECK DMA behavior, not a diagnostic defect;
hp13210_simh_compare.py provides the independent passing reference.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from hp2116_transfer_timing import IMAGE, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpu-dir', type=Path, default=ROOT/'build/check-step34/cpu')
    parser.add_argument('--out', type=Path, default=ROOT/'build/check-step34/instruction-trace')
    args = parser.parse_args()
    cpu = args.cpu_dir.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    checkpoint = ROOT/'build/hp2116-seek-validation/recovery/section1.hex'
    executable = cpu/'obj_dir/Vtb_hp2116'
    for path in (checkpoint, executable):
        if not path.is_file():
            parser.error(f'Missing prepared simulation artifact: {path}')
    production = ROOT/'fpga/hp13210/hp13210a_core.v'
    if (cpu/'hp13210a.sv').read_text() != production.read_text().replace(
            'module hp13210a_core', 'module hp13210a'):
        parser.error('Prepared controller differs from production RTL; regenerate and compile it')
    memory = [int(word, 16) for word in checkpoint.read_text().split()]
    expected = {0o126: 0o151302, 0o1542: 0o102206, 0o1550: 0o070156,
                0o1552: 0o102502, 0o1577: 0o064156, 0o1620: 0o015076}
    if any(memory[address] != word for address, word in expected.items()):
        parser.error('Unexpected diagnostic image; trace addresses must be rechecked')
    options = ['+DSN=151302', f'+FAST_MEM={checkpoint}', '+SECTION1_ONLY',
               '+SEEK_US=500', '+CPU_SCALE=15', '+RESPONSE_US=20', '+POLL_NS=200',
               '+DATA_START_US=100', '+STOP_STEP=35', '+MAX_MS=340', '+TRACE=YES',
               '+LOADFILE='+str(ROOT/'hp2116_verilog/diagnostics/'
                               '24296-60001_DSN000200_DIAGNOSTIC_CONFIGURATOR.abin')]
    command = ['docker', 'run', '--rm', '--user', f'{os.getuid()}:{os.getgid()}',
               '-v', f'{ROOT}:{ROOT}', '-w', str(out), '--entrypoint', 'stdbuf',
               IMAGE, '-oL', str(executable)] + options
    paths = [production, checkpoint, executable, *sorted(cpu.glob('*.sv'))]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in paths}
    active = False
    observations = {}
    # Addresses refer to the supplied revision-1805 configured memory image.
    milestones = {'001542': 'dma_flag_test', '001550': 'set_incomplete_marker',
                  '001552': 'read_dma_residue', '001555': 'convert_word_count',
                  '001356': 'compare_status', '001332': 'read_incomplete_marker',
                  '001577': 'dma_error_routine', '001613': 'incomplete_marker_test',
                  '001620': 'report_e13'}
    with (out/'instructions.log').open('w') as log:
        process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            if 'DIAG_STEP' in line and 'step=34 ' in line:
                active = True
            match = re.search(r'IE=[01] ([0-7]{6}) ', line) if active else None
            if not line.startswith('TIME ') or match and int(match[1], 8) < 0o2000:
                log.write(line)
            if match:
                if match[1] in milestones:
                    observations[milestones[match[1]]] = line.strip()
        returncode = process.wait()
    receipt = {'returncode': returncode, 'hardware_programmed': False,
               'diagnostic_modified': False, 'backend': 'SV, not STM32 C++',
               'physical_diagnostic_pass': False, 'options': options,
               'sources_before_run': hashes, 'observations': observations,
               'log_sha256': hashlib.sha256((out/'instructions.log').read_bytes()).hexdigest()}
    receipt['sources_unchanged'] = all(
        hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == digest
        for path, digest in hashes.items())
    (out/'result.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(observations, indent=2))
    if returncode or 'report_e13' not in observations:
        raise SystemExit('Trace incomplete: inspect instructions.log')
    print('Reproduced step 34 E13 path; diagnostic acceptance FAILED.')


if __name__ == '__main__':
    main()
