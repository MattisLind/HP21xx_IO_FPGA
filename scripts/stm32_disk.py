#!/usr/bin/env python3
"""Fetch pinned disk libraries and build/test firmware offline; never program hardware."""
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
    paths += [Path(__file__), ROOT/'scripts/stm32.py', ROOT/'firmware/stm32/cmake/arm-toolchain.cmake']
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['deps', 'build', 'test'])
    action = parser.parse_args().action
    try:
        {'deps':fetch, 'build':build, 'test':test}[action]()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print('ERROR:', error, file=sys.stderr)
        sys.exit(1)
