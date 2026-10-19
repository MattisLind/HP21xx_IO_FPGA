"""Check that missing constraints and timing failures cannot pass validation."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fpga


class TimingValidation(unittest.TestCase):
    def check_report(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "blink.twr"
            path.write_text(text)
            with redirect_stdout(StringIO()):
                fpga.check_timing(path)

    def report(self, period="20.000ns", items=25, errors=0, score=0):
        return ('Timing constraint: TS_clk = PERIOD TIMEGRP "clk" {} HIGH 50%;\n'
                '{} items analyzed, {} timing errors detected.\n'
                'Timing summary:\nTiming errors: {} Score: {}\n').format(period, items, errors, errors, score)

    def test_constrained_passing_clock(self):
        self.check_report(self.report())

    def test_spartan6_trace_report_format(self):
        self.check_report('Timing constraint: TS_clk = PERIOD TIMEGRP "clk" 20 ns HIGH 50%;\n'
                          '977 paths analyzed, 53 endpoints analyzed, 0 failing endpoints\n'
                          '0 timing errors detected. (0 setup errors, 0 hold errors)\n'
                          'Minimum period is 4.110ns.\n'
                          'Timing summary:\nTiming errors: 0 Score: 0 (Setup/Max: 0, Hold: 0)\n')

    def test_zero_paths_in_spartan6_report_is_rejected(self):
        with self.assertRaises(RuntimeError):
            self.check_report(self.report().replace('25 items analyzed', '0 paths analyzed'))

    def test_unconstrained_zero_error_summary_is_rejected(self):
        with self.assertRaises(RuntimeError):
            self.check_report("Timing errors: 0 Score: 0\n")

    def test_empty_clock_group_is_rejected(self):
        with self.assertRaises(RuntimeError):
            self.check_report(self.report(items=0))

    def test_timing_violation_is_rejected(self):
        with self.assertRaises(RuntimeError):
            self.check_report(self.report(errors=1, score=63))

    def test_wrong_clock_period_is_rejected_even_with_20ns_in_path_text(self):
        with self.assertRaises(RuntimeError):
            self.check_report(self.report(period="10ns") + "Path information: 20ns\n")


class BoardValidation(unittest.TestCase):
    def check_board(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "board.json"
            path.write_text(json.dumps(data))
            return fpga.read_board(path)

    def test_missing_hardware_details_are_rejected(self):
        template = json.loads((fpga.ROOT / "config/board.example.json").read_text())
        for field in ("part", "clock_pin", "iostandard"):
            with self.subTest(field=field):
                incomplete = dict(template, **{field: None})
                with self.assertRaises(RuntimeError):
                    self.check_board(incomplete)

    def test_shared_clock_and_led_pin_is_rejected(self):
        with self.assertRaises(RuntimeError):
            self.check_board({"part": "xc6slx9-2-tqg144", "clock_pin": "P57", "clock_hz": 50000000,
                              "led_pin": "P57", "led_active_low": False, "iostandard": "LVCMOS33"})


if __name__ == "__main__":
    unittest.main()
