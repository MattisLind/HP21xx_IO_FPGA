#!/usr/bin/env python3
"""Build a pinned xc3sprog locally, including its Xilinx Platform Cable backend."""
import hashlib
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile

from fpga import BUILD, require_tool, run, write_json

COMMIT = "2bba5381d64b98bca40cb83c9d1d56aaceb4c12f"
SHA256 = "f330894170a66c4cfb833c5afa6b09a218313eec53d2624d3e61ff9386e36262"


def build_fxload():
    source = BUILD / "tools/fxload-src"
    source.mkdir(parents=True, exist_ok=True)
    checksums = {
        "fxload.c": "e74a2dd98407875a96d8410a5b03b51dba3b4c9310a272af9d9939181056c785",
        "ezusb.c": "3b1b69ee07170b3586c84dc96727f338416cadd4285bb9b326c9ad84773f8a06",
        "ezusb.h": "2d0e597bb7a0cac0e8108d08227945914f931f164a459359e2f4f8551f3bd090",
    }
    for name, expected in checksums.items():
        path = source / name
        if not path.exists():
            run([require_tool("curl"), "-L", "--fail", "--silent", "--show-error", "--max-time", "120",
                 "-o", str(path), "https://raw.githubusercontent.com/libusb/libusb/v1.0.29/examples/" + name])
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError("fxload source checksum mismatch: " + str(path))
    (source / "config.h").write_text('#define PRINTF_FORMAT(a,b) __attribute__((format(printf,a,b)))\n')
    flags = subprocess.check_output([require_tool("pkg-config"), "--cflags", "--libs", "libusb-1.0"], text=True)
    run([require_tool("clang"), "-std=c99", "-I" + str(source), str(source / "fxload.c"),
         str(source / "ezusb.c"), "-o", str(BUILD / "tools/fxload")] + shlex.split(flags),
        log=BUILD / "tools/fxload-build.log")
    run([str(BUILD / "tools/fxload"), "-V"], log=BUILD / "tools/fxload-version.log")
    write_json(BUILD / "tools/fxload-source.json", {"repository": "https://github.com/libusb/libusb",
               "tag": "v1.0.29", "source_sha256": checksums})


def main():
    tools = BUILD / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    archive = tools / ("xc3sprog-" + COMMIT + ".tar.gz")
    if not archive.exists():
        run([require_tool("curl"), "-L", "--fail", "--silent", "--show-error", "--max-time", "120",
             "-o", str(archive), "https://codeload.github.com/UweBonnes/xc3sprog/tar.gz/" + COMMIT])
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise RuntimeError("xc3sprog source archive checksum mismatch: " + str(archive))
    source = tools / "xc3sprog-src"
    source.mkdir(exist_ok=True)
    # Extract only regular files/directories inside the archive's top-level root.
    # This works on Python 3.8 as well as newer hosts with tarfile filters.
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            relative = Path(*Path(member.name).parts[1:])
            if ".." in relative.parts or relative.is_absolute():
                raise RuntimeError("Unexpected source archive path")
            dest = source / relative
            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(tar.extractfile(member).read())
            else:
                raise RuntimeError("Unexpected source archive member: " + member.name)
    # Upstream uses bare linker names and omits the libusb-compat include path.
    # Imported pkg-config targets preserve Homebrew's actual paths on arm64 Macs.
    cmake_file = source / "CMakeLists.txt"
    text = cmake_file.read_text()
    text = text.replace("pkg_check_modules(LIBFTDI REQUIRED libftdi1)",
                        "pkg_check_modules(LIBFTDI REQUIRED IMPORTED_TARGET libftdi1)")
    text = text.replace("${LIBFTDI_LIBRARIES}", "PkgConfig::LIBFTDI")
    text = text.replace("pkg_check_modules(LIBUSB_COMPAT REQUIRED libusb)",
                        "pkg_check_modules(LIBUSB_COMPAT REQUIRED IMPORTED_TARGET libusb)\n"
                        "   pkg_check_modules(LIBUSB1 REQUIRED IMPORTED_TARGET libusb-1.0)")
    text = text.replace("include_directories(${LIBUSB_INCLUDE_DIRS})",
                        "include_directories(${LIBUSB_COMPAT_INCLUDE_DIRS} ${LIBUSB1_INCLUDE_DIRS})")
    text = text.replace("set(CONDITIONAL_LIBS ${CONDITIONAL_LIBS} usb usb-1.0)",
                        "set(CONDITIONAL_LIBS PkgConfig::LIBUSB_COMPAT PkgConfig::LIBUSB1)")
    cmake_file.write_text(text)
    # Report read-only Winbond status before indirect flash operations. IO2/IO3
    # are NC on this carrier, so the caller must confirm QE remains set.
    spi_file = source / "progalgspiflash.cpp"
    spi_text = spi_file.read_text()
    marker = '      buf = new byte[pgsize+16];'
    status_code = '''
      if (manf_id == 0xef)
      {
          byte status[3];
          const byte commands[3] = {0x05, 0x35, 0x15};
          for (int index = 0; index < 3; ++index)
          {
              byte request[2] = {commands[index], 0};
              byte response[1] = {0};
              spi_xfer_user1(NULL, 0, 0, request, 1, 1);
              spi_xfer_user1(response, 1, 1, NULL, 0, 0);
              status[index] = bitRevTable[response[0]];
          }
          fprintf(stderr, "Winbond status: SR1=%02x SR2=%02x SR3=%02x\\n",
                  status[0], status[1], status[2]);
      }
'''
    if spi_text.count(marker) != 1:
        raise RuntimeError("Unexpected upstream SPI source; status patch not applied")
    spi_file.write_text(spi_text.replace(marker, marker + status_code))
    env = os.environ.copy()
    env["PATH"] = "/opt/homebrew/bin" + os.pathsep + env.get("PATH", "")
    paths = ["/opt/homebrew/lib/pkgconfig", "/opt/homebrew/share/pkgconfig"]
    env["PKG_CONFIG_PATH"] = os.pathsep.join(paths + [env.get("PKG_CONFIG_PATH", "")])
    output = tools / "xc3sprog-build"
    cmake = require_tool("cmake")
    run([cmake, "-S", str(source), "-B", str(output), "-DUSE_FTD2XX=OFF",
         "-DCMAKE_BUILD_TYPE=Release"], env=env, log=tools / "xc3sprog-configure.log")
    run([cmake, "--build", str(output), "--target", "xc3sprog", "--parallel", "4"],
        env=env, log=tools / "xc3sprog-build.log")
    write_json(tools / "xc3sprog-source.json", {"repository": "https://github.com/UweBonnes/xc3sprog",
               "commit": COMMIT, "archive_sha256": SHA256,
               "build_patch": "pkg-config imported targets; read-only Winbond SR1/SR2/SR3 reporting"})
    print("Programmer built: " + str(output / "xc3sprog"))


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--fxload"]:
            build_fxload()
        elif not sys.argv[1:]:
            main()
        else:
            raise RuntimeError("Usage: build_programmer.py [--fxload]")
    except (OSError, RuntimeError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        sys.exit(1)
