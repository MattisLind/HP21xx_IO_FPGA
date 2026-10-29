#!/usr/bin/env python3
"""Prepare the original disk diagnostic with measured transfer waits.

Uses production RTL and the SV disk daemon, NOT the ARM/C++ backend. Images
stay in memory. WORD records expose normal and intentional delayed responses.
Runtime: RESPONSE_US, SETUP_US, DATA_START_US, POLL_NS, SERVICE_NS,
STOP_STEP (default33). No disk persistence or hardware programming.
CPU_SCALE and FAST_MEM/SECTION1_ONLY come from hp2116_seek_timing.py.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from hp2116_seek_timing import ROOT, replace

IMAGE = 'verilator/verilator@sha256:a5b73e2fce0b2c483396f3800940f33b6faa802331a061c21694dd27b7352120'


def run(out):
    mount=['docker','run','--rm','--user',f'{os.getuid()}:{os.getgid()}',
           '-v',f'{ROOT}:{ROOT}']
    with (out/'compile.log').open('w') as log:
        subprocess.run(mount+['-w',str(out),'--entrypoint','verilator',IMAGE,
            '-Wno-fatal','-Wno-UNUSEDSIGNAL','--no-sched-zero-delay','--sv',
            '--timing','--binary','-j','2','tb_hp2116.sv','hp2116_cpu.sv',
            'hp12531c.sv','hp12597a.sv','hp12566b.sv','hp13210a.sv',
            'hp12539c.sv','hp12845a.sv','--top-module','tb_hp2116'],
            stdout=log,stderr=subprocess.STDOUT,check=True)
    checkpoint=ROOT/'build/hp2116-seek-validation/recovery/section1.hex'
    cases=[('normal-and-overrun',15,20,200,33,120),
           ('normal-and-overrun-stall8',15,20,8000,33,120),
           ('normal-and-check',15,20,200,35,160),
           ('normal-and-check-stall8',15,20,8000,35,160),
           ('read-overrun',15,20,200,36,160),
           ('read-overrun-stall8',15,20,8000,36,160),
           ('write-cylinder-boundary',15,20,200,47,450),
           ('write-cylinder-boundary-stall8',15,20,8000,47,450),
           ('normal-slower-cpu-stall8',31,20,8000,28,100),
           ('control-six-us',15,6,8000,28,40)]
    def case(settings):
        name,scale,response,poll,stop,limit=settings
        folder=out/'cases'/name
        folder.mkdir(parents=True,exist_ok=True)
        options=['+DSN=151302',f'+FAST_MEM={checkpoint}','+SECTION1_ONLY',
            '+SEEK_US=500',f'+CPU_SCALE={scale}',f'+RESPONSE_US={response}',
            f'+POLL_NS={poll}','+DATA_START_US=100',f'+STOP_STEP={stop}',
            f'+MAX_MS={limit}',
            '+LOADFILE='+str(ROOT/'hp2116_verilog/diagnostics/24296-60001_DSN000200_DIAGNOSTIC_CONFIGURATOR.abin')]
        with (folder/'run.log').open('w') as log:
            result=subprocess.run(mount+['-w',str(folder),'--entrypoint','stdbuf',
                IMAGE,'-oL',str(out/'obj_dir/Vtb_hp2116')]+options,
                stdout=log,stderr=subprocess.STDOUT)
        text=(folder/'run.log').read_text()
        if response==6:
            passed='TIMEOUT step=24 dir=W position=1\n' in text and 'LATE step=24 ' in text
        else:
            passed=f'PASS: transfer diagnostic through step {stop-1}' in text
            if stop>=33: passed=passed and 'LATE step=32 position=2 ' in text
            passed=passed and 'FAIL:' not in text
        passed=passed and result.returncode==0
        print(f'{name}: {"PASS" if passed else "FAIL"}',flush=True)
        return {'case':name,'pass':passed,'options':options,
            'expected_six_us_failure':response==6,
            'log_sha256':hashlib.sha256((folder/'run.log').read_bytes()).hexdigest()}
    paths=[Path(__file__).resolve(),ROOT/'scripts/hp2116_seek_timing.py',
           ROOT/'fpga/hp13210/hp13210a_core.v',checkpoint]
    before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(case,cases))
    assert before=={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    receipt={'image':IMAGE,'hardware_programmed':False,
        'backend':'SV timing model, not ARM/C++ firmware','sources':before,
        'generated':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob('*.sv'))},
        'results':results}
    (out/'acceptance.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if not all(r['pass'] for r in results):raise SystemExit('Transfer timing regression failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT/'build/transfer-timing/cpu')
    parser.add_argument('--run',action='store_true')
    args = parser.parse_args()
    out = args.out.resolve()
    subprocess.run([sys.executable, str(ROOT/'scripts/hp2116_seek_timing.py'),
                    '--out', str(out)], check=True)
    path = out/'tb_hp2116.sv'
    tb = path.read_text()
    tb = replace(tb, 'module tb_hp2116;', '''module tb_hp2116;
integer transfer_response_us=20, transfer_setup_us=100, transfer_poll_ns=200;
integer transfer_service_ns=0, transfer_stop_step=33;
integer transfer_start_us=100;
initial begin
  void'($value$plusargs("RESPONSE_US=%d",transfer_response_us));
  void'($value$plusargs("SETUP_US=%d",transfer_setup_us));
  void'($value$plusargs("POLL_NS=%d",transfer_poll_ns));
  void'($value$plusargs("SERVICE_NS=%d",transfer_service_ns));
  void'($value$plusargs("STOP_STEP=%d",transfer_stop_step));
  void'($value$plusargs("DATA_START_US=%d",transfer_start_us));
end
always @(negedge cpu.run_ff) begin
  if (timing_configured && cpu.TR==16'o102001) begin
    $display("FAIL: diagnostic error P=%06o A=%06o step=%0d",cpu.P,cpu.A,timing_last_step);
    $finish;
  end
end
''')
    tb = replace(tb, '    timing_last_step = mem_wdata;', '''    timing_last_step = mem_wdata;
    if (mem_wdata==transfer_stop_step) begin
      $display("PASS: transfer diagnostic through step %0d",transfer_stop_step-1);
      $finish;
    end''')
    # Model software service time independently of CPU speed and FSMC strobes.
    start = tb.index('task automatic stm32_write_cylinder();')
    end = tb.index('// Kodkommentar: Läs en diskimage-fil',start)
    tb = tb[:start] + '''
task automatic transfer_wait(input time budget, output logic got_word);
  logic [15:0] csr;
  time deadline;
  begin
    got_word=0;
    deadline=$time+budget;
    while ($time<deadline && !got_word) begin
      stm32_fsmc_read16(STM32_REG_CSR,csr);
      got_word=csr[6];
      if (!got_word && $time<deadline) begin
        if ($time+transfer_poll_ns*1ns<deadline) #(transfer_poll_ns*1ns);
        else #(deadline-$time);
      end
    end
  end
endtask

task automatic transfer_close(input time last_response, input integer position);
  logic [15:0] csr, ignored;
  time closing;
  integer words, remaining;
  bit reported;
  begin
    words=position%128;
    remaining=words ? 128-words : 0;
    closing=last_response+transfer_response_us*1us+remaining*6400ns;
    reported=0;
    while ($time<closing) begin
      stm32_fsmc_read16(STM32_REG_CSR,csr);
      if (csr[6]) begin
        stm32_fsmc_read16(STM32_REG_7900_DATA,ignored);
        $display("LATE step=%0d position=%0d gap_ns=%0d",timing_last_step,position,$time-last_response);
        if (!reported) begin
          stm32_fsmc_write16(STM32_REG_7900_SET_STATUS,{selected_drive[1:0],STATUS_OVERRUN});
          reported=1;
        end
      end
      #(transfer_poll_ns*1ns);
    end
  end
endtask

task automatic stm32_write_cylinder();
  logic [15:0] data;
  logic got_word;
  integer off, position;
  time last_response, waited;
  begin
    word_count=0; eoc_flag=0; position=0;
    if (transfer_start_us>0) #(transfer_start_us*1us);
    last_response=$time;
    while (1) begin
      waited=$time;
      transfer_wait((position ? transfer_response_us : transfer_setup_us)*1us,got_word);
      if (!got_word) begin
        $display("TIMEOUT step=%0d dir=W position=%0d",timing_last_step,position);
        if (position) begin
          transfer_close(last_response,position);
          if (word_count!=0) disk_fill_rest_of_sector(int'(word_count));
        end
        break;
      end
      stm32_fsmc_read16(STM32_REG_7900_DATA,data);
      $display("WORD step=%0d dir=W position=%0d gap_ns=%0d wait_ns=%0d data=%04h",timing_last_step,position,$time-last_response,$time-waited,data);
      if (eoc_flag) begin
        stm32_fsmc_write16(STM32_REG_7900_SET_STATUS,{selected_drive[1:0],STATUS_END_OF_CYLINDER});
        break;
      end
      off=disk_byte_offset(rar_cylinder,rar_head,rar_sector)+word_count*2;
      disk_image[selected_drive][off]=data[7:0];
      disk_image[selected_drive][off+1]=data[15:8];
      position++;
      calculate_rar("WRITE");
      if (transfer_service_ns>0) #(transfer_service_ns*1ns);
      last_response=$time;
    end
  end
endtask

task automatic stm32_read_cylinder();
  logic [15:0] data;
  logic got_word;
  integer off, position;
  time staged;
  begin
    word_count=0; eoc_flag=0; position=0;
    if (transfer_start_us>0) #(transfer_start_us*1us);
    while (!eoc_flag) begin
      off=disk_byte_offset(rar_cylinder,rar_head,rar_sector)+word_count*2;
      data={disk_image[selected_drive][off+1],disk_image[selected_drive][off]};
      stm32_fsmc_write16(STM32_REG_7900_DATA,data);
      staged=$time;
      position++;
      calculate_rar("READ");
      transfer_wait(transfer_response_us*1us,got_word);
      if (!got_word) begin
        $display("TIMEOUT step=%0d dir=R position=%0d",timing_last_step,position);
        transfer_close(staged,position);
        break;
      end
      $display("WORD step=%0d dir=R position=%0d gap_ns=%0d data=%04h",timing_last_step,position,$time-staged,data);
      if (transfer_service_ns>0) #(transfer_service_ns*1ns);
      if (eoc_flag) stm32_fsmc_write16(STM32_REG_7900_SET_STATUS,{selected_drive[1:0],STATUS_END_OF_CYLINDER});
    end
  end
endtask

''' + tb[end:]
    start = tb.index("          4'h6: begin",tb.index('task automatic stm32_read_cylinder'))
    end = tb.index("          4'h9: begin",start)
    tb = tb[:start]+'''          4'h6: begin
            word_count=0; eoc_flag=0;
            stm32_get_seek_address();
            stm32_wait_csr_bit_set(6);
            stm32_fsmc_read16(STM32_REG_7900_DATA,indata);
            num_sectors=indata[5:0];
            got_word=1;
            if (transfer_start_us>0 && num_sectors!=0) #(transfer_start_us*1us);
            for (i=0; i<int'(num_sectors); i++) begin
              if (eoc_flag) begin
                stm32_fsmc_write16(STM32_REG_7900_SET_STATUS,{selected_drive[1:0],STATUS_END_OF_CYLINDER});
                break;
              end
              for (j=0; j<128; j++) begin
                if (got_word) begin
                  indata={disk_image[selected_drive][disk_byte_offset(rar_cylinder,rar_head,rar_sector)+word_count*2+1],
                          disk_image[selected_drive][disk_byte_offset(rar_cylinder,rar_head,rar_sector)+word_count*2]};
                  stm32_fsmc_write16(STM32_REG_7900_DATA,indata);
                  transfer_wait(transfer_response_us*1us,got_word);
                end
                // DMA exhaustion stops the optional stream, not CHECK.
                calculate_rar("CHECK DATA");
              end
            end
            stm32_fsmc_write16(STM32_REG_7900_ATTENTION,16'h0000);
          end

''' + tb[end:]
    path.write_text(tb)
    print(out)
    if args.run:run(out)


if __name__=='__main__':
    main()
