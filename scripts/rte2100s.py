#!/usr/bin/env python3
"""Generate and cold-boot-test HP 29016D RTE for the 32KW HP 2100S."""

import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "software" / "rte-2100s"
IMAGE_SIZE = 203 * 4 * 24 * 128 * 2


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_simh(simh, output, command_file, timeout, markers):
    log_path = output / (Path(command_file).stem + ".log")
    print(f"Running {command_file}; log: {log_path}", flush=True)
    with log_path.open("w") as log:
        try:
            result = subprocess.run(
                [str(simh), command_file],
                cwd=output,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"SIMH timed out; inspect {log_path}") from exc
    text = log_path.read_text(errors="replace")
    failures = (
        "%SIM-ERROR:",
        "Unknown command",
        "Command not allowed",
        "End of tape on the PTR",
        "Non-existent device",
        "Unimplemented instruction",
        "Unused I/O select code",
        "INPUT ERROR",
        "NO SUCH PROG",
        "FMGR-006",
    )
    if result.returncode or any(message in text for message in failures):
        raise RuntimeError(f"SIMH failed; inspect {log_path}")
    for marker in markers:
        if marker not in text:
            raise RuntimeError(f"Missing {marker!r}; inspect {log_path}")
    return text


def export_bootstrap(output):
    """Decode and checksum the punched HP absolute tape for panel entry."""
    tape = (output / "rte-2100s-boot.abs").read_bytes()
    words = {}
    offset = 0
    while offset < len(tape):
        if tape[offset] == 0:
            offset += 1
            continue
        count = tape[offset]
        end = offset + 6 + 2 * count
        if end > len(tape):
            raise RuntimeError("Truncated bootstrap tape")
        record = struct.unpack(f">{count + 2}H", tape[offset + 2 : end])
        if sum(record[:-1]) & 0xFFFF != record[-1]:
            raise RuntimeError("Bootstrap tape checksum mismatch")
        address = record[0]
        for index, word in enumerate(record[1:-1]):
            words[address + index] = word
        offset = end
    if sorted(words) != list(range(0o14, 0o101)) or words[0o100] != 0o024014:
        raise RuntimeError("Unexpected RTE bootstrap layout")
    listing = [
        "HP 2100S RTE bootstrap: PTR 12, disk data 14 / command 15 (octal).",
        "Deposit the following 53 words. All addresses and values are octal.",
        "Then set S=000000, P=000100, PRESET and RUN.",
        "Alternatively load rte-2100s-boot.abs with the SC 12 binary loader.",
        "",
        "Address  Word",
    ]
    listing.extend(f"{address:06o}   {word:06o}" for address, word in sorted(words.items()))
    (output / "rte-2100s-panel.txt").write_text("\n".join(listing) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path.home() / "Downloads" / "RTE",
                        help="extracted Sancho/Bryan HP 29016D RTE kit (January 2020)")
    parser.add_argument("--simh", type=Path,
                        default=Path(shutil.which("hp2100") or Path.home() / "simh/BIN/hp2100"))
    parser.add_argument("--output", type=Path, default=ROOT / "build/rte-2100s",
                        help="new output directory; existing directories are refused")
    parser.add_argument("--timeout", type=float, default=60,
                        help="maximum wall-clock seconds per SIMH stage")
    args = parser.parse_args()
    source, simh, output = (path.expanduser().resolve() for path in
                            (args.source, args.simh, args.output))
    readme = source / "RTE ReadMe.txt"
    if not readme.is_file() or "HP 29016D RTE" not in readme.read_text():
        parser.error(f"Not the expected HP 29016D RTE kit: {source}")
    if not simh.is_file():
        parser.error(f"SIMH HP2100 executable not found: {simh}")
    if output.exists():
        parser.error(f"Output already exists; choose a new --output directory: {output}")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    output.mkdir(parents=True)
    shutil.copytree(source / "rtgen", output / "rtgen")
    shutil.copyfile(readme, output / "SOURCE-README.txt")
    inputs = {
        str(path.relative_to(source)): digest(path)
        for path in sorted((source / "rtgen").rglob("*")) if path.is_file()
    }
    inputs[readme.name] = digest(readme)
    for path in TEMPLATES.iterdir():
        if not path.is_file():
            continue
        if path.name.endswith(".src.txt"):
            # The simulated paper tape reader needs the HP source's CR/LF lines.
            (output / path.name).write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        else:
            shutil.copyfile(path, output / path.name)

    generated = run_simh(simh, output, "generate.ini", args.timeout,
                         ["NO UNDEF EXTS", "SYSTEM STORED ON DISC", "ILAB=SYS",
                          "ILAB=AUX", "T.END", "GENERATION_OK"])
    # The kit deliberately replaces SXL's TERMF routine. Its two diagnostics
    # are also present in the original distribution's generation transcript.
    if re.findall(r"^ERR (\d+)$", generated, re.MULTILINE) != ["08", "05"]:
        raise RuntimeError("Unexpected RTGEN diagnostics; inspect generate.log")
    if "DVR12(00)" in generated:
        raise RuntimeError("Unexpected printer driver in generated system")
    image = output / "rte-2100s.img"
    if image.stat().st_size != IMAGE_SIZE:
        raise RuntimeError(f"Unexpected image size: {image.stat().st_size}")
    export_bootstrap(output)

    # Verify a disposable copy. A second simulator process checks persistence.
    pristine_hash = digest(image)
    shutil.copyfile(image, output / "verification.img")
    verified = run_simh(simh, output, "verify.ini", args.timeout,
                        ["**  NO ERRORS*", "NO UNDEFS", "OUTPUT FILE NAME:IOTST",
                         "T.END", "VERIFY_OK"])
    rebooted = run_simh(simh, output, "verify-reboot.ini", args.timeout, ["REBOOT_OK"])
    for text in (verified, rebooted):
        if not re.search(r"\*ON,IOTST\nHP2100S RTE OK", text):
            raise RuntimeError("The disk-resident IOTST program did not execute")
    if digest(image) != pristine_hash:
        raise RuntimeError("Verification unexpectedly modified the original image")

    # Deliver the tested disk with IOTST installed for the real-machine check.
    shutil.copyfile(output / "verification.img", image)
    sd = output / "sd-card"
    (sd / "images").mkdir(parents=True)
    shutil.copyfile(image, sd / "images/rte-2100s.img")
    (sd / "hp13210.cfg").write_text(
        "drive0=rte-2100s.img\ndrive1=none\ndrive2=none\ndrive3=none\n"
    )
    artifacts = {
        str(path.relative_to(output)): {"bytes": path.stat().st_size, "sha256": digest(path)}
        for path in [image, output / "rte-2100s-boot.abs", output / "rte-2100s-panel.txt",
                     sd / "images/rte-2100s.img", sd / "hp13210.cfg"]
    }
    version = subprocess.run([str(simh), "-v"], capture_output=True, text=True,
                             timeout=10, check=True).stdout.strip()
    manifest = {
        "system": "HP 29016D RTE-MH (1971), Sancho/Bryan January 2020 kit",
        "cpu": "2100", "memory_words": 32768,
        "select_codes_octal": {"tbg": "10", "tty": "11", "ptr": "12", "ptp": "13",
                               "disk_data": "14", "disk_command": "15"},
        "printer": False, "optional_fp_firmware": False,
        "requires": ["EAU (standard 2100)", "DMA", "memory protect"],
        "geometry": {"cylinders": 203, "heads": 4, "sectors_per_track": 24,
                     "words_per_sector": 128, "word_byte_order": "little-endian"},
        "boot": "RTGEN bootstrap tape or panel listing; S=0, P=100 octal, drive 0",
        "simh": {"executable": str(simh), "sha256": digest(simh), "version": version},
        "source": str(source), "inputs_sha256": inputs,
        "generator_sha256": digest(Path(__file__).resolve()),
        "templates_sha256": {p.name: digest(p) for p in sorted(TEMPLATES.iterdir()) if p.is_file()},
        "verification": ["cold boot", "FMGR directory", "ASMB assembly", "SXL link",
                         "disk file write/read", "IOTST execution", "STATS",
                         "IOTST execution after second cold boot",
                         "unimplemented/unused-select-code/I/O-error stops enabled"],
        "artifacts": artifacts,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Ready: {image}\nSHA-256: {digest(image)}\nSD layout: {sd}", flush=True)


if __name__ == "__main__":
    main()
