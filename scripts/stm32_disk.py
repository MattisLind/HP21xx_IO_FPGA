#!/usr/bin/env python3
"""Fetch, build and test disk firmware; program hardware only on explicit request."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile
import io
import datetime

import stm32

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'firmware/stm32-disk'
OUT = ROOT / 'build/stm32-disk'


def run(args):
    stm32.run(args)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch():
    for name, spec in json.loads((SOURCE / 'dependencies.json').read_text()).items():
        target = OUT / 'deps' / name
        if target.exists():
            marker = target / '.archive-sha256'
            if marker.exists() and marker.read_text().strip() == spec['archive_sha256']:
                print(name + ': pinned dependency already present')
                continue
            raise RuntimeError(f'{target} exists; keep it or choose a fresh directory before fetching')
        with urllib.request.urlopen(spec['url'], timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != spec['archive_sha256']:
            raise RuntimeError('Archive checksum mismatch: ' + name)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            prefix = archive.namelist()[0].split('/')[0]
            for member in archive.infolist():
                relative = Path(member.filename).relative_to(prefix)
                if member.is_dir() or not relative.parts:
                    continue
                if '..' in relative.parts or relative.is_absolute():
                    raise RuntimeError('Invalid archive path')
                path = target / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(member))
        (target / '.archive-sha256').write_text(spec['archive_sha256'] + '\n')
        print(f'{name} {spec["version"]} at {spec["commit"]}')


def hashes():
    paths = list(SOURCE.rglob('*')) + list((OUT / 'deps').rglob('*'))
    paths += [Path(__file__).resolve(), ROOT/'scripts/stm32.py', ROOT/'firmware/stm32/cmake/arm-toolchain.cmake']
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths) if p.is_file()}


def build():
    deps = stm32.dependencies()
    for name, spec in json.loads((SOURCE / 'dependencies.json').read_text()).items():
        marker = OUT / 'deps' / name / '.archive-sha256'
        if not marker.exists() or marker.read_text().strip() != spec['archive_sha256']:
            raise RuntimeError('Fetch pinned libraries first: make stm32-disk-deps')
    if 'version=' + stm32.VERSION not in (deps['core'] / 'platform.txt').read_text():
        raise RuntimeError('Use STM32duino ' + stm32.VERSION)
    core = OUT / ('core-' + stm32.VERSION)
    core.mkdir(parents=True, exist_ok=True)
    for entry in deps['core'].iterdir():
        target = core / entry.name
        if entry.name == 'cmake':
            shutil.copytree(entry, target, dirs_exist_ok=True)
        elif not target.exists():
            target.symlink_to(entry, target_is_directory=entry.is_dir())
        elif target.resolve() != entry.resolve():
            raise RuntimeError('Core sources changed; choose a fresh build directory')
    (core / 'cmake/boards_db.cmake').touch()
    receipt = OUT / 'success.json'
    receipt.unlink(missing_ok=True)
    before = hashes()
    folder = OUT / 'firmware'
    run(['cmake', '-S', SOURCE, '-B', folder, '-G', 'Unix Makefiles',
         '-DCORE_PATH=' + str(core), '-DCMSIS5_PATH=' + str(deps['cmsis']),
         '-DARM_TOOLCHAIN_BIN=' + str(deps['compiler']),
         '-DDISK_DEPS=' + str(OUT/'deps'), '-DPython3_EXECUTABLE=' + sys.executable])
    run(['cmake', '--build', folder, '--parallel', str(min(os.cpu_count() or 2, 8))])
    if hashes() != before:
        raise RuntimeError('Sources changed during build')
    receipt.write_text(json.dumps({'sources': before, 'elf_sha256': digest(folder/'disk_backend.elf'),
                                  'hardware_tested': False, 'programmed': False,
                                  'core_version': stm32.VERSION,
                                  'dependencies': {k:str(v) for k,v in deps.items()}}, indent=2)+'\n')


def test():
    folder = OUT / 'native-tests'
    folder.mkdir(parents=True, exist_ok=True)
    executable = folder / 'backend-test'
    run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-g',
         '-fsanitize=address,undefined', '-I'+str(SOURCE/'src'),
         SOURCE/'src/backend.cpp', SOURCE/'src/config.cpp',
         ROOT/'tests/stm32/backend_test.cpp', '-o', executable])
    run([executable])
    media_test = folder / 'media-test'
    run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-g',
         '-fsanitize=address,undefined', '-I'+str(SOURCE/'src'),
         ROOT/'tests/stm32/media_test.cpp', '-o', media_test])
    run([media_test])
    disk_test = folder / 'sd-diskio-test'
    run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-g',
         '-fsanitize=address,undefined', '-I'+str(ROOT/'tests/stm32/sd_stub'),
         SOURCE/'src/sd_diskio.c', ROOT/'tests/stm32/sd_diskio_test.c', '-o', disk_test])
    run([disk_test])


def program():
    receipt = OUT/'success.json'
    meta = json.loads(receipt.read_text())
    image = OUT/'firmware/disk_backend.elf'
    if meta['sources'] != hashes() or meta['elf_sha256'] != digest(image):
        raise RuntimeError('Backend changed since build; run make stm32-disk-build')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = OUT/'backups'
    folder.mkdir(exist_ok=True)
    backup = folder/('before-disk-backend-'+stamp+'.bin')
    probe = [str(stm32.dependencies()['openocd']), '-f', 'interface/stlink.cfg', '-f', 'target/stm32f4x.cfg']

    def logged(command, name):
        log = OUT/name
        print('+', ' '.join(command), flush=True)
        with log.open('w') as output:
            result = subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
        print(log.read_text(), flush=True)
        result.check_returncode()
        return str(log.relative_to(ROOT))

    # Save and verify the currently installed 512 KiB image before replacement.
    backup_log = logged(probe+['-c', 'adapter speed 1000; init; reset halt; flash probe 0; flash banks; '
                        'dump_image "'+str(backup)+'" 0x08000000 0x80000; '
                        'verify_image "'+str(backup)+'" 0x08000000 bin; shutdown'], 'backup-'+stamp+'.log')
    if backup.stat().st_size != 512*1024:
        raise RuntimeError('STM32 backup must be exactly 512 KiB')
    if meta['sources'] != hashes() or meta['elf_sha256'] != digest(image):
        raise RuntimeError('Backend changed during backup; rebuild before programming')
    log = logged(probe+['-c', 'adapter speed 1000; program "'+str(image)+'" verify reset exit'], 'program-'+stamp+'.log')
    (OUT/'programmed.json').write_text(json.dumps({
        'programmed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'elf_sha256': meta['elf_sha256'], 'sources': meta['sources'],
        'verified': True, 'reset_requested': True, 'hardware_disk_tested': False,
        'backup': {'path': str(backup.relative_to(ROOT)), 'sha256': digest(backup),
                   'size': backup.stat().st_size, 'verified': True, 'log': backup_log},
        'log': log}, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['deps', 'build', 'test', 'program'])
    action = parser.parse_args().action
    try:
        {'deps':fetch, 'build':build, 'test':test, 'program':program}[action]()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print('ERROR:', error, file=sys.stderr)
        sys.exit(1)
