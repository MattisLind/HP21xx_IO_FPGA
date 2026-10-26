#!/usr/bin/env python3
"""Prepare an isolated, instrumented copy of the pinned HP2116 testbench.

Run Verilator in the output directory; the reference submodule is never edited.
Runtime knobs: +SEEK_US=4000 +CAPTURE_US=0 +CPU_SCALE=1 +MAX_MS=3000.
CPU_SCALE is the divider terminal count (reference default 1), applied at
the diagnostic's initial HLT 74 after configuration has finished.
The current production controller core is used without experimental overrides.
+STOP_AFTER_CYL1 ends after step 2 succeeds
and step 21 advances to its cylinder-1 seek; this is not a full-diagnostic pass.
+STOP_AFTER_SEEK_STEPS stops on entry to section 1 step 24, after steps 21-23.
The initial HLT 74 saves configured.hex. +FAST_MEM=<path> replays that memory
at the same diagnostic entry with reset peripherals, for fast repeated tests.
"""
from pathlib import Path
import argparse
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/hp2116-seek-timing"


def replace(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new)


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=OUT)
    OUT = parser.parse_args().out.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    for source in (ROOT / "hp2116_verilog").glob("*.sv"):
        shutil.copy2(source, OUT / source.name)
    diagnostics = OUT / "diagnostics"
    if not diagnostics.exists():
        diagnostics.symlink_to(ROOT / "hp2116_verilog/diagnostics", target_is_directory=True)
    p = OUT / "hp2116_cpu.sv"
    cpu = p.read_text()
    # Use the controller currently on the board. The reference's overlapping
    # procedural tristate assignments are not a reliable FSMC read mux.
    core = (ROOT / "fpga/hp13210/hp13210a_core.v").read_text()
    (OUT / "hp13210a.sv").write_text(core.replace("module hp13210a_core", "module hp13210a"))
    cpu = replace(cpu, "hp13210a disk7900 (", """wire [15:0] timing_ad_out;
wire timing_ad_oe;
assign stm32_fsmc_ad = timing_ad_oe ? timing_ad_out : 16'hzzzz;
hp13210a #(.RESET_NOT_READY(4'h0)) disk7900 (
  .reset(1'b0),""")
    cpu = replace(cpu, "  .stm32_fsmc_ad(stm32_fsmc_ad),", """  .stm32_fsmc_ad_in(stm32_fsmc_ad),
  .stm32_fsmc_ad_out(timing_ad_out),
  .stm32_fsmc_ad_oe(timing_ad_oe),""")
    cpu = replace(cpu, "assign scale_clock_enable = (clk_scale == 5'd1);", """
integer timing_cpu_scale = 1;
integer timing_requested_scale = 1;
initial begin
  void'($value$plusargs("CPU_SCALE=%d", timing_requested_scale));
  if (timing_requested_scale < 1 || timing_requested_scale > 31) $fatal(1, "CPU_SCALE must be 1..31");
  wait (P == 15'o012307 && !run_ff);
  timing_cpu_scale = timing_requested_scale;
  $display("CPU_SCALE ns=%0d terminal_count=%0d", $time, timing_cpu_scale);
end
assign scale_clock_enable = (clk_scale == timing_cpu_scale);
""")
    p.write_text(cpu)
    p = OUT / "tb_hp2116.sv"
    tb = p.read_text()
    tb = replace(tb, "module tb_hp2116;", """module tb_hp2116;
integer timing_seek_us = 4000, timing_capture_us = 0, timing_max_ms = 3000;
string timing_boot_memory;
reg [15:0] timing_last_step = 16'hffff;
reg timing_configured = 0;
initial begin
  void'($value$plusargs("FAST_MEM=%s", timing_boot_memory));
  void'($value$plusargs("SEEK_US=%d", timing_seek_us));
  void'($value$plusargs("CAPTURE_US=%d", timing_capture_us));
  void'($value$plusargs("MAX_MS=%d", timing_max_ms));
  $display("TIMING seek_us=%0d capture_us=%0d", timing_seek_us, timing_capture_us);
  #(timing_max_ms * 1ms);
  $display("TIMING LIMIT P=%06o", cpu.P);
  $finish;
end
always @(negedge clk) begin
  if (timing_configured && cpu.run_ff && mem_we && mem_addr == (mem[15'o000131] & 15'o001777) &&
      mem_wdata != timing_last_step) begin
    timing_last_step = mem_wdata;
    $display("DIAG_STEP ns=%0d step=%0d P=%06o", $time, mem_wdata, cpu.P);
    if ($test$plusargs("STOP_AFTER_SEEK_STEPS") && mem_wdata == 24) begin
      $display("PASS: DSN151302 section 1 steps 1, 2, 21, 22, 23; entering step 24");
      $finish;
    end
  end
end
always @(negedge cpu.run_ff) begin
  if (cpu.P == 15'o012307 && cpu.TR == 16'o102074) begin
    $writememh("configured.hex", mem);
    timing_configured = 1;
    $display("CHECKPOINT: configured.hex P=012307 A=%06o B=%06o", cpu.A, cpu.B);
  end
end
// Log only transitions, since each HP strobe lasts several FPGA clocks.
always @(posedge cpu.ioo or posedge cpu.ioi or posedge cpu.stc or posedge cpu.clc)
  if (rst_n && (cpu.disk7900.csel || cpu.disk7900.dsel))
    $display("BUS ns=%0d P=%06o TR=%06o csel=%b dsel=%b OTA=%b LIA=%b STC=%b CLC=%b out=%06o attention=%h",
      $time, cpu.P, cpu.TR, cpu.disk7900.csel, cpu.disk7900.dsel,
      cpu.ioo, cpu.ioi, cpu.stc, cpu.clc, cpu.iob_out,
      cpu.disk7900.attention_input_register);
always @(posedge cpu.disk7900.set_irq_ff) begin
  $display("RAR_DONE ns=%0d P=%06o", $time, cpu.P);
  if ($test$plusargs("STOP_AFTER_CYL1") && cpu.disk7900.cylinder_address == 1) begin
    $display("TIMING REACHED CYLINDER 1: step 2 passed, step 21 has advanced; not a full diagnostic pass");
    $finish;
  end
end
always @(posedge cpu.disk7900.command_channel_flag_ff)
  if (rst_n) $display("CC_FLAG ns=%0d P=%06o attention=%h", $time, cpu.P, cpu.disk7900.attention_input_register);
""")
    tb = replace(tb, "#(4ms);", "#(timing_seek_us * 1us);")
    tb = replace(tb, "initial begin\n    if (!$value$plusargs(\"RTE=%s\", RTE))", """initial begin : timing_uart_config
    string skipped_boot;
    void'($value$plusargs("DSN=%s", DSN));
    if ($value$plusargs("FAST_MEM=%s", skipped_boot)) disable timing_uart_config;
    if (!$value$plusargs("RTE=%s", RTE))""")
    tb = replace(tb, "    load_hp21xx_abs(loadfile, /*do_fill_halt=*/1'b1);", """    load_hp21xx_abs(loadfile, /*do_fill_halt=*/1'b1);
    if (timing_boot_memory != "") begin
      $readmemh(timing_boot_memory, mem);
      if (mem[15'o000126] != 16'o151302) $fatal(1, "FAST_MEM is not DSN151302 memory");
      timing_configured = 1;
    end""")
    tb = replace(tb, "    // Enable single-cycle mode and do two phase-steps", """    if (timing_boot_memory != "") begin
      sw = 16'o102306; pulse_btn(load_a_btn);
      sw = 16'o001750; pulse_btn(load_b_btn);
      sw = 16'o012307; pulse_btn(load_addr_btn);
      sw = 0;
    end
    // Enable single-cycle mode and do two phase-steps""")
    tb = replace(tb, "        stm32_handle_irq();", """        $display("IRQ_SEEN ns=%0d", $time);
        if (timing_capture_us > 0) #(timing_capture_us * 1us);
        stm32_handle_irq();""")
    tb = replace(tb, "        command = indata[15:12];", """        $display("CAPTURE ns=%0d command=%04h", $time, indata);
        command = indata[15:12];""")
    tb = replace(tb, "        // seek is done", """        $display("SEEK_DEADLINE ns=%0d drive=%0d", $time, seek_drive);
        // seek is done""")
    tb = replace(tb, "        if (~seek_aborted[seek_drive]) begin", """        $display("SEEK_END ns=%0d command=%04h aborted=%b", $time, indata, seek_aborted[seek_drive]);
        if (~seek_aborted[seek_drive]) begin""")
    # The experiment never persists or modifies disk images.
    tb = replace(tb, "        disk_save_image(d);", '        $display("TIMING disk%0d persistence disabled", d);')
    tb = replace(tb, """      @(posedge clk);   // The DUT can sample the button here
      @(negedge clk);   // Wait until after the sampling edge
      @(posedge clk);   // The DUT can sample the button here
      @(negedge clk);   // Wait until after the sampling edge      """, """      @(negedge clk);
      while (!cpu.scale_clock_enable) @(negedge clk);
      @(posedge clk);
      @(negedge clk);""")
    p.write_text(tb)
    print(OUT)


if __name__ == "__main__":
    main()
