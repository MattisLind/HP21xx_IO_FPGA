#!/usr/bin/env python3
"""Build the HP ALGOL chess sources into a bootable HP 2100S RTE disk."""

import argparse
import json
import re
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

from rte2100s import IMAGE_SIZE, ROOT, digest, run_simh


TEMPLATES = ROOT / "software/rte-2100s/chess"
SOURCE_NAMES = ["chess.alg", *(f"chess{i}.asm" for i in range(1, 6)),
                "chess.txt", "chessbcs.txt", "mkchess.sim"]


def cached_source(path, descriptor):
    if not path.exists():
        print(f"Downloading {descriptor['url']}", flush=True)
        with urllib.request.urlopen(descriptor["url"], timeout=30) as response:
            data = response.read()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as target:
            target.write(data)
    if digest(path) != descriptor["sha256"]:
        raise RuntimeError(f"Source checksum mismatch: {path}")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=ROOT / "build/rte-2100s",
                        help="verified base RTE output directory")
    parser.add_argument("--output", type=Path, default=ROOT / "build/rte-2100s-chess",
                        help="new output directory; existing directories are refused")
    parser.add_argument("--cache", type=Path, default=ROOT / "build/reference/hpgames",
                        help="download cache for checksum-pinned upstream sources")
    parser.add_argument("--simh", type=Path,
                        default=Path(shutil.which("hp2100") or Path.home() / "simh/BIN/hp2100"))
    parser.add_argument("--timeout", type=float, default=120,
                        help="maximum wall-clock seconds per SIMH stage")
    args = parser.parse_args()
    base, output, cache, simh = (p.expanduser().resolve() for p in
                                 (args.base, args.output, args.cache, args.simh))
    if output.exists():
        parser.error(f"Output already exists; choose a new --output directory: {output}")
    if not simh.is_file():
        parser.error(f"SIMH HP2100 executable not found: {simh}")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    image = base / "rte-2100s.img"
    base_manifest = json.loads((base / "manifest.json").read_text())
    if image.stat().st_size != IMAGE_SIZE:
        parser.error("The base image has the wrong geometry")
    if digest(image) != base_manifest["artifacts"][image.name]["sha256"]:
        parser.error("The base image no longer matches its successful-build manifest")
    for name in ["hardware.ini", "rte-2100s-boot.abs", "rte-2100s-panel.txt"]:
        recorded = base_manifest["templates_sha256"].get(name)
        if recorded is None:
            recorded = base_manifest["artifacts"][name]["sha256"]
        if digest(base / name) != recorded:
            parser.error(f"The base configuration or bootstrap has changed: {name}")

    sources = json.loads((TEMPLATES / "sources.json").read_text())
    downloaded = {name: cached_source(cache / name, descriptor)
                  for name, descriptor in sources.items()}
    output.mkdir(parents=True)
    (output / "source").mkdir()
    (output / "objects").mkdir()
    with zipfile.ZipFile(downloaded["chessbcs.zip"]) as archive:
        # Extract only the named source/doc files. The prebuilt BCS chess.abs
        # is not used: the program must link against this RTE's own library.
        for name in SOURCE_NAMES:
            (output / "source" / name).write_bytes(archive.read(name))
    for name, path in downloaded.items():
        shutil.copyfile(path, output / "source" / name)
    for name in ["hardware.ini", "rte-2100s-boot.abs", "rte-2100s-panel.txt"]:
        shutil.copyfile(base / name, output / name)
    for path in TEMPLATES.iterdir():
        if path.is_file():
            if path.name == "README.md":
                (output / path.name).write_text(
                    path.read_text().replace("../README.md", "base-README.md"))
            else:
                shutil.copyfile(path, output / path.name)
    shutil.copyfile(base / "README.md", output / "base-README.md")
    shutil.copyfile(base / "manifest.json", output / "base-manifest.json")
    target_image = output / "rte-chess.img"
    shutil.copyfile(image, target_image)

    built = run_simh(simh, output, "build.ini", args.timeout,
                     ["NO UNDEFS", "OUTPUT FILE NAME:CHESS", "CHESS_BUILD_OK"])
    if re.findall(r"ERRORS=(\d+)", built) != ["000"]:
        raise RuntimeError("ALGOL did not compile cleanly; inspect build.log")
    if built.count("**  NO ERRORS*") != 10:
        raise RuntimeError("The five two-pass assemblies did not all pass; inspect build.log")
    final_link = built.rsplit("-END", 1)[-1].split("$END SXL", 1)[0]
    if "NO UNDEFS" not in final_link or "\n UNDEFS" in final_link:
        raise RuntimeError("The final link has unresolved references; inspect build.log")
    core = re.search(r"CORE USED\s+([0-7]+)\s+([0-7]+)\s+([0-7]+)\s+([0-7]+)", built)
    if core is None or int(core[2], 8) > 0o77677:
        raise RuntimeError("CHESS does not fit the configured background memory")
    if not re.search(r"^CHESS\s+00006\s+\d+", built, re.MULTILINE):
        raise RuntimeError("FMGR did not find the linked CHESS executable")

    # Prove the saved program runs after a fresh boot, using a disposable copy.
    compiled_hash = digest(target_image)
    shutil.copyfile(target_image, output / "playtest.img")
    played = run_simh(simh, output, "play.ini", args.timeout,
                      ["HP CHESS VERSION A", "YOU MOVED FROM 32 TO 42",
                       "YOU MOVED FROM 35 TO 55", "HP2100S RTE OK", "CHESS_PLAY_OK"])
    moves = re.findall(r"MY MOVE FROM\s+(\d+)\s+TO\s+(\d+)", played)
    if moves != [("85", "65"), ("97", "76")]:
        raise RuntimeError(f"Unexpected chess replies: {moves}; inspect play.log")
    if "Unimplemented" in played or "INDEX?" in played or "MEMORY" in played:
        raise RuntimeError("Chess encountered a runtime error; inspect play.log")
    if digest(target_image) != compiled_hash or digest(image) != base_manifest["artifacts"][image.name]["sha256"]:
        raise RuntimeError("Verification changed an image that should have stayed untouched")

    sd = output / "sd-card"
    (sd / "images").mkdir(parents=True)
    shutil.copyfile(target_image, sd / "images/rte-chess.img")
    (sd / "hp13210.cfg").write_text(
        "drive0=rte-chess.img\ndrive1=none\ndrive2=none\ndrive3=none\n"
    )
    version = subprocess.run([str(simh), "-v"], capture_output=True, text=True,
                             timeout=10, check=True).stdout.strip()
    artifacts = {
        str(p.relative_to(output)): {"bytes": p.stat().st_size, "sha256": digest(p)}
        for p in sorted(output.rglob("*")) if p.is_file() and p.name != "playtest.img"
    }
    manifest = {
        "program": "HP CHESS VERSION A, 1973-10-26, CSL 2001 x167",
        "source_changes": [], "prebuilt_bcs_executable_used": False,
        "sources": sources, "base_image_sha256": digest(image),
        "cpu": "2100", "memory_words": 32768, "printer": False,
        "optional_fp_firmware": False, "core_range_octal": [core[1], core[2]],
        "base_page_range_octal": [core[3], core[4]],
        "simh": {"path": str(simh), "sha256": digest(simh), "version": version},
        "generator_sha256": digest(Path(__file__).resolve()),
        "shared_generator_sha256": digest(ROOT / "scripts/rte2100s.py"),
        "verification": {"algol_errors": 0, "assembly_modules": 5,
                         "unresolved_symbols": 0, "cold_boot": True,
                         "human_moves": [[32, 42], [35, 55]],
                         "computer_moves": [[int(a), int(b)] for a, b in moves],
                         "normal_exit_and_iotst": True},
        "artifacts": artifacts,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    package = output / "rte-2100s-chess-package.zip"
    with zipfile.ZipFile(package, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in [*artifacts, "manifest.json"]:
            archive.write(output / name, name)
    with zipfile.ZipFile(package) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Package checksum verification failed")
    print(f"Ready: {target_image}\nSHA-256: {digest(target_image)}\nPackage: {package}", flush=True)


if __name__ == "__main__":
    main()
