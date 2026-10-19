`timescale 1ns/1ps
module tb_blink;
    reg clk = 0;
    always #10 clk = ~clk; // Board clock: 50 MHz.
    wire led_high, led_low, led_fast;
    // Accelerate the divider while preserving the real input-clock period.
    blink #(.CLOCK_HZ(20), .BLINK_HZ(1)) positive(clk, led_high);
    blink #(.CLOCK_HZ(20), .BLINK_HZ(1), .ACTIVE_LOW(1)) negative(clk, led_low);
    blink #(.CLOCK_HZ(2), .BLINK_HZ(1)) fastest(clk, led_fast);
    integer cycle;
    reg expected;

    initial begin
        #1;
        if ({led_high, led_low, led_fast} !== 3'b010)
            $fatal(1, "Incorrect initial LED state");
        for (cycle = 1; cycle <= 100; cycle = cycle + 1) begin
            @(posedge clk);
            #1;
            expected = (cycle / 10) % 2;
            if (led_high !== expected || led_low !== !expected)
                $fatal(1, "Divider or LED polarity failed at cycle %0d", cycle);
            if (led_fast !== (cycle % 2 == 1))
                $fatal(1, "Single-cycle divider failed at cycle %0d", cycle);
        end
        $display("PASS: startup, exact divider boundaries, both polarities, and minimum divider");
        $finish;
    end
endmodule
