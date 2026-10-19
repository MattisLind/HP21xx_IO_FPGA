#!/usr/bin/env python3
"""Carrier-specific xc3sprog bridge and backed-up SPI flash programming."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tarfile

import fpga
from build_programmer import COMMIT, SHA256

OUT = fpga.BUILD / 'spi'
SIZE = 2097152
PINS = {'CSB': 'P38', 'DRCK1': 'P70', 'MISO': 'P65', 'MOSI': 'P64'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inputs():
    return {'script': sha(__file__), 'driver': sha(fpga.__file__),
            'board': fpga.read_board('config/board.local.json'),
            'pins': PINS, 'upstream': COMMIT}


def validated_blink():
    meta = json.loads((fpga.BUILD / 'blink/success.json').read_text())
    board = fpga.read_board('config/board.local.json')
    if meta['board'] != board or meta['input_sha256'] != fpga.fingerprint(board):
        raise RuntimeError('Blink sources/settings changed; run make blink first')
    if meta['bitstream_sha256'] != sha(fpga.BUILD / 'blink/blink.bit'):
        raise RuntimeError('Blink bitstream changed; run make blink first')
    if board['part'] != 'xc6slx9-2-tqg144' or board['iostandard'] != 'LVCMOS33':
        raise RuntimeError('This bridge targets the confirmed -2 TQG144 3.3 V carrier')
    return meta


def build():
    blink = validated_blink()
    archive = fpga.BUILD / ('tools/xc3sprog-' + COMMIT + '.tar.gz')
    if sha(archive) != SHA256:
        raise RuntimeError('Programmer archive checksum mismatch')
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'success.json').unlink(missing_ok=True)
    with tarfile.open(archive) as tar:
        for filename in ('bscan_s6_spi_isf_ext.v', 'bscan_common.v'):
            member = next(m for m in tar.getmembers()
                          if m.name.endswith('/bscan_spi/' + filename))
            (OUT / filename).write_bytes(tar.extractfile(member).read())
    # Keep a matching copy of the routed, timing-checked blink implementation.
    for name in ('blink.ncd', 'blink.pcf'):
        shutil.copy2(fpga.BUILD / 'blink' / name, OUT / name)
    request = {'inputs': inputs(), 'blink': blink,
               'ncd_sha256': sha(OUT / 'blink.ncd'),
               'pcf_sha256': sha(OUT / 'blink.pcf')}
    fpga.write_json(OUT / 'request.json', request)
    command, image = fpga.docker_run(['python3', 'scripts/spi_flash.py', 'flow'])
    fpga.run(command, log=OUT / 'container.log', env=fpga.docker_env())
    request.update({'image': image, 'completed_utc': fpga.timestamp(),
                    'bridge_sha256': sha(OUT / 'bridge.bit'),
                    'boot_sha256': sha(OUT / 'blink-boot.bit')})
    fpga.write_json(OUT / 'success.json', request)


def flow():
    ucf = ''.join('NET "{}" LOC = "{}" | IOSTANDARD = LVCMOS33;\n'.format(k, v)
                  for k, v in PINS.items())
    # Conservative 10 MHz bound for the JTAG-derived bridge clock.
    ucf += ('NET "DRCK1_OBUF" TNM_NET = "bridge_clock";\n'
            'TIMESPEC "TS_bridge" = PERIOD "bridge_clock" 100 ns HIGH 50%;\n')
    (OUT / 'bridge.ucf').write_text(ucf)
    (OUT / 'bridge.prj').write_text('verilog work "bscan_s6_spi_isf_ext.v"\n')
    (OUT / 'bridge.xst').write_text('run\n-ifn bridge.prj\n-ifmt mixed\n-ofn bridge.ngc\n'
                                  '-ofmt NGC\n-p xc6slx9-2-tqg144\n-top top\n'
                                  '-opt_mode Speed\n-opt_level 1\n')
    steps = [
        ('xst', ['xst', '-ifn', 'bridge.xst', '-ofn', 'bridge.syr']),
        ('ngdbuild', ['ngdbuild', '-p', 'xc6slx9-2-tqg144', '-uc', 'bridge.ucf', 'bridge.ngc', 'bridge.ngd']),
        ('map', ['map', '-w', '-p', 'xc6slx9-2-tqg144', '-o', 'bridge_map.ncd', 'bridge.ngd', 'bridge.pcf']),
        ('par', ['par', '-w', 'bridge_map.ncd', 'bridge.ncd', 'bridge.pcf']),
        ('trce', ['trce', '-v', '10', 'bridge.ncd', 'bridge.pcf', '-o', 'bridge.twr']),
    ]
    for name, command in steps:
        fpga.run(command, cwd=OUT, log=OUT / (name + '.log'))
    report = (OUT / 'bridge.twr').read_text()
    if (not re.search(r'Timing errors:\s*0\s+Score:\s*0\b', report)
            or 'TS_bridge' not in report
            or not re.search(r'[1-9]\d* paths analyzed', report)):
        raise RuntimeError('Bridge timing validation failed; inspect bridge.twr')
    fpga.run(['bitgen', '-w', '-g', 'StartupClk:JtagClk', '-g', 'UnusedPin:Pullnone',
              'bridge.ncd', 'bridge.bit', 'bridge.pcf'], cwd=OUT, log=OUT / 'bitgen.log')
    fpga.run(['bitgen', '-w', '-g', 'StartupClk:Cclk', '-g', 'spi_buswidth:1',
              '-g', 'ConfigRate:2', '-g', 'UnusedPin:Pullnone',
              'blink.ncd', 'blink-boot.bit', 'blink.pcf'], cwd=OUT, log=OUT / 'boot-bitgen.log')


def evidence():
    validated_blink()
    meta = json.loads((OUT / 'success.json').read_text())
    if meta['inputs'] != inputs():
        raise RuntimeError('Bridge inputs changed; rebuild with make spi-bridge')
    for filename, key in (('bridge.bit', 'bridge_sha256'), ('blink-boot.bit', 'boot_sha256')):
        if sha(OUT / filename) != meta[key]:
            raise RuntimeError(filename + ' changed since build')
    return meta


def spi(action, files=(), load=False):
    command = [fpga.require_tool('xc3sprog'), '-c', 'xpc',
               '-I' + (str(OUT / 'bridge.bit') if load else '')] + list(files)
    log = OUT / (action + '.log')
    fpga.run(command, log=log)
    text = log.read_text()
    if 'JEDEC: ef 40 0x15' not in text:
        raise RuntimeError('Expected Winbond EF 40 15 identity was not confirmed')
    status = re.search(r'Winbond status: SR1=([0-9a-f]{2}) SR2=([0-9a-f]{2}) SR3=([0-9a-f]{2})', text)
    if not status:
        raise RuntimeError('Rebuild programmer with status reporting before flash operations')
    sr1, sr2, sr3 = (int(v, 16) for v in status.groups())
    if not sr2 & 2:
        raise RuntimeError('QE is clear with IO2/IO3 unconnected; stop and inspect hardware')
    if sr1 & 0x7d or sr2 & 0x40 or sr3 & 4:
        raise RuntimeError('Flash is busy or protected; inspect status before proceeding')
    return {'jedec': 'ef4015', 'sr1': sr1, 'sr2': sr2, 'sr3': sr3}


def hardware(action):
    meta = evidence()
    status = spi('identify', load=True)
    backup = OUT / 'original.bin'
    receipt = OUT / 'backup.json'
    if action == 'probe':
        fpga.write_json(OUT / 'identity.json', dict(status, observed_utc=fpga.timestamp()))
        return
    if action == 'backup':
        if backup.exists():
            raise RuntimeError('Original backup already exists; preserve it')
        # Explicit size prevents upstream saveAs() trimming trailing FF bytes.
        spi('backup', [str(backup) + ':r:0:BIN:' + str(SIZE)])
        if backup.stat().st_size != SIZE:
            raise RuntimeError('Flash backup is not exactly 2 MiB')
        spi('backup-verify', [str(backup) + ':v:0:BIN'])
        fpga.write_json(receipt, {'sha256': sha(backup), 'size': SIZE,
                                 'verified_utc': fpga.timestamp(), 'status': status})
    elif action == 'program':
        saved = json.loads(receipt.read_text())
        if backup.stat().st_size != SIZE or sha(backup) != saved['sha256']:
            raise RuntimeError('Valid verified 2 MiB original backup required')
        # Reconfirm that the backup still belongs to the currently attached flash.
        spi('before-write-verify', [str(backup) + ':v:0:BIN'])
        spi('program', [str(OUT / 'blink-boot.bit') + ':w:0:BIT'])
        spi('verify', [str(OUT / 'blink-boot.bit') + ':v:0:BIT'])
        fpga.write_json(OUT / 'programmed.json', {'completed_utc': fpga.timestamp(),
                       'bitstream_sha256': meta['boot_sha256'], 'backup_sha256': saved['sha256'],
                       'status': status, 'power_cycle_confirmed': False})
        # Return FPGA to normal master configuration, exercising flash startup.
        fpga.run([fpga.require_tool('xc3sprog'), '-c', 'xpc', '-R'], log=OUT / 'reconfigure.log')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'flow', 'probe', 'backup', 'program'])
    action = parser.parse_args().action
    if action == 'build':
        build()
    elif action == 'flow':
        flow()
    else:
        hardware(action)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        sys.exit(1)
