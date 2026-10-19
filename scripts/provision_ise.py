#!/usr/bin/env python3
"""Extract the Spartan-6 CLI tools directly from the vendor VM's virtual disk.

The VM is never booted or expanded to a raw disk. Python 3.10+ and the packages
in toolchain/extract-requirements.txt are needed on the extraction host only.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tarfile
import time
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
sys.path.insert(0, str(BUILD / "tools/python"))
EXPECTED_MD5 = "085a59d7e0e33f03eaae730c25f22bd4"
VENDOR_ROOT = "/opt/Xilinx/14.7/ISE_DS"
KEPT_ISE_DIRS = {"bin", "lib", "data", "spartan6", "spartan6l", "verilog", "vhdl",
                 "fpga", "xilinx", "xilinxun", "msg", "fpgacore", "xbr"}


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def extract_vm(archive):
    out = BUILD / "ise-vm"
    out.mkdir(parents=True, exist_ok=True)
    signature = {"path": str(archive), "size": archive.stat().st_size,
                 "mtime_ns": archive.stat().st_mtime_ns}
    receipt = out / "archive.json"
    previous = json.loads(receipt.read_text()) if receipt.exists() else {}
    if previous.get("signature") != signature or previous.get("md5") != EXPECTED_MD5:
        print("Checking vendor archive MD5...", flush=True)
        digest = hashlib.md5()
        with archive.open("rb") as source:
            for chunk in iter(lambda: source.read(16 * 1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != EXPECTED_MD5:
            raise RuntimeError("Archive checksum does not match the documented 14.7 VM distribution")
        save(receipt, {"signature": signature, "md5": digest.hexdigest()})
    target = out / "14.7_VM-disk001.vmdk"
    with ZipFile(archive) as zipped, zipped.open("ova/14.7_VM.ova") as stream:
        with tarfile.open(fileobj=stream, mode="r|") as ova:
            for member in ova:
                name = Path(member.name).name
                if name == "14.7_VM.ovf":
                    (out / name).write_bytes(ova.extractfile(member).read())
                if name == target.name:
                    if target.exists() and target.stat().st_size == member.size:
                        print("Reusing extracted compressed VMDK", flush=True)
                        return target
                    if shutil.disk_usage(out).free < member.size + 2 * 2**30:
                        raise RuntimeError("Need room for the compressed VMDK plus at least 2 GiB")
                    done = 0
                    milestone = 0
                    partial = target.with_suffix(".vmdk.partial")
                    with ova.extractfile(member) as source, partial.open("wb") as dest:
                        while chunk := source.read(8 * 1024 * 1024):
                            dest.write(chunk)
                            done += len(chunk)
                            if done // 2**30 > milestone:
                                milestone = done // 2**30
                                print("VMDK: {:.1f}/{:.1f} GiB".format(done / 2**30, member.size / 2**30), flush=True)
                    if done != member.size:
                        raise RuntimeError("Incomplete VMDK extraction")
                    partial.rename(target)
                    return target
    raise RuntimeError("Expected virtual disk is absent from the archive")


def filesystem(vmdk):
    try:
        from dissect.extfs import ExtFS
        from dissect.hypervisor.disk.vmdk import VMDK
        from dissect.volume.disk import Disk
    except ImportError as error:
        raise RuntimeError("Install extraction dependencies with: python3 -m pip install "
                           "--target build/tools/python -r toolchain/extract-requirements.txt") from error
    disk = Disk(VMDK(vmdk))
    for partition in disk.partitions:
        if partition.type != 0x83:
            continue
        fs = ExtFS(partition.open())
        try:
            fs.get(VENDOR_ROOT)
            return fs
        except Exception:
            continue
    raise RuntimeError("ISE filesystem not found in vendor VM")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ROOT / "Xilinx_ISE_14.7_Win10_14.7_VM_0213_1.zip")
    args = parser.parse_args()
    archive = args.archive.resolve()
    vmdk = extract_vm(archive)
    fs = filesystem(vmdk)
    output = BUILD / "ise/Xilinx/14.7/ISE_DS"
    output.mkdir(parents=True, exist_ok=True)
    total = 0
    copied = 0
    links = 0
    last_report = time.monotonic()

    def copy(node, path):
        nonlocal total, copied, links, last_report
        if node.filetype == stat.S_IFDIR:
            path.mkdir(parents=True, exist_ok=True)
            for child in node.iterdir():
                if child.filename in (".", "..", "lin", "doc"):
                    continue
                if "/" in child.filename or child.filename.startswith(".."):
                    raise RuntimeError("Unexpected vendor filesystem name")
                copy(child, path / child.filename)
        elif node.filetype == stat.S_IFLNK:
            if path.is_symlink():
                if os.readlink(path) == node.link:
                    return
                raise RuntimeError("Existing symlink differs: " + str(path))
            if path.exists():
                raise RuntimeError("Expected symlink, found existing file: " + str(path))
            path.symlink_to(node.link)
            links += 1
        elif node.filetype == stat.S_IFREG:
            if path.is_symlink():
                raise RuntimeError("Refusing to write through existing symlink: " + str(path))
            if not path.exists() or path.stat().st_size != node.size:
                if shutil.disk_usage(output).free < node.size + 512 * 1024 * 1024:
                    raise RuntimeError("Insufficient remaining space for ISE extraction")
                with node.open() as source, path.open("wb") as dest:
                    shutil.copyfileobj(source, dest, 1024 * 1024)
                path.chmod(stat.S_IMODE(node.inode.i_mode))
                copied += 1
            total += node.size
            if time.monotonic() - last_report > 10:
                print("ISE files: {:.1f} MiB, {} copied".format(total / 2**20, copied), flush=True)
                last_report = time.monotonic()

    base = fs.get(VENDOR_ROOT)
    for node in base.iterdir():
        if node.filename in (".", ".."):
            continue
        if node.filetype == stat.S_IFREG:
            copy(node, output / node.filename)
    for component in ("common", "ISE"):
        dest = output / component
        dest.mkdir(exist_ok=True)
        for node in fs.get(VENDOR_ROOT + "/" + component).iterdir():
            if node.filename in (".", ".."):
                continue
            if node.filetype == stat.S_IFDIR and component == "ISE" and node.filename not in KEPT_ISE_DIRS:
                continue
            print("Extracting", component + "/" + node.filename, flush=True)
            copy(node, dest / node.filename)
    license_path = BUILD / "ise/Xilinx/Xilinx.lic"
    license_path.write_bytes(fs.get("/home/ise/.Xilinx/Xilinx.lic").open().read())
    license_path.chmod(0o600)
    fw = output / "ISE/bin/lin64/xusb_emb.hex"
    firmware = BUILD / "firmware/xusb_emb.hex"
    firmware.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fw, firmware)
    ovf = ET.parse(BUILD / "ise-vm/14.7_VM.ovf")
    adapter = next(e for e in ovf.iter() if e.tag.endswith("Adapter") and e.attrib.get("enabled") == "true")
    raw_mac = adapter.attrib["MACAddress"]
    mac = ":".join(raw_mac[i:i+2] for i in range(0, 12, 2)).lower()
    save(ROOT / "config/toolchain.local.json", {"ISE_INSTALL_DIR": str(output),
         "ISE_LICENSE_FILE": str(license_path), "ISE_LICENSE_MAC": mac})
    save(BUILD / "ise/provision.json", {"archive": archive.name, "archive_md5": EXPECTED_MD5,
         "selected_ise_directories": sorted(KEPT_ISE_DIRS), "files_copied": copied, "symlinks_copied": links,
         "regular_file_bytes": total, "firmware_sha256": hashlib.sha256(firmware.read_bytes()).hexdigest()})
    print("Provisioned Spartan-6 CLI tools: {:.1f} MiB".format(total / 2**20), flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        sys.exit(1)
