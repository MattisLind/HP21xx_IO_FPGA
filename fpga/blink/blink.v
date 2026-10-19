// Verilog-2001, for ISE XST. Register initialization uses Spartan-6 startup INIT.
`timescale 1ns/1ps
module blink #(
    parameter integer CLOCK_HZ = 50000000,
    parameter integer BLINK_HZ = 1,
    parameter integer ACTIVE_LOW = 0
) (
    input wire clk,
    output wire led
);
    function integer counter_width;
        input integer value;
        integer remaining;
        begin
            remaining = value - 1;
            counter_width = 0;
            while (remaining > 0) begin
                counter_width = counter_width + 1;
                remaining = remaining >> 1;
            end
            if (counter_width == 0) counter_width = 1;
        end
    endfunction

    localparam integer HALF_CYCLES = CLOCK_HZ / (2 * BLINK_HZ);
    localparam integer WIDTH = counter_width(HALF_CYCLES);
    reg [WIDTH-1:0] count = 0;
    reg led_on = 1'b0;

    always @(posedge clk) begin
        if (count == HALF_CYCLES - 1) begin
            count <= 0;
            led_on <= ~led_on;
        end else begin
            count <= count + 1'b1;
        end
    end

    assign led = ACTIVE_LOW ? ~led_on : led_on;
endmodule
