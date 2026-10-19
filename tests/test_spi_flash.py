"""Reject unexpected or protected flash before destructive operations."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import spi_flash


class FlashStatusValidation(unittest.TestCase):
    def probe(self, text):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            def fake_run(command, log):
                log.write_text(text)
            with patch.object(spi_flash, 'OUT', out), \
                    patch.object(spi_flash.fpga, 'require_tool', return_value='xc3sprog'), \
                    patch.object(spi_flash.fpga, 'run', side_effect=fake_run):
                return spi_flash.spi('probe')

    def report(self, sr1='00', sr2='02', sr3='60', identity='ef 40 0x15'):
        return ('JEDEC: {} 0x00\nWinbond status: SR1={} SR2={} SR3={}\n'
                .format(identity, sr1, sr2, sr3))

    def test_expected_unprotected_quad_enabled_flash(self):
        self.assertEqual(self.probe(self.report())['sr2'], 2)

    def test_wrong_density_is_rejected(self):
        with self.assertRaises(RuntimeError):
            self.probe(self.report(identity='ef 40 0x16'))

    def test_missing_status_reporting_is_rejected(self):
        with self.assertRaises(RuntimeError):
            self.probe('JEDEC: ef 40 0x15 0x00\n')

    def test_quad_disabled_is_rejected_with_nc_auxiliary_pins(self):
        with self.assertRaises(RuntimeError):
            self.probe(self.report(sr2='00'))

    def test_busy_or_protected_flash_is_rejected(self):
        for status in ({'sr1': '01'}, {'sr1': '04'}, {'sr1': '40'},
                       {'sr2': '42'}, {'sr3': '64'}):
            with self.subTest(status=status), self.assertRaises(RuntimeError):
                self.probe(self.report(**status))
