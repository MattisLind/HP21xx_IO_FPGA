#!/usr/bin/env python3
"""Simulate and implement the HP13210 port without producing a loadable image."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import fpga

SOURCES = [fpga.ROOT / 'fpga/hp13210' / name for name in
           ('hp13210a_core.v', 'hp13210a_fpga.v')]
TESTBENCH = fpga.ROOT / 'fpga/hp13210/tb_hp13210a.sv'
OUT = fpga.BUILD / 'controller'


def fingerprint():
    files = SOURCES + [Path(__file__), Path(fpga.__file__)]
    return {str(p.relative_to(fpga.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files}


def simulate():
    out = fpga.BUILD / 'sim/hp13210'
    out.mkdir(parents=True, exist_ok=True)
    variants = [(enabled, 173, 0, 0) for enabled in (0, 1)]
    variants += [(enabled, 200, phase, 0) for enabled in (0, 1) for phase in (0, 5, 10, 15)]
    variants += [(1, 200, phase, 1) for phase in (0, 5, 10, 15)]
    for enabled, pulse, phase, omit_ne in variants:
        name = 'backend-{}-pulse-{}-phase-{}-omit-ne-{}'.format(enabled, pulse, phase, omit_ne)
        target = out / (name + '.vvp')
        fpga.run([fpga.require_tool('iverilog'), '-g2012', '-Wall', '-s', 'tb_hp13210a',
                  '-Ptb_hp13210a.ENABLE_STM32={}'.format(enabled),
                  '-Ptb_hp13210a.HP_PULSE_NS={}'.format(pulse),
                  '-Ptb_hp13210a.START_PHASE_NS={}'.format(phase),
                  '-Ptb_hp13210a.OMIT_NE={}'.format(omit_ne), '-o', str(target)] +
                 [str(p) for p in SOURCES] + [str(TESTBENCH)],
                 log=out / (name + '-compile.log'))
        fpga.run([fpga.require_tool('vvp'), str(target)], log=out / (name + '-test.log'))
    fpga.write_json(out / 'success.json', {'completed_utc': fpga.timestamp(),
                    'inputs': fingerprint(), 'testbench_sha256': hashlib.sha256(TESTBENCH.read_bytes()).hexdigest(),
                    'backend_modes': [0, 1], 'variants': variants})


def smoke():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'success.json').unlink(missing_ok=True)
    (OUT / 'controller.bit').unlink(missing_ok=True)
    request = {'started_utc': fpga.timestamp(), 'inputs': fingerprint(),
               'part': 'xc6slx9-2-tqg144', 'clock_hz': 50000000,
               'backend_enabled_for_implementation': True,
               'downloadable': False}
    fpga.write_json(OUT / 'request.json', request)
    command, image = fpga.docker_run(['python3', 'scripts/controller.py', 'flow'])
    fpga.run(command, log=OUT / 'container.log', env=fpga.docker_env())
    if request['inputs'] != fingerprint():
        raise RuntimeError('Controller inputs changed during implementation; rerun smoke')
    request.update({'completed_utc': fpga.timestamp(), 'image': image})
    fpga.write_json(OUT / 'success.json', request)


def flow():
    # Enable the backend here so synthesis checks the entire port, including
    # its FSMC read mux and tri-state output enable, without needing firmware.
    wrapper = SOURCES[1].read_text()
    # Use an explicit generated harness rather than relying on XST -generics.
    ports = re.findall(r'^\s*(input|output|inout)\s+wire\s*(\[[^\]]+\])?\s*(\w+)\s*[,\n]', wrapper, re.M)
    declarations = ['  {} wire {} {}'.format(d, w or '', n) for d, w, n in ports]
    top = 'module controller_smoke (\n' + ',\n'.join(declarations) + '\n);\n'
    top += 'hp13210a_fpga #(.ENABLE_STM32(1)) dut (\n'
    top += ',\n'.join('.{}({})'.format(n, n) for d, w, n in ports) + '\n);\nendmodule\n'
    (OUT / 'top.v').write_text(top)
    ucf = ('NET "clk" LOC = "P56";\nNET "clk" TNM_NET = "clk";\n'
           'TIMESPEC "TS_clk" = PERIOD "clk" 20 ns HIGH 50%;\n')
    for direction, width, name in ports:
        ucf += 'NET "{}{}" IOSTANDARD = LVCMOS33;\n'.format(name, '<*>' if width else '')
    (OUT / 'controller.ucf').write_text(ucf)
    (OUT / 'controller.prj').write_text(''.join('verilog work "../../{}"\n'.format(p.relative_to(fpga.ROOT))
                                              for p in SOURCES) + 'verilog work "top.v"\n')
    (OUT / 'controller.xst').write_text('run\n-ifn controller.prj\n-ifmt mixed\n'
        '-ofn controller.ngc\n-ofmt NGC\n-p xc6slx9-2-tqg144\n-top controller_smoke\n'
        '-opt_mode Speed\n-opt_level 1\n')
    steps = [
        ('xst', ['xst', '-ifn', 'controller.xst', '-ofn', 'controller.syr']),
        ('ngdbuild', ['ngdbuild', '-p', 'xc6slx9-2-tqg144', '-uc', 'controller.ucf', 'controller.ngc', 'controller.ngd']),
        ('map', ['map', '-w', '-p', 'xc6slx9-2-tqg144', '-o', 'controller_map.ncd', 'controller.ngd', 'controller.pcf']),
        ('par', ['par', '-w', 'controller_map.ncd', 'controller.ncd', 'controller.pcf']),
        ('trce', ['trce', '-v', '10', '-u', '10', 'controller.ncd', 'controller.pcf', '-o', 'controller.twr']),
    ]
    for name, command in steps:
        fpga.run(command, cwd=OUT, log=OUT / (name + '.log'))
    fpga.check_timing(OUT / 'controller.twr')
    fpga.run(['bitgen', '-j', '-w', '-g', 'UnusedPin:Pullnone', 'controller.ncd',
              'controller.drc', 'controller.pcf'], cwd=OUT, log=OUT / 'bitgen.log')
    if (OUT / 'controller.bit').exists():
        raise RuntimeError('Controller smoke test must not produce a bitstream')
    print('PASS: HP13210 full-controller ISE implementation; no download image')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['sim', 'smoke', 'flow'])
    try:
        {'sim': simulate, 'smoke': smoke, 'flow': flow}[parser.parse_args().action]()
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        sys.exit(1)
