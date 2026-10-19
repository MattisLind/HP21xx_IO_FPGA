// Logical-level boundary; hp13210a_board adapts the inverting HP circuitry.
// Default build leaves the STM32 interface inactive until firmware is available.
`timescale 1ns/1ps
module hp13210a_fpga #(parameter ENABLE_STM32 = 0) (
  input wire  clk,
  input wire  reset,
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
  input wire  edt,
  input wire  pon,
  input wire  bioo_n,
  input wire  sfsb_or_bioi_n,
  input wire  stm32_fsmc_ne,
  input wire  stm32_fsmc_nadv,
  input wire  stm32_fsmc_nwe,
  input wire  stm32_fsmc_noe,
  output wire  stm32_irq,
  output wire  stm32_drq,
  inout wire [15:0] stm32_fsmc_ad
);

  // These synchronizers reduce metastability risk, but do not establish a
  // multi-bit transfer protocol. Data must remain stable around its strobe.
  (* ASYNC_REG = "TRUE", SHREG_EXTRACT = "NO" *)
  reg [42:0] hp_meta = 0, hp_sync = 0;
  (* ASYNC_REG = "TRUE", SHREG_EXTRACT = "NO" *)
  reg [3:0] fsmc_meta = 4'hf, fsmc_sync = 4'hf;
  reg [15:0] ad_meta = 0, ad_sync = 0;
  (* ASYNC_REG = "TRUE", SHREG_EXTRACT = "NO" *)
  reg reset_meta = 0, reset_sync = 0;
  reg [3:0] startup_reset = 4'hf;
  wire core_reset = |startup_reset;
  always @(posedge clk) begin
    hp_meta <= {crs, sfc, clf, ien, stf, iak, t3, scm_l, scl_l, iog, popio, iob16_or_bios_n, ioo, clc, stc, prh, ioi, sfs, scl_h, scm_h, iob_out, sir, enf, run, edt, pon, bioo_n, sfsb_or_bioi_n};
    hp_sync <= hp_meta;
    fsmc_meta <= {stm32_fsmc_ne, stm32_fsmc_nadv, stm32_fsmc_nwe, stm32_fsmc_noe};
    fsmc_sync <= fsmc_meta;
    ad_meta <= stm32_fsmc_ad;
    ad_sync <= ad_meta;
    reset_meta <= reset;
    reset_sync <= reset_meta;
    if (reset_sync) startup_reset <= 4'hf;
    else startup_reset <= {startup_reset[2:0], 1'b0};
  end

  wire  s_crs;
  wire  s_sfc;
  wire  s_clf;
  wire  s_ien;
  wire  s_stf;
  wire  s_iak;
  wire  s_t3;
  wire  s_scm_l;
  wire  s_scl_l;
  wire  s_iog;
  wire  s_popio;
  wire  s_iob16_or_bios_n;
  wire  s_ioo;
  wire  s_clc;
  wire  s_stc;
  wire  s_prh;
  wire  s_ioi;
  wire  s_sfs;
  wire  s_scl_h;
  wire  s_scm_h;
  wire [15:0] s_iob_out;
  wire  s_sir;
  wire  s_enf;
  wire  s_run;
  wire  s_edt;
  wire  s_pon;
  wire  s_bioo_n;
  wire  s_sfsb_or_bioi_n;
  assign {s_crs, s_sfc, s_clf, s_ien, s_stf, s_iak, s_t3, s_scm_l, s_scl_l, s_iog, s_popio, s_iob16_or_bios_n, s_ioo, s_clc, s_stc, s_prh, s_ioi, s_sfs, s_scl_h, s_scm_h, s_iob_out, s_sir, s_enf, s_run, s_edt, s_pon, s_bioo_n, s_sfsb_or_bioi_n} = hp_sync;
  wire [15:0] ad_out;
  wire ad_oe;
  // Immediate release on raw bus controls prevents a delayed read enable
  // from driving AD into the following address/write phase.
  wire read_window = ENABLE_STM32 && !stm32_fsmc_ne && stm32_fsmc_nadv &&
                     !stm32_fsmc_noe && stm32_fsmc_nwe;
  assign stm32_fsmc_ad = (read_window && ad_oe && !core_reset) ? ad_out : 16'hzzzz;

  hp13210a_core core (
    .clk(clk),
    .reset(core_reset),
    .crs(s_crs),
    .prl(prl),
    .flgl(flgl),
    .sfc(s_sfc),
    .irql(irql),
    .clf(s_clf),
    .ien(s_ien),
    .stf(s_stf),
    .iak(s_iak),
    .t3(s_t3),
    .skf(skf),
    .scm_l(s_scm_l),
    .scl_l(s_scl_l),
    .iog(s_iog),
    .popio(s_popio),
    .iob16_or_bios_n(s_iob16_or_bios_n),
    .srq(srq),
    .ioo(s_ioo),
    .clc(s_clc),
    .stc(s_stc),
    .prh(s_prh),
    .ioi(s_ioi),
    .sfs(s_sfs),
    .irqh(irqh),
    .scl_h(s_scl_h),
    .scm_h(s_scm_h),
    .iob_out(s_iob_out),
    .iob_in(iob_in),
    .sir(s_sir),
    .enf(s_enf),
    .flgh(flgh),
    .run(s_run),
    .edt(s_edt),
    .pon(s_pon),
    .bioo_n(s_bioo_n),
    .sfsb_or_bioi_n(s_sfsb_or_bioi_n),
    .stm32_fsmc_ne(ENABLE_STM32 ? fsmc_sync[3] : 1'b1),
    .stm32_fsmc_nadv(ENABLE_STM32 ? fsmc_sync[2] : 1'b1),
    .stm32_fsmc_nwe(ENABLE_STM32 ? fsmc_sync[1] : 1'b1),
    .stm32_fsmc_noe(ENABLE_STM32 ? fsmc_sync[0] : 1'b1),
    .stm32_irq(stm32_irq),
    .stm32_drq(stm32_drq),
    .stm32_fsmc_ad_in(ENABLE_STM32 ? ad_sync : 16'h0000),
    .stm32_fsmc_ad_out(ad_out),
    .stm32_fsmc_ad_oe(ad_oe)
  );
endmodule
