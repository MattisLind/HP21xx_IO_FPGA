`timescale 1ns/1ps
module tb_activity_led;
  // Scale the reference frequency: 10 clocks = 100 ms, 200 = two seconds.
  reg clk=0, iog=0, scm_l=0, scl_l=0, scm_h=0, scl_h=0;
  wire led, led_n;
  integer cycles=0, pulse_length=0, completed_pulses=0;
  reg previous_led=0;
  always #10 clk=~clk;
  activity_led #(.CLOCK_HZ(100)) dut(.*);
  activity_led #(.CLOCK_HZ(100), .ACTIVE_LOW(1)) inverted(
    .clk(clk), .iog(iog), .scm_l(scm_l), .scl_l(scl_l),
    .scm_h(scm_h), .scl_h(scl_h), .led(led_n));

  task tick;
    @(posedge clk); #1; cycles=cycles+1;
    if (led_n !== ~led) $fatal(1, "LED polarity");
    if (led) begin
      pulse_length=pulse_length+1;
      if (pulse_length>10) $fatal(1, "Pulse extended beyond 100 ms");
    end else if (previous_led) begin
      if (pulse_length!=10) $fatal(1, "Pulse shorter than 100 ms");
      pulse_length=0; completed_pulses=completed_pulses+1;
    end
    previous_led=led;
  endtask
  task off_ticks(input integer count);
    repeat(count) begin tick(); if(led!==0) $fatal(1, "Unexpected blink at %0d",cycles); end
  endtask
  task await_pulse;
    integer timeout;
    timeout=0;
    while (!led && timeout<5) begin tick(); timeout=timeout+1; end
    if(led!==1) $fatal(1, "Missing selection blink");
  endtask
  task finish_pulse;
    while(led) tick();
  endtask
  initial begin
    #1; if(led!==0 || led_n!==1) $fatal(1, "Startup LED state");
    off_ticks(199); tick();
    if(led!==1) $fatal(1, "First idle heartbeat must start at two seconds");
    finish_pulse();
    off_ticks(189); tick();
    if(cycles!=400 || led!==1) $fatal(1, "Heartbeat onset period must be two seconds");
    finish_pulse();

    // Select-code bits alone, or incomplete code with IOG, cannot trigger.
    scm_l=1; scl_l=1; off_ticks(10);
    scm_l=0; iog=1; off_ticks(10);
    scm_l=1; await_pulse(); finish_pulse();
    // A held selection yields one fixed pulse and prevents idle heartbeats.
    off_ticks(220);
    // Switch directly between select codes without an IOG-low gap.
    scm_l=0; scl_l=0; scm_h=1; scl_h=1;
    await_pulse();
    // A new selection inside the pulse does not lengthen it.
    scm_h=0; scl_h=0; scm_l=1; scl_l=1;
    repeat(4) tick(); finish_pulse();
    off_ticks(10);

    // Following final de-selection, allow synchronizers to drain, then count
    // an entire quiet interval before automatic heartbeat resumes.
    iog=0;
    off_ticks(2);
    off_ticks(199); tick();
    if(led!==1) $fatal(1, "Idle heartbeat must resume two seconds after activity");
    finish_pulse();
    if(completed_pulses!=5) $fatal(1, "Unexpected pulse count %0d",completed_pulses);
    $display("PASS: both select codes, IOG qualification, exact 100 ms pulses, overlap, held selection, two-second idle heartbeat and LED polarities");
    $finish;
  end
  initial begin #100000; $fatal(1,"LED test timeout"); end
endmodule
