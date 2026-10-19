#!/usr/bin/env python3
"""Host and container entry point for the initial ISE 14.7 bring-up."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
LOCAL_CONFIG = ROOT / "config/toolchain.local.json"
if LOCAL_CONFIG.is_file():
    for key, value in json.loads(LOCAL_CONFIG.read_text()).items():
        if key in {"ISE_IMAGE", "ISE_INSTALL_DIR", "ISE_LICENSE_FILE", "ISE_LICENSE_MAC", "ISE_CONTAINER_LICENSE_FILE"}:
            os.environ.setdefault(key, value)
IMAGE = os.environ.get("ISE_IMAGE", "hp21xx-ise:14.7-runtime")
RUNTIME_IMAGE = os.environ.get("ISE_RUNTIME_IMAGE", "hp21xx-ise:14.7-runtime")
SETTINGS = os.environ.get("ISE_SETTINGS", "/opt/Xilinx/14.7/ISE_DS/settings64.sh")
TOOLS = ("xst", "ngdbuild", "map", "par", "trce", "bitgen")


def find_tool(name):
    found = shutil.which(name)
    candidates = [Path("/opt/homebrew/bin") / name]
    if name == "cmake" and platform.system() == "Darwin" and candidates[0].is_file():
        return str(candidates[0])
    if name == "docker":
        candidates.insert(0, Path("/Applications/Docker.app/Contents/Resources/bin/docker"))
    if name == "xc3sprog":
        candidates.insert(0, BUILD / "tools/xc3sprog-build/xc3sprog")
    if name == "fxload":
        candidates.insert(0, BUILD / "tools/fxload")
    return found or next((str(p) for p in candidates if p.is_file()), None)


def require_tool(name):
    tool = find_tool(name)
    if not tool:
        raise RuntimeError("Missing executable: " + name)
    return tool


def run(command, cwd=ROOT, log=None, env=None):
    print("+ " + shlex.join([str(v) for v in command]), flush=True)
    output = None
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        output = log.open("w")
    try:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, errors="replace")
        for line in process.stdout:
            print(line, end="", flush=True)
            if output:
                output.write(line)
                output.flush()
        code = process.wait()
        if code:
            raise RuntimeError("Command failed (exit {}); see {}".format(code, log or "output above"))
    finally:
        if output:
            output.close()


def docker_env():
    env = os.environ.copy()
    # Docker.app can be installed without its CLI or credential helper on PATH.
    docker_dir = str(Path(require_tool("docker")).parent)
    env["PATH"] = docker_dir + os.pathsep + env.get("PATH", "")
    return env


def image_metadata():
    result = subprocess.run([require_tool("docker"), "image", "inspect", IMAGE,
                             "--format", "{{json .}}"], env=docker_env(),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode:
        raise RuntimeError("Cannot inspect image {}. Start Docker and run make runtime-image, "
                           "or set ISE_IMAGE to an existing ISE image.\n{}".format(IMAGE, result.stderr.strip()))
    data = json.loads(result.stdout)
    if data["Architecture"] != "amd64" or data["Os"] != "linux":
        raise RuntimeError("ISE requires a linux/amd64 image, got {}/{}".format(data["Os"], data["Architecture"]))
    return {key: data[key] for key in ("Id", "RepoDigests", "Architecture", "Os")}


def docker_run(arguments, with_ise=True):
    metadata = image_metadata()
    command = [require_tool("docker"), "run", "--rm", "--pull=never",
               "--platform", "linux/amd64", "--network", "bridge" if with_ise and os.environ.get("ISE_LICENSE_MAC") else "none",
               "--mount", "type=bind,source={},target=/work".format(ROOT),
               "--workdir", "/work", "--entrypoint", "/bin/bash"]
    if with_ise:
        install = os.environ.get("ISE_INSTALL_DIR")
        if install:
            path = Path(install).expanduser().resolve()
            if not (path / "settings64.sh").is_file():
                raise RuntimeError("ISE_INSTALL_DIR must name the installed ISE_DS directory containing settings64.sh")
            command += ["--mount", "type=bind,source={},target=/opt/Xilinx/14.7/ISE_DS,readonly".format(path)]
        license_file = os.environ.get("ISE_LICENSE_FILE")
        if license_file:
            path = Path(license_file).expanduser().resolve()
            if not path.is_file():
                raise RuntimeError("ISE_LICENSE_FILE does not exist")
            command += ["--mount", "type=bind,source={},target=/run/ise-license.lic,readonly".format(path),
                        "--env", "XILINXD_LICENSE_FILE=/run/ise-license.lic"]
        # Optional for an existing image whose license is already installed.
        if os.environ.get("ISE_CONTAINER_LICENSE_FILE"):
            if license_file:
                raise RuntimeError("Use only one of ISE_LICENSE_FILE and ISE_CONTAINER_LICENSE_FILE")
            command += ["--env", "XILINXD_LICENSE_FILE=" + os.environ["ISE_CONTAINER_LICENSE_FILE"]]
        if os.environ.get("ISE_LICENSE_MAC"):
            mac = os.environ["ISE_LICENSE_MAC"]
            if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", mac):
                raise RuntimeError("ISE_LICENSE_MAC must be a MAC address for your licensed installation")
            command += ["--mac-address", mac]
        command += ["--env", "HP21XX_ISE_SETTINGS=" + SETTINGS]
        setup = ('set -eo pipefail; '
                 'if [ ! -f "$HP21XX_ISE_SETTINGS" ]; then '
                 'echo "ISE 14.7 is missing. Set ISE_INSTALL_DIR to a Linux ISE_DS installation, '
                 'or ISE_IMAGE to an installed ISE image. See toolchain/README.md." >&2; exit 2; fi; '
                 'source "$HP21XX_ISE_SETTINGS" "$(dirname "$HP21XX_ISE_SETTINGS")" >/dev/null; exec "$@"')
    else:
        setup = 'set -eo pipefail; exec "$@"'
    command += [IMAGE, "-c", setup, "ise-run"] + arguments
    return command, metadata


def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def read_board(filename):
    path = Path(filename)
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        raise RuntimeError("Create config/board.local.json from config/board.example.json; "
                           "fill in the actual part, clock pin, and I/O standard")
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise RuntimeError("Board configuration must be a JSON object")
    patterns = {"part": r"xc6slx9-[123](?:l)?-tqg144", "clock_pin": r"P(?:[1-9]|[1-9][0-9]|1[0-3][0-9]|14[0-4])",
                "led_pin": r"P(?:[1-9]|[1-9][0-9]|1[0-3][0-9]|14[0-4])", "iostandard": r"LVCMOS(?:12|15|18|25|33)|LVTTL"}
    for key, pattern in patterns.items():
        if not isinstance(data.get(key), str) or not re.fullmatch(pattern, data[key]):
            raise RuntimeError("Set a valid {} in {}".format(key, path))
    if data.get("clock_hz") != 50000000:
        raise RuntimeError("This board design requires clock_hz = 50000000")
    if not isinstance(data.get("led_active_low"), bool):
        raise RuntimeError("led_active_low must be true or false")
    if data["clock_pin"] == data["led_pin"]:
        raise RuntimeError("Clock and LED pins must differ")
    return data


def fingerprint(board):
    digest = hashlib.sha256(json.dumps(board, sort_keys=True).encode())
    for path in (ROOT / "fpga/blink/blink.v", Path(__file__)):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def check_timing(path):
    report = path.read_text(errors="replace")
    summaries = re.findall(r"Timing errors:\s*(\d+)\s+Score:\s*(\d+)", report)
    clock = re.search(r'Timing constraint:\s*TS_clk\s*=\s*PERIOD\b(.*?)(?=Timing constraint:|Timing summary:|\Z)',
                      report, re.S)
    if not summaries or any(int(errors) or int(score) for errors, score in summaries):
        raise RuntimeError("Timing report missing a passing summary or contains violations: " + str(path))
    if not clock or not re.search(r"\b[1-9][0-9]* (?:items?|paths?) analyzed", clock.group(1)):
        raise RuntimeError("No analyzed paths for TS_clk in timing report: " + str(path))
    header = clock.group(1).split(";", 1)[0]
    if not re.search(r"\b20(?:\.0+)?\s*ns\b", header, re.I):
        raise RuntimeError("TS_clk is not constrained to 20 ns")
    print("PASS: TS_clk has analyzed paths and the timing summary has zero errors and score")


def ise_flow(mode):
    """Executed inside a single container, after settings64.sh is sourced."""
    for tool in TOOLS:
        print(tool + ": " + require_tool(tool))
    if mode == "check":
        run(["xst", "-help"], log=BUILD / "toolchain/xst-help.log")
        return
    out = BUILD / mode
    out.mkdir(parents=True, exist_ok=True)
    board = json.loads((out / "request.json").read_text())
    part = board["part"]
    ucf = 'NET "clk" TNM_NET = "clk";\nTIMESPEC "TS_clk" = PERIOD "clk" 20 ns HIGH 50%;\n'
    if mode == "blink":
        ucf += ('NET "clk" LOC = "{clock_pin}" | IOSTANDARD = {iostandard};\n'
                'NET "led" LOC = "{led_pin}" | IOSTANDARD = {iostandard} | DRIVE = 8 | SLEW = SLOW;\n').format(**board)
    (out / "blink.ucf").write_text(ucf)
    active_low = int(board.get("led_active_low", False))
    (out / "top.v").write_text('module top(input wire clk, output wire led);\n'
                               'blink #(.ACTIVE_LOW({})) u_blink(.clk(clk), .led(led));\nendmodule\n'.format(active_low))
    (out / "blink.prj").write_text('verilog work "../../fpga/blink/blink.v"\nverilog work "top.v"\n')
    (out / "blink.xst").write_text("run\n-ifn blink.prj\n-ifmt mixed\n-ofn blink.ngc\n-ofmt NGC\n"
                                 "-p {}\n-top top\n-opt_mode Speed\n-opt_level 1\n".format(part))
    steps = [
        ("xst", ["xst", "-ifn", "blink.xst", "-ofn", "blink.syr"]),
        ("ngdbuild", ["ngdbuild", "-p", part, "-uc", "blink.ucf", "blink.ngc", "blink.ngd"]),
        ("map", ["map", "-w", "-p", part, "-o", "blink_map.ncd", "blink.ngd", "blink.pcf"]),
        ("par", ["par", "-w", "blink_map.ncd", "blink.ncd", "blink.pcf"]),
        ("trce", ["trce", "-v", "10", "-u", "10", "blink.ncd", "blink.pcf", "-o", "blink.twr"]),
    ]
    for name, command in steps:
        run(command, cwd=out, log=out / (name + ".log"))
    check_timing(out / "blink.twr")
    if mode == "blink":
        run(["bitgen", "-w", "-g", "UnusedPin:Pullnone", "blink.ncd", "blink.bit", "blink.pcf"],
            cwd=out, log=out / "bitgen.log")
    else:
        # Vendor bitgen.usg: -j means "Don't create bit file". Exercise its
        # configuration DRC without making an automatically placed design loadable.
        run(["bitgen", "-j", "-w", "-g", "UnusedPin:Pullnone", "blink.ncd", "blink.drc", "blink.pcf"],
            cwd=out, log=out / "bitgen.log")
        if (out / "blink.bit").exists():
            raise RuntimeError("Smoke test unexpectedly generated a bitstream")
    print("PASS: ISE {} flow completed".format(mode))


def build(mode, board_file):
    board = read_board(board_file) if mode == "blink" else {"part": "xc6slx9-2-tqg144"}
    out = BUILD / mode
    out.mkdir(parents=True, exist_ok=True)
    # Invalidate evidence before a new attempt, including any stale bitstream.
    for name in ("success.json", "blink.bit"):
        (out / name).unlink(missing_ok=True)
    write_json(out / "request.json", board)
    command, image = docker_run(["python3", "scripts/fpga.py", "ise-flow", "--mode", mode])
    metadata = {"started_utc": timestamp(), "mode": mode, "image": image,
                "board": board, "input_sha256": fingerprint(board)}
    write_json(out / "build.json", metadata)
    run(command, log=out / "container.log", env=docker_env())
    metadata["completed_utc"] = timestamp()
    if mode == "blink":
        metadata["bitstream_sha256"] = hashlib.sha256((out / "blink.bit").read_bytes()).hexdigest()
    write_json(out / "success.json", metadata)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["doctor", "runtime-image", "runtime-check", "toolchain-check",
                                          "sim", "smoke", "blink", "jtag-detect", "program", "ise-flow",
                                          "usb-scan", "cable-firmware", "firmware-extract", "ise-image"])
    parser.add_argument("--board", default="config/board.local.json")
    parser.add_argument("--cable", default="xpc")
    parser.add_argument("--programmer", choices=["xc3sprog", "openfpgaloader"], default="xc3sprog")
    parser.add_argument("--mode", choices=["check", "smoke", "blink"])
    parser.add_argument("--firmware", default="")
    args = parser.parse_args()
    if args.action == "runtime-image":
        run([require_tool("docker"), "build", "--platform", "linux/amd64", "-t", RUNTIME_IMAGE,
             "-f", "toolchain/Dockerfile", "toolchain"],
            log=BUILD / "toolchain/image-build.log", env=docker_env())
    elif args.action == "ise-image":
        if not (BUILD / "ise/Xilinx/14.7/ISE_DS/settings64.sh").is_file():
            raise RuntimeError("Run make provision-ise before building the full image")
        full_image = os.environ.get("ISE_FULL_IMAGE", "hp21xx-ise:14.7")
        run([require_tool("docker"), "build", "--platform", "linux/amd64", "-t", full_image,
             "--build-arg", "RUNTIME_IMAGE=" + RUNTIME_IMAGE, "-f", str(ROOT / "toolchain/Dockerfile.ise"),
             str(BUILD / "ise")], log=BUILD / "toolchain/ise-image-build.log", env=docker_env())
        config = json.loads(LOCAL_CONFIG.read_text())
        write_json(LOCAL_CONFIG, {"ISE_IMAGE": full_image, "ISE_LICENSE_MAC": config["ISE_LICENSE_MAC"],
                   "ISE_CONTAINER_LICENSE_FILE": "/opt/Xilinx/Xilinx.lic"})
        print("Default ISE image configured: " + full_image)
    elif args.action == "doctor":
        print("Host: {} {}".format(platform.system(), platform.machine()))
        tools = {}
        for tool in ("docker", "make", "iverilog", "vvp", "openFPGALoader", "xc3sprog"):
            tools[tool] = find_tool(tool)
            print("{}: {}".format(tool, tools[tool] or "not installed"))
        print("Free project disk space: {:.1f} GiB".format(shutil.disk_usage(ROOT).free / 2**30))
        print("ISE_IMAGE: " + IMAGE)
        print("ISE_INSTALL_DIR: " + os.environ.get("ISE_INSTALL_DIR", "not configured"))
        run([require_tool("docker"), "version"], env=docker_env())
        image = image_metadata()
        print(json.dumps(image, indent=2))
        write_json(BUILD / "toolchain/doctor.json", {"tested_utc": timestamp(),
                   "host_os": platform.system(), "host_arch": platform.machine(),
                   "tools": tools, "image": image,
                   "ise_install_configured": bool(os.environ.get("ISE_INSTALL_DIR"))})
    elif args.action == "runtime-check":
        out = BUILD / "toolchain"
        marker = out / "runtime-ok.txt"
        marker.unlink(missing_ok=True)
        check = ('test "$(uname -m)" = x86_64; test "$(dpkg --print-architecture)" = amd64; '
                 'python3 --version; python3 scripts/fpga.py --help >/dev/null; make --version; '
                 'printf "linux/amd64 runtime and writable project mount OK\\n" > build/toolchain/runtime-ok.txt; '
                 'cat build/toolchain/runtime-ok.txt')
        command, image = docker_run(["bash", "-euc", check], with_ise=False)
        run(command, log=out / "runtime-check.log", env=docker_env())
        if not marker.is_file():
            raise RuntimeError("Container output was not visible on the host")
        write_json(out / "runtime.json", {"tested_utc": timestamp(), "image": image})
    elif args.action == "toolchain-check":
        command, _ = docker_run(["python3", "scripts/fpga.py", "ise-flow", "--mode", "check"])
        run(command, log=BUILD / "toolchain/ise-check.log", env=docker_env())
    elif args.action == "sim":
        out = BUILD / "sim"
        out.mkdir(parents=True, exist_ok=True)
        run([require_tool("iverilog"), "-g2012", "-Wall", "-s", "tb_blink", "-o", str(out / "blink.vvp"),
             "fpga/blink/blink.v", "fpga/blink/tb_blink.sv"], log=out / "compile.log")
        run([require_tool("vvp"), str(out / "blink.vvp")], log=out / "simulation.log")
    elif args.action == "usb-scan":
        if platform.system() != "Darwin":
            raise RuntimeError("usb-scan currently uses macOS system_profiler")
        devices = []
        def visit(value):
            if isinstance(value, dict):
                if "USBDeviceKeyVendorID" in value and "USBDeviceKeyProductID" in value:
                    devices.append({"name": value.get("_name", "?"),
                                    "vid": value["USBDeviceKeyVendorID"], "pid": value["USBDeviceKeyProductID"]})
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        profile = subprocess.check_output(["/usr/sbin/system_profiler", "SPUSBHostDataType", "-json"], text=True)
        visit(json.loads(profile))
        print(json.dumps(devices, indent=2))
        write_json(BUILD / "toolchain/usb-scan.json", devices)
    elif args.action == "cable-firmware":
        firmware = Path(args.firmware).expanduser()
        if not args.firmware or not firmware.is_file():
            raise RuntimeError("Set CABLE_FIRMWARE to the xusb_emb.hex file for the observed 03fd:000d device")
        firmware = firmware.resolve()
        run([require_tool("fxload"), "-v", "-t", "fx2", "-d", "03fd:000d", "-i", str(firmware)],
            log=BUILD / "toolchain/cable-firmware.log")
        write_json(BUILD / "toolchain/cable-firmware.json", {"loaded_utc": timestamp(),
                   "initial_usb_id": "03fd:000d", "firmware_name": firmware.name,
                   "firmware_sha256": hashlib.sha256(firmware.read_bytes()).hexdigest(), "destination": "RAM"})
    elif args.action == "firmware-extract":
        destination = BUILD / "firmware/xusb_emb.hex"
        source_path = "/opt/Xilinx/14.7/ISE_DS/ISE/bin/lin64/xusb_emb.hex"
        if os.environ.get("ISE_INSTALL_DIR"):
            path = Path(os.environ["ISE_INSTALL_DIR"]).expanduser() / "ISE/bin/lin64/xusb_emb.hex"
            if not path.is_file():
                raise RuntimeError("Firmware missing in the supplied installation: " + str(path))
            content = path.read_bytes()
            provenance = {"installation_file": str(path.resolve())}
        else:
            provenance = {"image": image_metadata(), "container_path": source_path}
            command = [require_tool("docker"), "run", "--rm", "--pull=never", "--platform", "linux/amd64",
                       "--network", "none", "--entrypoint", "/bin/cat", IMAGE, source_path]
            result = subprocess.run(command, env=docker_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode:
                raise RuntimeError("Cannot extract firmware from {}. This requires a full ISE installation/image; "
                                   "the dependency-only runtime contains no vendor files.\n{}".format(
                                       IMAGE, result.stderr.decode(errors="replace").strip()))
            content = result.stdout
        if not content.startswith(b":") or b":00000001FF" not in content.upper():
            raise RuntimeError("Extracted firmware does not look like an Intel HEX file")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        provenance["firmware_sha256"] = hashlib.sha256(content).hexdigest()
        write_json(BUILD / "firmware/source.json", provenance)
        print("Extracted firmware to " + str(destination))
    elif args.action in ("smoke", "blink"):
        build(args.action, args.board)
    elif args.action == "ise-flow":
        if not args.mode:
            parser.error("ise-flow requires --mode")
        ise_flow(args.mode)
    elif args.action in ("jtag-detect", "program"):
        if not args.cable:
            raise RuntimeError("Specify CABLE=<name> for the selected programmer")
        executable = "xc3sprog" if args.programmer == "xc3sprog" else "openFPGALoader"
        command = [require_tool(executable), "-c", args.cable]
        if args.action == "jtag-detect":
            command += ["-j"] if args.programmer == "xc3sprog" else ["--detect"]
        else:
            board = read_board(args.board)
            success = BUILD / "blink/success.json"
            bitstream = BUILD / "blink/blink.bit"
            if not success.is_file() or not bitstream.is_file():
                raise RuntimeError("Run make blink successfully before programming")
            metadata = json.loads(success.read_text())
            if metadata["input_sha256"] != fingerprint(board):
                raise RuntimeError("Sources or board configuration changed; rebuild with make blink")
            if metadata["bitstream_sha256"] != hashlib.sha256(bitstream.read_bytes()).hexdigest():
                raise RuntimeError("Bitstream changed since the successful build; rebuild with make blink")
            command += [str(bitstream)]  # Volatile SRAM configuration; no flash write.
        run(command, log=BUILD / "toolchain" / (args.action + ".log"))
        if args.action == "jtag-detect":
            log = (BUILD / "toolchain/jtag-detect.log").read_text()
            if "No JTAG Chain found" in log:
                raise RuntimeError("Cable opened, but no JTAG chain was found. Check FPGA power, Vref, and JTAG wiring.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        sys.exit(1)
