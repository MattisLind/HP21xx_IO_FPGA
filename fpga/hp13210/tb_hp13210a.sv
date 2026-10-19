`timescale 1ns/1ps
module tb_hp13210a;
  parameter ENABLE_STM32 = 0;
  parameter HP_PULSE_NS = 173;
  parameter START_PHASE_NS = 0;
  parameter OMIT_NE = 0;
  reg  clk = 0;
  reg  reset = 0;
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
  reg  edt = 0;
  reg  pon = 0;
  reg  bioo_n = 0;
  reg  sfsb_or_bioi_n = 0;
  reg  stm32_fsmc_ne = 0;
  reg  stm32_fsmc_nadv = 0;
  reg  stm32_fsmc_nwe = 0;
  reg  stm32_fsmc_noe = 0;
  wire  stm32_irq;
  wire  stm32_drq;
  wire [15:0] stm32_fsmc_ad;
  always #10 clk = ~clk;
  reg [15:0] host_ad = 0;
  reg host_oe = 0;
  assign stm32_fsmc_ad = host_oe ? host_ad : 16'hzzzz;
  hp13210a_fpga #(.ENABLE_STM32(ENABLE_STM32)) dut (
    .clk(clk),
    .reset(reset),
    .crs(crs),
    .prl(prl),
    .flgl(flgl),
    .sfc(sfc),
    .irql(irql),
    .clf(clf),
    .ien(ien),
    .stf(stf),
    .iak(iak),
    .t3(t3),
    .skf(skf),
    .scm_l(scm_l),
    .scl_l(scl_l),
    .iog(iog),
    .popio(popio),
    .iob16_or_bios_n(iob16_or_bios_n),
    .srq(srq),
    .ioo(ioo),
    .clc(clc),
    .stc(stc),
    .prh(prh),
    .ioi(ioi),
    .sfs(sfs),
    .irqh(irqh),
    .scl_h(scl_h),
    .scm_h(scm_h),
    .iob_out(iob_out),
    .iob_in(iob_in),
    .sir(sir),
    .enf(enf),
    .flgh(flgh),
    .run(run),
    .edt(edt),
    .pon(pon),
    .bioo_n(bioo_n),
    .sfsb_or_bioi_n(sfsb_or_bioi_n),
    .stm32_fsmc_ne(stm32_fsmc_ne),
    .stm32_fsmc_nadv(stm32_fsmc_nadv),
    .stm32_fsmc_nwe(stm32_fsmc_nwe),
    .stm32_fsmc_noe(stm32_fsmc_noe),
    .stm32_irq(stm32_irq),
    .stm32_drq(stm32_drq),
    .stm32_fsmc_ad(stm32_fsmc_ad)
  );

  task check(input logic condition, input string message);
    if (condition !== 1'b1) $fatal(1, "%s at %0t", message, $time);
  endtask

  task select_channel(input bit command_channel);
    iog = 1;
    scm_l = !command_channel; scl_l = !command_channel;
    scm_h = command_channel; scl_h = command_channel;
    #157;
  endtask

  task pulse(input integer signal_number);
    case (signal_number)
      0: stf=1; 1: clf=1; 2: enf=1; 3: stc=1; 4: clc=1;
      5: sir=1; 6: iak=1; 7: popio=1; 8: crs=1;
    endcase
    #(HP_PULSE_NS);
    case (signal_number)
      0: stf=0; 1: clf=0; 2: enf=0; 3: stc=0; 4: clc=0;
      5: sir=0; 6: iak=0; 7: popio=0; 8: crs=0;
    endcase
    #191;
  endtask

  task hp_write(input bit command_channel, input logic [15:0] value);
    select_channel(command_channel);
    iob_out=value; #137;
    ioo=1; #(HP_PULSE_NS); ioo=0; #191;
  endtask

  task hp_read(input bit command_channel, input logic [15:0] expected_value);
    select_channel(command_channel);
    ioi=1; #(HP_PULSE_NS);
    check(iob_in === expected_value, $sformatf("HP input expected %04x got %04x", expected_value, iob_in));
    ioi=0; #191;
    check(iob_in === 0, "Unstrobed HP input must be zero");
  endtask

  task address_phase(input logic [15:0] address);
    stm32_fsmc_ne=0; stm32_fsmc_nwe=1; stm32_fsmc_noe=1;
    host_oe=1; host_ad=address; #181;
    stm32_fsmc_nadv=0; #179;
    stm32_fsmc_nadv=1; #183;
  endtask

  task backend_write(input logic [15:0] address, input logic [15:0] value);
    address_phase(address);
    host_ad=value; #177;
    stm32_fsmc_nwe=0; #181;
    check(stm32_fsmc_ad === value, "FPGA must not drive during an FSMC write");
    stm32_fsmc_nwe=1; #179;
    stm32_fsmc_ne=OMIT_NE ? 0 : 1; host_oe=0; #183;
  endtask

  task backend_read(input logic [15:0] address, output logic [15:0] value);
    address_phase(address);
    host_oe=0; #177;
    stm32_fsmc_noe=0; #241;
    value=stm32_fsmc_ad;
    stm32_fsmc_noe=1; #1;
    check(stm32_fsmc_ad === 16'hzzzz, "FSMC read bus must release immediately");
    #178; stm32_fsmc_ne=OMIT_NE ? 0 : 1; #183;
  endtask

  logic [15:0] value;
  integer test_bit;
  initial begin
    #200000;
    $fatal(1, "Controller test timeout");
  end

  initial begin
    prh=1; pon=1; run=1; bioo_n=1; sfsb_or_bioi_n=1;
    iob16_or_bios_n=1;
    stm32_fsmc_ne=OMIT_NE ? 0 : 1; stm32_fsmc_nadv=1;
    stm32_fsmc_nwe=1; stm32_fsmc_noe=1;
    #(207+START_PHASE_NS);
    check({irqh,irql,flgh,flgl,srq,stm32_irq,stm32_drq} === 0, "Known inactive power-on outputs");
    check(prl === 1, "Power-on priority passes");
    check(stm32_fsmc_ad === 16'hzzzz, "Idle FSMC bus must float");

    select_channel(0); sfc=1; #157;
    check(skf === 1, "Preset data flag starts clear");
    sfc=0; sfs=1; #157; check(skf === 0, "SFS before ENF");
    pulse(2); check(skf === 1 && srq === 1, "ENF transfers preset flag buffer");
    pulse(1); check(skf === 0 && srq === 0, "CLF clears data flag and buffer");
    pulse(0); check(skf === 0, "STF sets buffer, not flag directly");
    pulse(2); check(skf === 1, "STF then ENF sets data flag");
    clf=1; stf=1; enf=1; #(HP_PULSE_NS);
    check(srq === 0, "CLF has priority over STF and ENF");
    clf=0; stf=0; enf=0; #191;

    // Neither channel is selected: broadcast strobes cannot set flags.
    iog=0; #157; pulse(0); pulse(2);
    check(srq === 0 && skf === 0, "Unselected STF and skip isolation");
    select_channel(0); pulse(2); check(srq === 0, "Unselected STF did not set buffer");
    sfs=0;

    // Command flag and priority / interrupt chain, independently of firmware.
    select_channel(1); pulse(1); pulse(0); pulse(2);
    sfs=1; #157; check(skf === 1, "Command channel flag"); sfs=0;
    ien=0; pulse(3); check(prl === 1, "IEN disabled passes priority");
    pulse(5); check(irqh === 0, "IEN gates interrupt");
    ien=1; prh=0; #157; pulse(5);
    check(irqh === 0 && prl === 0, "Higher priority blocks interrupt");
    prh=1; #157; check(prl === 0, "Command request claims priority");
    pulse(5); check(irqh === 1 && flgh === 1, "SIR latches higher-channel interrupt");
    check(irql === 0 && flgl === 0, "Reference lower interrupt outputs remain inactive");
    pulse(6); pulse(2); pulse(5);
    check(irqh === 0, "IAK clears flag buffer and ENF releases interrupt");
    pulse(4); check(prl === 1, "CLC clears command control");
    pulse(0); pulse(2); pulse(3); pulse(8);
    check(prl === 1, "CRS clears command control");

    // With no backend, status check still works and disks report not-ready.
    pulse(7); pulse(2);
    hp_write(1, 16'h0000); pulse(3); pulse(2);
    hp_read(0, 16'h0040);
    hp_read(1, 16'h0000);
    check(stm32_irq === 0 && stm32_drq === 0, "Backend interrupts start disabled");

    // A disk read command stays pending: no fabricated disk data/completion.
    select_channel(0); pulse(1);
    hp_write(1, 16'h2001); pulse(3); pulse(2);
    #997;
    check(srq === 0, "No backend means no read-data completion");

    if (ENABLE_STM32) begin
      backend_read(16'h000e, value);
      check(value === 0, "Scratchpad starts at zero");
      backend_write(16'h000e, 16'ha55a);
      backend_read(16'h000e, value);
      check(value === 16'ha55a, "Scratchpad alternating bits");
      backend_write(16'h000e, 16'h5aa5);
      backend_read(16'h000e, value);
      check(value === 16'h5aa5, "Scratchpad inverse alternating bits");
      for (test_bit=0; test_bit<16; test_bit=test_bit+1) begin
        backend_write(16'h000e, 16'h0001 << test_bit);
        backend_read(16'h000e, value);
        check(value === (16'h0001 << test_bit), "Scratchpad walking one");
        backend_write(16'h000e, ~(16'h0001 << test_bit));
        backend_read(16'h000e, value);
        check(value === ~(16'h0001 << test_bit), "Scratchpad walking zero");
      end
      backend_write(16'h000e, 16'h0000);
      backend_read(16'h000e, value);
      check(value === 0, "Scratchpad all zero");
      backend_write(16'h000e, 16'hffff);
      backend_read(16'h000e, value);
      check(value === 16'hffff, "Scratchpad all one");
      backend_read(16'h0002, value);
      check(value === 16'h2001, "FSMC command/status read mux");
      backend_read(16'h0000, value);
      check(value[7] === 1, "Command IRQ pending in CSR");
      backend_read(16'h0000, value);
      check(value[7] === 0, "CSR read acknowledges command IRQ");
      backend_write(16'h0000, 16'h0300);
      hp_write(1, 16'h1001); pulse(3);
      check(stm32_irq === 1, "Enabled command interrupt reaches backend");
      backend_read(16'h0000, value);
      check(stm32_irq === 0, "Backend CSR read releases command interrupt");

      hp_write(0, 16'ha55a);
      backend_read(16'h0004, value);
      check(value === 16'ha55a, "HP output word reaches backend");
      backend_write(16'h0004, 16'h1234);
      hp_read(0, 16'h1234);

      backend_write(16'h0006, 16'h0005);
      backend_write(16'h0006, 16'h000a);
      hp_read(1, 16'h000f);
      // Set then clear drive-1 not-ready and set data-protect via status masks.
      backend_write(16'h0008, 16'h40a0);
      backend_write(16'h000a, 16'h4020);
      hp_write(1, 16'h0001); pulse(3); pulse(2);
      hp_read(0, 16'h0400);

      hp_write(1, 16'h3002); pulse(3);
      hp_write(0, 16'h007b); pulse(3);
      hp_write(0, 16'h0215); pulse(3);
      backend_read(16'h000c, value);
      check(value === 16'h3dd5, "Two-word seek record retains cylinder/head/sector");

      pulse(7);
      backend_read(16'h000e, value);
      check(value === 16'hffff, "HP POPIO leaves transport scratchpad intact");
      hp_read(1, 16'h0000);
      hp_write(1, 16'h2000); pulse(3);
      check(stm32_irq === 1, "POPIO preserves explicitly enabled backend IRQs");
    end else begin
      backend_write(16'h0000, 16'h0300);
      backend_write(16'h0004, 16'h1234);
      backend_read(16'h0000, value);
      check(value === 16'hzzzz, "Disabled backend never drives AD");
      check(stm32_irq === 0, "Disabled backend cannot enable IRQs");
      hp_read(0, 16'h0040);
    end

    reset=1; #199; reset=0; #211;
    check(stm32_irq === 0 && irqh === 0 && srq === 0, "Board reset clears all state");
    if (ENABLE_STM32) begin
      backend_read(16'h000e, value);
      check(value === 0, "Board reset clears scratchpad");
    end
    $display("PASS: 50 MHz HP protocol, backend=%0d pulse=%0d ns phase=%0d ns omit_NE=%0d", ENABLE_STM32, HP_PULSE_NS, START_PHASE_NS, OMIT_NE);
    if (ENABLE_STM32) $display("PASS: FSMC command/data/status/attention/seek and bus release");
    $finish;
  end
endmodule
