// Carrier image with the wired STM32 multiplexed FSMC interface enabled.
// HP ports are physical FPGA pins: receivers and drivers both invert.
// External driver input bias must be fitted before HP bus connection.
`timescale 1ns/1ps
module hp13210a_board (
  input wire  clk,
  input wire  crs,
  output wire  prl,
  output wire  flgl,
  input wire  sfc,
  output wire  irql,
  input wire  clf,
  input wire  ien,
  input wire  stf,
  input wire  iak,
  input wire  t3,
  output wire  skf,
  input wire  scm_l,
  input wire  scl_l,
  input wire  iog,
  input wire  popio,
  input wire  iob16_or_bios_n,
  output wire  srq,
  input wire  ioo,
  input wire  clc,
  input wire  stc,
  input wire  prh,
  input wire  ioi,
  input wire  sfs,
  output wire  irqh,
  input wire  scl_h,
  input wire  scm_h,
  input wire [15:0] iob_out,
  output wire [15:0] iob_in,
  input wire  sir,
  input wire  enf,
  output wire  flgh,
  input wire  run,
  input wire  pon,
  input wire  bioo_n,
  input wire  sfsb_or_bioi_n,
  input wire  edt,
  output wire  run_drive,
  output wire  flash_cs_n,
  output wire  led,
  input wire stm32_fsmc_nadv,
  input wire stm32_fsmc_nwe,
  input wire stm32_fsmc_noe,
  inout wire [15:0] stm32_fsmc_ad
  );
  assign flash_cs_n = 1'b1;
  assign run_drive = 1'b1;
  // Hold HP outputs inactive until the controller startup reset has drained.
  reg [7:0] release_pipe = 0;
  always @(posedge clk) release_pipe <= {release_pipe[6:0], 1'b1};
  wire outputs_enabled = &release_pipe;
  wire  core_prl;
  assign prl = outputs_enabled ? ~core_prl : prh;
  wire  core_flgl;
  assign flgl = outputs_enabled ? ~core_flgl : 1'b1;
  wire  core_irql;
  assign irql = outputs_enabled ? ~core_irql : 1'b1;
  wire  core_skf;
  assign skf = outputs_enabled ? ~core_skf : 1'b1;
  wire  core_srq;
  assign srq = outputs_enabled ? ~core_srq : 1'b1;
  wire  core_irqh;
  assign irqh = outputs_enabled ? ~core_irqh : 1'b1;
  wire [15:0] core_iob_in;
  assign iob_in = outputs_enabled ? ~core_iob_in : 16'hffff;
  wire  core_flgh;
  assign flgh = outputs_enabled ? ~core_flgh : 1'b1;
  hp13210a_fpga #(.ENABLE_STM32(1)) controller (
    .clk(clk),
    .reset(1'b0),
    .crs(~crs),
    .prl(core_prl),
    .flgl(core_flgl),
    .sfc(~sfc),
    .irql(core_irql),
    .clf(~clf),
    .ien(~ien),
    .stf(~stf),
    .iak(~iak),
    .t3(~t3),
    .skf(core_skf),
    .scm_l(~scm_l),
    .scl_l(~scl_l),
    .iog(~iog),
    .popio(~popio),
    .iob16_or_bios_n(~iob16_or_bios_n),
    .srq(core_srq),
    .ioo(~ioo),
    .clc(~clc),
    .stc(~stc),
    .prh(~prh),
    .ioi(~ioi),
    .sfs(~sfs),
    .irqh(core_irqh),
    .scl_h(~scl_h),
    .scm_h(~scm_h),
    .iob_out(~iob_out),
    .iob_in(core_iob_in),
    .sir(~sir),
    .enf(~enf),
    .flgh(core_flgh),
    .run(~run),
    .edt(~edt),
    .pon(~pon),
    .bioo_n(~bioo_n),
    .sfsb_or_bioi_n(~sfsb_or_bioi_n),
    .stm32_fsmc_ne(1'b0),
    .stm32_fsmc_nadv(stm32_fsmc_nadv),
    .stm32_fsmc_nwe(stm32_fsmc_nwe),
    .stm32_fsmc_noe(stm32_fsmc_noe),
    .stm32_irq(),
    .stm32_drq(),
    .stm32_fsmc_ad(stm32_fsmc_ad)
  );
  // Monitor both select codes after undoing receiver inversion. The LED
  // module synchronizes these asynchronous inputs separately from the core.
  activity_led status_led (.clk(clk), .iog(~iog),
    .scm_l(~scm_l), .scl_l(~scl_l), .scm_h(~scm_h), .scl_h(~scl_h), .led(led));
endmodule
