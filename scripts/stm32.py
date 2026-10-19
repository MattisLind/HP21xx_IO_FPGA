#!/usr/bin/env python3
"""Build STM32 USB/FSMC firmware with Make/CMake and installed STM32duino tools."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/stm32'
VERSION = '2.9.0'


def dependencies():
    local = ROOT / 'config/stm32.local.json'
    config = json.loads(local.read_text()) if local.exists() else {}
    packages = Path(config.get('packages', Path.home() / 'Library/Arduino15/packages'))
    st = packages / 'STMicroelectronics'
    values = {
        'core': st / 'hardware/stm32' / VERSION,
        'compiler': st / 'tools/xpack-arm-none-eabi-gcc/13.2.1-1.1/bin',
        'cmsis': st / 'tools/CMSIS/5.9.0',
        'openocd': st / 'tools/xpack-openocd/0.12.0-4/bin/openocd',
    }
    return {key: Path(config.get(key, value)).expanduser().resolve()
            for key, value in values.items()}


def run(command):
    print('+', ' '.join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=ROOT, check=True)


def source_hashes():
    paths = list((ROOT / 'firmware/stm32').rglob('*')) + [Path(__file__)]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths) if p.is_file()}


def build():
    deps = dependencies()
    for path in [deps['core'] / 'cmake/build_sketch.cmake',
                 deps['compiler'] / 'arm-none-eabi-gcc',
                 deps['cmsis'] / 'CMSIS/Core/Include/core_cm4.h']:
        if not path.exists():
            raise RuntimeError('Missing dependency: ' + str(path) + '; see firmware/stm32/README.md')
    if 'version=' + VERSION not in (deps['core'] / 'platform.txt').read_text():
        raise RuntimeError('Use the tested STM32duino core ' + VERSION)
    # Core CMake regenerates its board database. Keep that write in build/;
    # installed sources/libraries remain read-only symlinks.
    core = OUT / ('core-' + VERSION)
    core.mkdir(parents=True, exist_ok=True)
    for entry in deps['core'].iterdir():
        target = core / entry.name
        if entry.name == 'cmake':
            shutil.copytree(entry, target, dirs_exist_ok=True)
        elif not target.exists():
            target.symlink_to(entry, target_is_directory=entry.is_dir())
        elif target.resolve() != entry.resolve():
            raise RuntimeError('Core source changed; choose a fresh build/stm32 directory')
    # The database shipped with this pinned release matches its boards.txt.
    (core / 'cmake/boards_db.cmake').touch()
    folder = OUT / 'firmware'
    receipt = OUT / 'success.json'
    receipt.unlink(missing_ok=True)
    hashes = source_hashes()
    run(['cmake', '-S', ROOT / 'firmware/stm32', '-B', folder, '-G', 'Unix Makefiles',
         '-DCORE_PATH=' + str(core), '-DCMSIS5_PATH=' + str(deps['cmsis']),
         '-DARM_TOOLCHAIN_BIN=' + str(deps['compiler']),
         '-DPython3_EXECUTABLE=' + sys.executable])
    run(['cmake', '--build', folder, '--parallel', str(min(os.cpu_count() or 2, 8))])
    if source_hashes() != hashes:
        raise RuntimeError('Firmware sources changed during build')
    image = folder / 'fsmc_test.elf'
    metadata = {'sources': hashes, 'dependencies': {k: str(v) for k, v in deps.items()},
                'core_version': VERSION, 'board': 'DevEBox STM32F4XX-M / STM32F407VET6',
                'hse_hz': 8000000, 'hclk_hz': 168000000,
                'elf_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
                'hardware_tested': False}
    receipt.write_text(json.dumps(metadata, indent=2) + '\n')


def program():
    meta = json.loads((OUT / 'success.json').read_text())
    image = OUT / 'firmware/fsmc_test.elf'
    if meta['sources'] != source_hashes() or meta['elf_sha256'] != hashlib.sha256(image.read_bytes()).hexdigest():
        raise RuntimeError('Firmware changed since successful build; run make stm32-build')
    # Invoked only by an explicit program command, never by build/test.
    run([dependencies()['openocd'], '-f', 'interface/stlink.cfg', '-f', 'target/stm32f4x.cfg',
         '-c', 'program "' + str(image) + '" verify reset exit'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['doctor', 'build', 'program'])
    action = parser.parse_args().action
    if action == 'doctor':
        for name, path in dependencies().items():
            print(name + ': ' + str(path) + (' [present]' if path.exists() else ' [missing]'))
    elif action == 'build':
        build()
    else:
        program()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print('ERROR:', error, file=sys.stderr)
        sys.exit(1)
