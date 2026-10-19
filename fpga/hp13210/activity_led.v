// Verilog-2001 / Spartan-6 startup INIT. Select inputs use logical HP levels.
`timescale 1ns/1ps
module activity_led #(
  parameter integer CLOCK_HZ = 50000000,
  parameter integer ACTIVE_LOW = 0
) (
  input wire clk,
  input wire iog,
  input wire scm_l,
  input wire scl_l,
  input wire scm_h,
  input wire scl_h,
  output wire led
);
  function integer counter_width;
    input integer value;
    integer remaining;
    begin
      remaining = value - 1;
      counter_width = 1;
      while (remaining > 1) begin
        counter_width = counter_width + 1;
        remaining = remaining >> 1;
      end
    end
  endfunction
  localparam integer PULSE_CYCLES = CLOCK_HZ / 10;
  localparam integer IDLE_CYCLES = CLOCK_HZ * 2;
  // Include PULSE_CYCLES itself, which is loaded into the countdown.
  reg [counter_width(PULSE_CYCLES + 1)-1:0] pulse_left = 0;
  reg [counter_width(IDLE_CYCLES)-1:0] idle_count = 0;
  (* ASYNC_REG = "TRUE", SHREG_EXTRACT = "NO" *)
  reg [4:0] select_meta = 0, select_sync = 0;
  reg [1:0] previous_select = 0;
  wire [1:0] selected = {select_sync[4] & select_sync[1] & select_sync[0],
                         select_sync[4] & select_sync[3] & select_sync[2]};
  wire selection_event = |(selected & ~previous_select);
  wire idle_tick = !(|selected) && idle_count == IDLE_CYCLES - 1;

  always @(posedge clk) begin
    select_meta <= {iog, scm_l, scl_l, scm_h, scl_h};
    select_sync <= select_meta;
    previous_select <= selected;
    // Sustained selection suppresses idle heartbeat but does not lengthen
    // the activity pulse. Adjacent channel selections are separate events.
    if (|selected) idle_count <= 0;
    else if (idle_tick) idle_count <= 0;
    else idle_count <= idle_count + 1'b1;

    // Pulses last exactly 100 ms. Events during a pulse share that pulse;
    // they do not extend it or accumulate a backlog of delayed blinks.
    if (pulse_left != 0) pulse_left <= pulse_left - 1'b1;
    else if (selection_event || idle_tick) pulse_left <= PULSE_CYCLES;
  end
  assign led = ACTIVE_LOW ? (pulse_left == 0) : (pulse_left != 0);
endmodule
