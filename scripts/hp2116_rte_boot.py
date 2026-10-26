#!/usr/bin/env python3
"""Prepare an isolated RTE-II boot/FMGR/DL regression with production RTL.

--run compiles with the local Verilator Docker image, then tests 500/4000 us
seeks. A PASS requires boot, FMGR, both DL directory headers and its next prompt.
Disk writes stay in memory; acceptance.json records inputs and results.
The pinned reference sources and disk image are never modified.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from hp2116_seek_timing import ROOT, replace

IMAGE = 'verilator/verilator@sha256:a5b73e2fce0b2c483396f3800940f33b6faa802331a061c21694dd27b7352120'
PASS = 'PASS: RTE-II boot, FMGR DL SYS/AUX directories, return to prompt'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(out, args):
    mount = ['docker', 'run', '--rm', '--user', f'{os.getuid()}:{os.getgid()}',
             '-v', f'{ROOT}:{ROOT}', '-w', str(out)]
    with (out / 'compile.log').open('w') as log:
        subprocess.run(mount + ['--entrypoint', 'verilator', IMAGE,
            '-Wno-fatal', '-Wno-UNUSEDSIGNAL', '--no-sched-zero-delay', '--sv',
            '--timing', '--binary', '-j', '2', 'tb_hp2116.sv', 'hp2116_cpu.sv',
            'hp12531c.sv', 'hp12597a.sv', 'hp12566b.sv', 'hp13210a.sv',
            'hp12539c.sv', 'hp12845a.sv', '--top-module', 'tb_hp2116'],
            stdout=log, stderr=subprocess.STDOUT, check=True)
    sources = [ROOT / 'scripts/hp2116_rte_boot.py', ROOT / 'scripts/hp2116_seek_timing.py',
               ROOT / 'fpga/hp13210/hp13210a_core.v',
               ROOT / 'hp2116_verilog/RTE_MH.disc', ROOT / 'hp2116_verilog/mh_boot.abs.new']
    receipt = {'image': IMAGE, 'hardware_programmed': False, 'results': [],
               'sources': {str(p.relative_to(ROOT)): sha256(p) for p in sources},
               'generated': {p.name: sha256(p) for p in sorted(out.glob('*.sv'))}}
    def run_case(seek_us):
        name = f'seek{seek_us}-capture{args.capture_us}'
        log_path = out / f'{name}.log'
        with log_path.open('w') as log:
            result = subprocess.run(mount + ['--entrypoint', 'stdbuf', IMAGE, '-oL',
                './obj_dir/Vtb_hp2116', '+RTE=YES', '+LOADFILE=mh_boot.abs.new',
                '+DISK0=RTE_MH.disc', f'+SEEK_US={seek_us}', f'+CAPTURE_US={args.capture_us}',
                f'+RTE_REPLY_US={args.reply_us}', f'+MAX_MS={args.max_ms}'],
                stdout=log, stderr=subprocess.STDOUT)
        passed = result.returncode == 0 and PASS.encode() in log_path.read_bytes()
        record = {'case': name, 'seek_us': seek_us,
            'capture_us': args.capture_us, 'reply_us': args.reply_us,
            'max_ms': args.max_ms, 'pass': passed, 'log_sha256': sha256(log_path)}
        print(f'{name}: {"PASS" if passed else "FAIL"}', flush=True)
        return record
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipt['results'] = list(pool.map(run_case, args.seek_us))
    for path in sources:
        assert sha256(path) == receipt['sources'][str(path.relative_to(ROOT))], path
    (out / 'acceptance.json').write_text(json.dumps(receipt, indent=2) + '\n')
    if not all(r['pass'] for r in receipt['results']):
        raise SystemExit('RTE regression failed; see logs and acceptance.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/hp2116-rte-boot')
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--seek-us', type=int, nargs='+', default=[500, 4000])
    parser.add_argument('--capture-us', type=int, default=0)
    parser.add_argument('--reply-us', type=int, default=100000,
                        help='cap on prompt reply delay in us; default preserves reference 20/100 ms')
    parser.add_argument('--max-ms', type=int, default=1000)
    args = parser.parse_args()
    out = args.out.resolve()
    subprocess.run([sys.executable, str(ROOT / 'scripts/hp2116_seek_timing.py'),
                    '--out', str(out)], check=True)
    for name in ('mh_boot.abs.new', 'RTE_MH.disc'):
        shutil.copy2(ROOT / 'hp2116_verilog' / name, out / name)
    path = out / 'tb_hp2116.sv'
    tb = path.read_text()
    tb = replace(tb, 'module tb_hp2116;', '''module tb_hp2116;
bit rte_dl_sent = 0, rte_started = 0;
integer rte_reply_us = 100000;
int rte_sys_labels = 0, rte_aux_labels = 0, rte_directory_headers = 0;
string rte_output_line = "";
initial void'($value$plusargs("RTE_REPLY_US=%d", rte_reply_us));
always @(posedge cpu.run_ff) rte_started = 1;
always @(negedge cpu.run_ff)
    if (rte_started) $fatal(1, "Unexpected RTE CPU halt P=%06o TR=%06o", cpu.P, cpu.TR);
initial begin : rte_directory_check
    logic [7:0] raw;
    byte ch;
    forever begin
        uart_recv_byte(uart_tx, raw);
        ch = {1'b0, raw[6:0]};
        if (rte_dl_sent) begin
            if (ch == 10) begin
                if (rte_output_line.len() > 0) begin
                    for (int i = 0; i + 8 <= rte_output_line.len(); i++) begin
                        if (rte_output_line.substr(i, i+7) == "ILAB=SYS") rte_sys_labels++;
                        if (rte_output_line.substr(i, i+7) == "ILAB=AUX") rte_aux_labels++;
                    end
                    for (int i = 0; i + 13 <= rte_output_line.len(); i++)
                        if (rte_output_line.substr(0,3) == "NAME" &&
                            rte_output_line.substr(i, i+12) == "TYPE #BLKS/LU") rte_directory_headers++;
                end
                rte_output_line = "";
            end else if (ch != 13) rte_output_line = {rte_output_line, ch};
            if (ch == ":" && rte_output_line == ":" &&
                rte_sys_labels > 0 && rte_aux_labels > 0 && rte_directory_headers >= 2) begin
                $display("PASS: RTE-II boot, FMGR DL SYS/AUX directories, return to prompt");
                $finish;
            end
        end
    end
end
''')
    # Arm before sending DL so even its first output byte is checked.
    tb = replace(tb, '        uart_send_string(tb_rx, response, inter_char_delay);', '''        if (response == "DL\\r") rte_dl_sent = 1;
        uart_send_string(tb_rx, response, inter_char_delay);''')
    tb = replace(tb, '            #(after_match_delay);',
                 '            #(after_match_delay < rte_reply_us * 1us ? after_match_delay : rte_reply_us * 1us);')
    tb = replace(tb, '$display("TIMING LIMIT P=%06o", cpu.P);\n  $finish;',
                 '$fatal(1, "RTE boot timeout P=%06o A=%06o B=%06o", cpu.P, cpu.A, cpu.B);')
    tb = replace(tb, '''                $error("UART string mismatch''', '''                $fatal(1, "UART string mismatch''')
    path.write_text(tb)
    if args.run:
        run(out, args)


if __name__ == '__main__':
    main()
