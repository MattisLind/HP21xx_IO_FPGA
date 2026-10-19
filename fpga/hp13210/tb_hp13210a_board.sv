`timescale 1ns/1ps
module tb_hp13210a_board;
  reg  clk = 0;
  reg  crs = 0;
  wire  prl;
  wire  flgl;
  reg  sfc = 0;
  wire  irql;
  reg  clf = 0;
  reg  ien = 0;
  reg  stf = 0;
  reg  iak = 0;
  reg  t3 = 0;
  wire  skf;
  reg  scm_l = 0;
  reg  scl_l = 0;
  reg  iog = 0;
  reg  popio = 0;
  reg  iob16_or_bios_n = 0;
  wire  srq;
  reg  ioo = 0;
  reg  clc = 0;
  reg  stc = 0;
  reg  prh = 0;
  reg  ioi = 0;
  reg  sfs = 0;
  wire  irqh;
  reg  scl_h = 0;
  reg  scm_h = 0;
  reg [15:0] iob_out = 0;
  wire [15:0] iob_in;
  reg  sir = 0;
  reg  enf = 0;
  wire  flgh;
  reg  run = 0;
  reg  pon = 0;
  reg  bioo_n = 0;
  reg  sfsb_or_bioi_n = 0;
  reg  edt = 0;
  wire  run_drive;
  wire  flash_cs_n;
  wire  led;
  reg stm32_fsmc_nadv=1, stm32_fsmc_nwe=1, stm32_fsmc_noe=1;
  tri [15:0] stm32_fsmc_ad;
  reg host_oe=0;
  reg [15:0] host_ad=0;
  assign stm32_fsmc_ad = host_oe ? host_ad : 16'hzzzz;
  always #10 clk = ~clk;
  hp13210a_board dut (
.clk(clk),
.crs(~crs),
.prl(prl),
.flgl(flgl),
.sfc(~sfc),
.irql(irql),
.clf(~clf),
.ien(~ien),
.stf(~stf),
.iak(~iak),
.t3(~t3),
.skf(skf),
.scm_l(~scm_l),
.scl_l(~scl_l),
.iog(~iog),
.popio(~popio),
.iob16_or_bios_n(~iob16_or_bios_n),
.srq(srq),
.ioo(~ioo),
.clc(~clc),
.stc(~stc),
.prh(~prh),
.ioi(~ioi),
.sfs(~sfs),
.irqh(irqh),
.scl_h(~scl_h),
.scm_h(~scm_h),
.iob_out(~iob_out),
.iob_in(iob_in),
.sir(~sir),
.enf(~enf),
.flgh(flgh),
.run(~run),
.pon(~pon),
.bioo_n(~bioo_n),
.sfsb_or_bioi_n(~sfsb_or_bioi_n),
.edt(~edt),
.run_drive(run_drive),
.flash_cs_n(flash_cs_n),
.led(led),
.stm32_fsmc_nadv(stm32_fsmc_nadv),
.stm32_fsmc_nwe(stm32_fsmc_nwe),
.stm32_fsmc_noe(stm32_fsmc_noe),
.stm32_fsmc_ad(stm32_fsmc_ad)
  );
  initial begin
    prh=1; pon=1; bioo_n=1; sfsb_or_bioi_n=1; iob16_or_bios_n=1;
    #7;
    if (flash_cs_n !== 1 || run_drive !== 1) $fatal(1, "Carrier idle controls");
    if ({flgl,irql,skf,srq,irqh,flgh,iob_in} !== {6'b111111,16'hffff})
      $fatal(1, "Startup outputs must leave HP signals inactive");
    #240;
    if (prl !== 0) $fatal(1, "Available priority must pass through inverting driver");
    if (stm32_fsmc_ad !== 16'hzzzz) $fatal(1, "Idle STM32 bus must release");
    // AD address 0xE is CPU byte offset 0x1C in 16-bit multiplexed mode.
    host_oe=1; host_ad=16'h000e;
    stm32_fsmc_nadv=0; #95; stm32_fsmc_nadv=1; #95;
    host_ad=16'ha55a; #95; stm32_fsmc_nwe=0; #381;
    stm32_fsmc_nwe=1; #95; host_oe=0; #95;
    stm32_fsmc_noe=0; #381;
    if (stm32_fsmc_ad !== 16'ha55a) $fatal(1, "Wired backend scratchpad readback");
    stm32_fsmc_noe=1; #1;
    if (stm32_fsmc_ad !== 16'hzzzz) $fatal(1, "STM32 bus release after read");
    #199;
    iog=1; scm_l=1; scl_l=1; #173;
    if (led !== 1) $fatal(1, "Physical lower select must trigger activity LED");
    enf=1; #173; enf=0; #173;
    if (srq !== 0) $fatal(1, "Board data flag after ENF");
    clf=1; #173; clf=0; #173;
    if (srq !== 1) $fatal(1, "Board data flag after CLF");
    stf=1; #173; stf=0; #173; enf=1; #173; enf=0; #173;
    sfs=1; #173;
    if (skf !== 0) $fatal(1, "Board skip on flag");
    edt=1; #173; edt=0; #173;
    if (skf !== 0) $fatal(1, "Unused EDT input must not change the flag");
    if (flash_cs_n !== 1 || run_drive !== 1) $fatal(1, "Reserved controls remain idle");
    $display("PASS: physical HP inversion, priority, flags, skip, RUN idle, EDT input, wired FSMC scratchpad");
    $finish;
  end
endmodule
