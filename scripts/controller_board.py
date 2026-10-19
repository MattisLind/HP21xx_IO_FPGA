#!/usr/bin/env python3
"""Build the located controller with wired FSMC and program with a fresh backup."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

import fpga
import spi_flash

OUT = fpga.BUILD / 'controller-board'
HDL = [fpga.ROOT / p for p in ('fpga/hp13210/hp13210a_core.v',
       'fpga/hp13210/hp13210a_fpga.v', 'fpga/hp13210/hp13210a_board.v', 'fpga/hp13210/activity_led.v')]
BOOK = fpga.ROOT / 'requirements/HP 21xx IO bus.xlsx'
STM32_BOOK = fpga.ROOT / 'requirements/STM32F407VET.xlsx'
TEST = fpga.ROOT / 'fpga/hp13210/tb_hp13210a_board.sv'
LED_TEST = fpga.ROOT / 'fpga/hp13210/tb_activity_led.sv'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inputs():
    files = HDL + [TEST, LED_TEST, BOOK, STM32_BOOK, Path(__file__), Path(fpga.__file__)]
    return {'files': {str(p.relative_to(fpga.ROOT)): sha(p) for p in files},
            'board': fpga.read_board('config/board.local.json')}


def pinmap():
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(BOOK) as archive:
        shared = [''.join(s.itertext()) for s in ET.fromstring(
            archive.read('xl/sharedStrings.xml')).findall('s:si', ns)]
        root = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
    controls = {3: 'prl', 4: 'flgl', 5: 'sfc', 6: 'irql', 7: 'clf', 8: 'ien',
        9: 'stf', 10: 'iak', 11: 't3', 12: 'skf', 13: 'crs', 14: 'scm_l',
        15: 'iog', 16: 'scl_l', 17: 'popio', 18: 'iob16_or_bios_n', 19: 'srq',
        20: 'ioo', 21: 'clc', 22: 'stc', 23: 'prh', 24: 'ioi', 25: 'sfs',
        32: 'sir', 33: 'irqh', 34: 'scl_h', 37: 'scm_h', 46: 'enf',
        49: 'flgh', 50: 'run', 62: 'edt', 66: 'pon', 67: 'bioo_n', 73: 'sfsb_or_bioi_n'}
    pins = {}
    for row in root.findall('.//s:row', ns):
        cells = {}
        for cell in row.findall('s:c', ns):
            value = cell.find('s:v', ns)
            text = value.text if value is not None else ''.join(cell.itertext())
            if cell.get('t') == 's':
                text = shared[int(text)]
            cells[re.match('[A-Z]+', cell.get('r'))[0]] = text
        try:
            connector = int(float(cells.get('A', '')))
        except ValueError:
            continue
        input_marked = cells.get('D') in ('1', '1.0')
        output_marked = cells.get('E') in ('1', '1.0')
        if not input_marked and not output_marked:
            continue
        direction = 'input' if input_marked else 'output'
        bit = re.fullmatch(r'IOB(\d+):?', cells.get('B', ''))
        if bit:
            name = ('iob_out' if direction == 'input' else 'iob_in') + '<' + bit[1] + '>'
        else:
            name = controls[connector]
        if 'I' not in cells:
            raise RuntimeError('Missing FPGA pin for connector ' + str(connector))
        pins[name] = {'pin': 'P' + str(int(float(cells['I']))), 'direction': direction,
                      'connector': connector}
        if connector == 50:
            pins['run_drive'] = {'pin': 'P' + str(int(float(cells['J']))), 'direction': 'output',
                                 'connector': connector}
    board = fpga.read_board('config/board.local.json')
    for name, pin, direction in (('clk', board['clock_pin'], 'input'),
                                 ('led', board['led_pin'], 'output'), ('flash_cs_n', 'P38', 'output')):
        pins[name] = {'pin': pin, 'direction': direction}
    with zipfile.ZipFile(STM32_BOOK) as archive:
        shared = [''.join(item.itertext()) for item in
                  ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        root = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
    for row in root.findall('.//s:row', ns):
        cells = {}
        for cell in row.findall('s:c', ns):
            value = cell.find('s:v', ns)
            text = value.text if value is not None else ''.join(cell.itertext())
            if cell.get('t') == 's':
                text = shared[int(text)]
            cells[re.match('[A-Z]+', cell.get('r'))[0]] = text
        data = re.fullmatch(r'FSMC_D(\d+)', cells.get('B', ''))
        control = {'FSMC_NOE': 'noe', 'FSMC_NWE': 'nwe',
                   'FSMC_NL / NADV': 'nadv'}.get(cells.get('B'))
        if data:
            name, direction = 'stm32_fsmc_ad<' + data[1] + '>', 'inout'
        elif control:
            name, direction = 'stm32_fsmc_' + control, 'input'
        else:
            continue
        pins[name] = {'pin': 'P' + str(int(float(cells['C']))),
                      'direction': direction, 'stm32_pin': cells['A']}
    if len({p['pin'] for p in pins.values()}) != len(pins):
        raise RuntimeError('Duplicate FPGA pin assignments')
    for name, entry in pins.items():
        if entry['pin'] in {'P37', 'P39', 'P60', 'P64', 'P65', 'P69', 'P70', 'P71'}:
            raise RuntimeError('Reserved configuration/flash pin assigned to ' + name)
    if pins['iob_in<4>']['pin'] != 'P57' or pins['iob_in<12>']['pin'] != 'P58':
        raise RuntimeError('Expected corrected HP output pins P57/P58')
    # Every top-level pin must be assigned, including all bits of each vector.
    ports = re.findall(r'^\s*(input|output|inout)\s+wire\s*(\[(\d+):0\])?\s*(\w+)\s*[,\n]', HDL[2].read_text(), re.M)
    expected = {}
    for direction, width, high, name in ports:
        if width:
            expected.update({name + '<' + str(i) + '>': direction for i in range(int(high) + 1)})
        else:
            expected[name] = direction
    if expected != {name: entry['direction'] for name, entry in pins.items()}:
        raise RuntimeError('Sheet pins/directions do not match the controller board top')
    return pins


def simulate():
    OUT.mkdir(parents=True, exist_ok=True)
    led_target = OUT / 'activity-led-test.vvp'
    fpga.run([fpga.require_tool('iverilog'), '-g2012', '-Wall', '-s', 'tb_activity_led',
              '-o', str(led_target), str(HDL[3]), str(LED_TEST)], log=OUT / 'led-compile.log')
    fpga.run([fpga.require_tool('vvp'), str(led_target)], log=OUT / 'led-sim.log')
    target = OUT / 'board-test.vvp'
    fpga.run([fpga.require_tool('iverilog'), '-g2012', '-Wall', '-s', 'tb_hp13210a_board',
              '-o', str(target)] + [str(p) for p in HDL] + [str(TEST)], log=OUT / 'sim-compile.log')
    fpga.run([fpga.require_tool('vvp'), str(target)], log=OUT / 'sim.log')


def build():
    simulate()
    pins = pinmap()
    (OUT / 'success.json').unlink(missing_ok=True)
    (OUT / 'controller.bit').unlink(missing_ok=True)
    request = {'started_utc': fpga.timestamp(), 'inputs': inputs(), 'pins': pins,
               'stm32_enabled': True, 'led_pulse_ms': 100, 'idle_heartbeat_period_ms': 2000,
               'hp_connector_validation': 'pending; standalone-carrier bring-up image'}
    fpga.write_json(OUT / 'request.json', request)
    command, image = fpga.docker_run(['python3', 'scripts/controller_board.py', 'flow'])
    fpga.run(command, log=OUT / 'container.log', env=fpga.docker_env())
    if inputs() != request['inputs']:
        raise RuntimeError('Inputs changed during controller build')
    request.update({'completed_utc': fpga.timestamp(), 'image': image,
                    'bitstream_sha256': sha(OUT / 'controller.bit')})
    fpga.write_json(OUT / 'success.json', request)


def flow():
    request = json.loads((OUT / 'request.json').read_text())
    ucf = 'NET "clk" TNM_NET = "clk";\nTIMESPEC "TS_clk" = PERIOD "clk" 20 ns HIGH 50%;\n'
    for name, entry in request['pins'].items():
        attrs = 'LOC = "{}" | IOSTANDARD = LVCMOS33'.format(entry['pin'])
        if entry['direction'] == 'output':
            attrs += ' | DRIVE = 8 | SLEW = SLOW'
        elif entry['direction'] == 'input' and name != 'clk':
            # Inverted HP receiver outputs: logical inactive zero needs a high
            # pin. Logical default-one exceptions need low. FSMC is uninverted.
            attrs += ' | ' + ('PULLDOWN' if name in ('prh', 'pon', 'run', 'bioo_n', 'sfsb_or_bioi_n', 'iob16_or_bios_n') else 'PULLUP')
        if name == 'flash_cs_n':
            attrs += ' | PULLUP'
        ucf += 'NET "{}" {};\n'.format(name, attrs)
    (OUT / 'controller.ucf').write_text(ucf)
    (OUT / 'controller.prj').write_text(''.join('verilog work "../../{}"\n'.format(p.relative_to(fpga.ROOT)) for p in HDL))
    (OUT / 'controller.xst').write_text('run\n-ifn controller.prj\n-ifmt mixed\n-ofn controller.ngc\n'
        '-ofmt NGC\n-p xc6slx9-2-tqg144\n-top hp13210a_board\n-opt_mode Speed\n-opt_level 1\n')
    steps = [('xst', ['xst', '-ifn', 'controller.xst', '-ofn', 'controller.syr']),
        ('ngdbuild', ['ngdbuild', '-p', 'xc6slx9-2-tqg144', '-uc', 'controller.ucf', 'controller.ngc', 'controller.ngd']),
        ('map', ['map', '-w', '-p', 'xc6slx9-2-tqg144', '-o', 'controller_map.ncd', 'controller.ngd', 'controller.pcf']),
        ('par', ['par', '-w', 'controller_map.ncd', 'controller.ncd', 'controller.pcf']),
        ('trce', ['trce', '-v', '10', '-u', '10', 'controller.ncd', 'controller.pcf', '-o', 'controller.twr'])]
    for name, command in steps:
        fpga.run(command, cwd=OUT, log=OUT / (name + '.log'))
    fpga.check_timing(OUT / 'controller.twr')
    fpga.run(['bitgen', '-w', '-g', 'StartupClk:Cclk', '-g', 'spi_buswidth:1', '-g', 'ConfigRate:2',
              '-g', 'UnusedPin:Pullnone', 'controller.ncd', 'controller.bit', 'controller.pcf'],
             cwd=OUT, log=OUT / 'bitgen.log')


def validated():
    meta = json.loads((OUT / 'success.json').read_text())
    if meta['inputs'] != inputs() or meta['pins'] != pinmap():
        raise RuntimeError('Controller sources or pin map changed; rebuild')
    if meta['bitstream_sha256'] != sha(OUT / 'controller.bit'):
        raise RuntimeError('Controller bitstream changed since successful build')
    return meta


def program():
    validated()
    spi_flash.evidence()  # Reuse the already verified bridge without modifying it.
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    status = spi_flash.spi('controller-identify-' + stamp, load=True)
    folder = OUT / 'backups'
    folder.mkdir(exist_ok=True)
    backup = folder / ('before-controller-' + stamp + '.bin')
    spi_flash.spi('controller-backup-' + stamp, [str(backup) + ':r:0:BIN:2097152'])
    if backup.stat().st_size != spi_flash.SIZE:
        raise RuntimeError('Current-image backup must be exactly 2 MiB')
    spi_flash.spi('controller-backup-verify-' + stamp, [str(backup) + ':v:0:BIN'])
    backup_meta = {'path': str(backup.relative_to(fpga.ROOT)), 'sha256': sha(backup),
                   'size': backup.stat().st_size, 'verified_utc': fpga.timestamp(), 'status': status}
    fpga.write_json(backup.with_suffix('.json'), backup_meta)
    meta = validated()  # Recheck after the potentially long backup operation.
    spi_flash.spi('controller-program-' + stamp, [str(OUT / 'controller.bit') + ':w:0:BIT'])
    spi_flash.spi('controller-verify-' + stamp, [str(OUT / 'controller.bit') + ':v:0:BIT'])
    receipt = {'verified_utc': fpga.timestamp(), 'bitstream_sha256': meta['bitstream_sha256'],
               'backup': backup_meta, 'status': status, 'power_cycle_confirmed': False}
    fpga.write_json(OUT / 'programmed.json', receipt)
    fpga.run([fpga.require_tool('xc3sprog'), '-c', 'xpc', '-R'], log=OUT / 'reconfigure.log')
    receipt['reconfiguration_requested_utc'] = fpga.timestamp()
    fpga.write_json(OUT / 'programmed.json', receipt)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'flow', 'sim', 'program'])
    try:
        {'build': build, 'flow': flow, 'sim': simulate, 'program': program}[parser.parse_args().action]()
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        sys.exit(1)
