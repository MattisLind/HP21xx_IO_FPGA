`timescale 1ns/1ps
module tb_hp13210a;
  parameter ENABLE_STM32 = 0;
  parameter HP_PULSE_NS = 173;
  parameter START_PHASE_NS = 0;
  parameter OMIT_NE = 0;
  parameter EARLY_WRITE = 0;
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
    if (iob_in !== expected_value)
      $display("HP input expected %04x got %04x", expected_value, iob_in);
    check(iob_in === expected_value, "HP input value mismatch");
    ioi=0; #191;
    check(iob_in === 0, "Unstrobed HP input must be zero");
  endtask

  task address_phase(input logic [15:0] address, input bit early_write = 0);
    stm32_fsmc_ne=0; stm32_fsmc_nwe=1; stm32_fsmc_noe=1;
    host_oe=1; host_ad=address; #181;
    stm32_fsmc_nadv=0;
    if (early_write) stm32_fsmc_nwe=0;
    #179;
    stm32_fsmc_nadv=1; #183;
  endtask

  task backend_write(input logic [15:0] address, input logic [15:0] value);
    address_phase(address, EARLY_WRITE);
    host_ad=value; #177;
    stm32_fsmc_nwe=0; #181;
    check(stm32_fsmc_ad === value, "FPGA must not drive during an FSMC write");
    stm32_fsmc_nwe=1; #179;
    stm32_fsmc_ne=OMIT_NE ? 0 : 1; host_oe=0; #183;
  endtask

  // Measured FSMC waveform: NWE briefly releases while AD changes from
  // address to data, then asserts again for the actual data phase.
  task backend_write_boundary_release(input logic [15:0] address, input logic [15:0] data);
    address_phase(address, 1);
    stm32_fsmc_nwe=1; host_ad=data; #20;
    stm32_fsmc_nwe=0; #380;
    stm32_fsmc_nwe=1; #179;
    stm32_fsmc_ne=OMIT_NE ? 0 : 1; host_oe=0; #183;
  endtask

  integer data_commit_events=0;
  integer commits_before;
  always @(posedge clk)
    if (dut.core.stm32_write_7900_data_negedge)
      data_commit_events=data_commit_events+1;

  task backend_read(input logic [15:0] address, output logic [15:0] value);
    address_phase(address);
    host_oe=0; #177;
    stm32_fsmc_noe=0; #241;
    value=stm32_fsmc_ad;
    stm32_fsmc_noe=1; #1;
    check(stm32_fsmc_ad === 16'hzzzz, "FSMC read bus must release immediately");
    #178; stm32_fsmc_ne=OMIT_NE ? 0 : 1; #183;
  endtask

  task record_command(input logic [3:0] command, input logic [1:0] drive,
                      input logic [7:0] cylinder, input logic [9:0] head_sector);
    // Diagnostic order: cylinder first, then command, then head/sector.
    hp_write(0, {8'h00, cylinder}); pulse(3);
    hp_write(1, {command, 10'h000, drive});
    pulse(4); pulse(1); pulse(3);
    hp_write(0, {6'h00, head_sector}); pulse(3);
    select_channel(1); pulse(2);
  endtask

  logic [15:0] value;
  task start_transfer(input logic [3:0] command);
    hp_write(1,{command,12'h000}); pulse(4); pulse(1); pulse(3);
    backend_read(16'h0000,value);
    backend_read(16'h0002,value);
    backend_read(16'h000c,value);
    backend_write(16'h0004,16'h1234);
    select_channel(0); pulse(2);
  endtask

  task final_read_clc;
    ioi=1; clc=1; #(HP_PULSE_NS);
    check(iob_in===16'h1234,"Final READ input remains valid with CLC");
    ioi=0; clc=0; #191;
  endtask

  task check_overrun(input bit expected);
    // Observe the HP status word; the status input also clears Overrun.
    select_channel(0); pulse(3); pulse(1);
    hp_write(1,16'h0000); pulse(4); pulse(1); pulse(3);
    select_channel(0); pulse(2);
    ioi=1; #(HP_PULSE_NS);
    check(iob_in[13]===expected,"HP status Overrun matches READ termination");
    ioi=0; #191;
  endtask
  integer test_bit;
  integer seek_drive;
  reg [3:0] test_command;
  initial begin
    #1000000;
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
      backend_read(16'h0002, value);
      backend_read(16'h000c, value);
      backend_write(16'h0000, 16'h0300);
      hp_write(1, 16'h1001); pulse(3);
      check(stm32_irq === 1, "Enabled command interrupt reaches backend");
      backend_read(16'h0000, value);
      check(stm32_irq === 0, "Backend CSR read releases command interrupt");
      backend_read(16'h0002, value);
      backend_read(16'h000c, value);

      hp_write(0, 16'ha55a);
      backend_read(16'h0004, value);
      check(value === 16'ha55a, "HP output word reaches backend");
      backend_write(16'h0004, 16'h1234);
      hp_read(0, 16'h1234);

      backend_write(16'h0006, 16'h0000);
      backend_read(16'h0006, value);
      check(value === 0, "Zero attention write must not latch multiplexed address 6");
      backend_write(16'h0006, 16'h0001);
      backend_read(16'h0006, value);
      check(value === 1, "One-hot attention write must set only drive 0");
      backend_write(16'h0006, 16'h0005);
      backend_write(16'h0006, 16'h000a);
      hp_read(1, 16'h000f);
      // OR/set/clear registers must not consume transient address bits either.
      backend_write(16'h0008, 16'h0000);
      check(dut.core.address_error[0] === 0, "Zero SET STATUS must not latch address bit 3");
      backend_write(16'h0008, 16'h0006);
      backend_write(16'h000a, 16'h0000);
      check(dut.core.drive_busy[0] && dut.core.flagged_cylinder[0],
            "Zero CLEAR STATUS must preserve busy and flagged bits");
      backend_write(16'h000a, 16'h0006);
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

      // Address acceptance must not let HP read attention before completion.
      // Repeat for every drive, including the maximum valid cylinder.
      for (seek_drive=0; seek_drive<4; seek_drive=seek_drive+1) begin
        pulse(7);
        record_command(4'h3, seek_drive[1:0], 8'd202, 10'h317);
        check(dut.core.drive_busy[seek_drive] === 1,
              "SEEK busy status starts at address acceptance before backend service");
        sfs=1; #157;
        check(skf === 0, "SEEK must keep HP command flag clear until backend completion");
        sfs=0;
        backend_read(16'h0000, value);
        check(value[7] === 1, "SEEK address acceptance still requests backend service");
        backend_read(16'h0000, value);
        check(value[7] === 0, "SEEK request is acknowledged by CSR read");
        backend_read(16'h000c, value);
        check(value === {1'b0, 8'd202, 2'd3, 5'd23}, "SEEK retains maximum valid address");
        hp_read(1, 0);
        backend_write(16'h000a, {seek_drive[1:0], 14'h0802});
        backend_write(16'h0006, 16'h0001 << seek_drive);
        select_channel(1); pulse(2); sfs=1; #157;
        check(skf === 1, "Backend attention write raises HP SEEK completion flag");
        sfs=0;
        hp_read(1, 16'h0001 << seek_drive);
      end

      pulse(7);
      record_command(4'hb, 0, 8'd37, 10'h102);
      sfs=1; #157;
      check(skf === 1, "ADDRESS RECORD still completes at address acceptance");
      sfs=0;
      backend_read(16'h0000, value);
      check(value[7] === 0, "ADDRESS RECORD does not dispatch a SEEK worker");

      pulse(7);
      record_command(4'h3, 0, 8'd1, 0);
      backend_read(16'h0000, value);
      hp_write(1, 16'h0000); pulse(4); pulse(3);
      backend_read(16'h0002, value);
      check(value[2] === 0, "STATUS during SEEK must preserve its completion attention");

      pulse(7);
      record_command(4'h3, 0, 8'd1, 0);
      backend_read(16'h0000, value);
      record_command(4'h3, 1, 8'd202, 0);
      backend_read(16'h0002, value);
      check(value[5:2] === 0, "Starting another drive must not abort an outstanding seek");
      pulse(8);
      backend_read(16'h0002, value);
      check(value[5:2] === 4'b0011, "CRS aborts attention for all outstanding seeks");

      pulse(7);
      // Four drives can request seeks before the MCU polls, and a legal
      // STATUS command may overwrite the live command register meanwhile.
      for (seek_drive=0; seek_drive<4; seek_drive=seek_drive+1)
        record_command(4'h3, seek_drive[1:0], 8'd10+seek_drive,
                       (seek_drive << 8) | 23);
      hp_write(1, 16'h0003); pulse(4); pulse(3);
      for (seek_drive=0; seek_drive<4; seek_drive=seek_drive+1) begin
        backend_read(16'h0000, value);
        check(value[7] === 1, "Each queued SEEK remains pending until CSR acknowledgement");
        backend_read(16'h0002, value);
        check(value[15:12] === 4'h3 && value[1:0] === seek_drive[1:0],
              "Queued command survives later STATUS and retains drive order");
        backend_read(16'h000c, value);
        check(value == (((10+seek_drive) << 7) | (seek_drive << 5) | 23),
              "Queued SEEK retains its own address words");
      end
      backend_read(16'h0000, value);
      check(value[7] === 0, "All queued commands consumed exactly once");
      backend_read(16'h0002, value);
      check(value[15:12] === 0 && value[1:0] === 3,
            "After packet consumption, command/status reads return live state");

      pulse(7);
      for (seek_drive=0; seek_drive<8; seek_drive=seek_drive+1)
        record_command(4'h3, 0, 8'd10+seek_drive, 0);
      check(dut.core.request_count === 8, "Request queue holds eight packets");
      record_command(4'h3, 0, 8'd99, 0);
      check(dut.core.overrun[0] === 1, "Queue overflow reports overrun without overwriting old packets");
      for (seek_drive=0; seek_drive<8; seek_drive=seek_drive+1) begin
        backend_read(16'h0000, value);
        backend_read(16'h0002, value);
        backend_read(16'h000c, value);
        check(value == ((10+seek_drive) << 7), "Queue overflow preserves accepted request order");
      end

      pulse(7);
      hp_write(0, 16'd7); pulse(3);
      hp_write(1, 16'h3000); pulse(1); pulse(3);
      hp_write(0, 16'h0117);
      // STC,C has overlapping STC and later CLF phases. Acknowledge only
      // after CLF, including CPU pulses much wider than the FPGA clock.
      stc=1; #(HP_PULSE_NS/2);
      clf=1; #(HP_PULSE_NS/2);
      stc=0; #(HP_PULSE_NS/2);
      clf=0; #191; pulse(2);
      sfs=1; #157;
      check(skf === 1, "SEEK second-word acknowledgement survives delayed CLF");
      sfs=0;
      backend_read(16'h000c, value);
      check(value === {1'b0, 8'd7, 2'd1, 5'd23}, "Wide STC,C captures each address word once");

      pulse(7);
      record_command(4'h3, 0, 8'd1, 0);
      select_channel(1); pulse(4);
      backend_read(16'h0002, value);
      check(value[2] === 1, "Explicit CLC marks a pending seek's attention aborted");
      pulse(2); sfs=1; #157;
      check(skf === 0, "Aborted seek has no fabricated HP completion flag");
      sfs=0;

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

    if (ENABLE_STM32) begin
      // CHECK consumes the count without requesting a stale DMA word.
      // A subsequent backend DATA write explicitly starts optional CHECK DMA.
      // READ staging and WRITE/INITIALIZE consumption must still request it.
      for (test_bit=0; test_bit<4; test_bit=test_bit+1) begin
        case (test_bit)
          0: test_command=4'h1;
          1: test_command=4'h2;
          2: test_command=4'h6;
          3: test_command=4'h9;
        endcase
        reset=1; #199; reset=0; #211;
        backend_write(16'h0000,16'h0100);
        select_channel(0); pulse(1);
        hp_write(0,16'd50); pulse(3); pulse(1);
        hp_write(1,{test_command,12'h000}); pulse(4); pulse(1); pulse(3);
        backend_read(16'h0000,value);
        check(value[7:6]===2'b11,"Command and data request captured");
        backend_read(16'h0002,value);
        check(value[15:12]===test_command,"Transfer command retained");
        backend_read(16'h000c,value);
        select_channel(0); pulse(1); pulse(2);
        check(srq===0,"Data request clear before backend acknowledgement");
        if (test_command==4'h2) backend_write(16'h0004,16'h1234);
        else begin
          backend_read(16'h0004,value);
          check(value===16'd50,"Output/count word reaches backend");
        end
        select_channel(0); pulse(2);
        if (test_command==4'h6)
          check(srq===0,"CHECK count acknowledgement must not request DMA");
        else check(srq===1,"READ/WRITE/INITIALIZE still request next DMA word");
        backend_read(16'h0000,value);
        check(value[6]===0,"Backend data acknowledgement releases CSR6");
        if (test_command==4'h6) begin
          backend_write(16'h0004,16'h5ac3);
          select_channel(0); pulse(2);
          check(srq===1,"Staged CHECK data requests optional DMA");
          ioi=1; #157;
          check(iob_in===16'h5ac3,"CHECK DMA sees staged data, not the sector count");
          ioi=0; pulse(1); pulse(3);
          backend_read(16'h0000,value);
          check(value[6]===1,"CHECK HP acceptance requests the next backend word");
          backend_write(16'h0004,16'h36a9);
          backend_read(16'h0000,value);
          check(value[6]===0,"CHECK staging acknowledges the next-word request");
        end
        backend_write(16'h0006,16'h0000);
        select_channel(1); pulse(2); sfs=1; #157;
        check(skf===1,"Command completion flag preserved after data acknowledgement");
        sfs=0;
      end
    end

    if (ENABLE_STM32) begin
      // Run with every pulse/phase/backend variant, including completion
      // during a held HP STC. No timing-window reduction is involved.
      for (test_bit=0; test_bit<10; test_bit=test_bit+1) begin
        reset=1; #199; reset=0; #211;
        backend_write(16'h0000,16'h0100);
        case (test_bit)
          7: test_command=4'h6;
          8: test_command=4'h1;
          9: test_command=4'h9;
          default: test_command=4'h2;
        endcase
        start_transfer(test_command);
        if (test_bit==0) begin
          pulse(3);
          backend_read(16'h0000,value);
          check(value[6]===1,"Normal READ continuation reaches backend");
          backend_write(16'h0004,16'h1234);
        end
        if (test_bit!=3 && test_bit<8) final_read_clc();
        if (test_bit==1) backend_write(16'h0006,16'h0000);
        if (test_bit==4) pulse(8); // CRS
        if (test_bit==5) pulse(7); // POPIO
        if (test_bit==6) begin
          reset=1; #199; reset=0; #211;
          backend_write(16'h0000,16'h0100);
        end
        if (test_bit==2 || test_bit==3) begin
          stc=1; #211;
          backend_write(16'h0006,16'h0000);
          #211; stc=0; #191;
        end else if (test_bit>=8) begin
          iob_out=16'hbeef; ioo=1; stc=1; clc=1;
          #(HP_PULSE_NS); ioo=0; stc=0; clc=0; #191;
        end else pulse(3);
        backend_read(16'h0000,value);
        if (test_bit==0 || test_bit==2) begin
          check(value[6]===0,"STC after READ CLC is rejected through completion");
          // A subsequent command clears termination, not just reset/POPIO.
          if (test_bit==0) begin
            backend_write(16'h000a,16'h0200);
            start_transfer(4'h2); pulse(3);
            backend_read(16'h0000,value);
            check(value[6]===1,"New READ clears previous termination");
          end
        end else begin
          if (value[6]!==1) $display("READ CLC test case %0d CSR=%04x",test_bit,value);
          check(value[6]===1,"Valid or non-READ STC remains a request");
        end
        if (test_bit>=8) begin
          backend_read(16'h0004,value);
          check(value===16'hbeef,"WRITE/INIT final STC+CLC preserves the last word");
        end
        check_overrun(test_bit==2);
      end
    end

    if (ENABLE_STM32) begin
      pulse(7);
      start_transfer(4'h2);
      select_channel(0); pulse(1);
      commits_before=data_commit_events;
      backend_write_boundary_release(16'h0004,16'hbeef);
      check(data_commit_events==commits_before+1,
            "Address/data NWE release must not duplicate DATA completion");
      pulse(2); hp_read(0,16'hbeef);
      pulse(7);
      backend_write_boundary_release(16'h0006,16'h0001);
      backend_read(16'h0006,value);
      check(value==16'h0001,"Address/data release must not OR address into attention");
      // Captured on the failing physical READ: NOE pulses low for one
      // 50 MHz sample while NWE remains low during a DATA write.
      pulse(7);
      start_transfer(4'h2);
      select_channel(0); pulse(1); pulse(3);
      check(dut.core.stm32_data_channel_irq_ff===1,
            "READ continuation is pending before DATA write");
      commits_before=data_commit_events;
      address_phase(16'h0004,1);
      host_ad=16'hbeef; #80;
      stm32_fsmc_noe=0; #20; stm32_fsmc_noe=1; #180;
      check(dut.core.stm32_data_channel_irq_ff===1,
            "NOE overlap during write must not acknowledge READ continuation");
      check(dut.core.data_channel_flag_buffer_ff===0,
            "NOE overlap must not present stale data to HP");
      stm32_fsmc_nwe=1; #179;
      stm32_fsmc_ne=OMIT_NE ? 0 : 1; host_oe=0; #183;
      check(data_commit_events==commits_before+1,
            "Overlapping NOE pulse must preserve one DATA completion");
      check(dut.core.stm32_data_channel_irq_ff===0,
            "Actual DATA completion acknowledges READ continuation");
      pulse(2); hp_read(0,16'hbeef);
      // Captured loss: NADV and NOE both pulse low for one sample as
      // AD changes from address 4 to FFFF. It is still the same DATA write.
      pulse(7);
      start_transfer(4'h2);
      select_channel(0); pulse(1); pulse(3);
      commits_before=data_commit_events;
      address_phase(16'h0004,1);
      host_ad=16'hffff; #80;
      stm32_fsmc_nadv=0; stm32_fsmc_noe=0; #20;
      stm32_fsmc_nadv=1; stm32_fsmc_noe=1; #300;
      stm32_fsmc_nwe=1; #179;
      stm32_fsmc_ne=OMIT_NE ? 0 : 1; host_oe=0; #183;
      check(data_commit_events==commits_before+1,
            "Brief NADV glitch must not redirect DATA write to address F");
      pulse(2); hp_read(0,16'hffff);
      backend_write_boundary_release(16'h000e,16'ha55a);
      backend_read(16'h000e,value);
      check(value==16'ha55a,"Boundary release retains last data sample");
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
