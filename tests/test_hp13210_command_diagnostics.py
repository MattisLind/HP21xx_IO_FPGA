"""Check command-only HP stimulus encodings, flow, and absolute tape output."""
from pathlib import Path
import importlib.util
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import hp13210_command_diagnostics as diag
from hp13210_flag_diagnostics import abs_image


class CommandDiagnostics(unittest.TestCase):
    def test_reference_instruction_decode_and_flow(self):
        spec = importlib.util.spec_from_file_location('reference_disasm', ROOT/'hp2116_verilog/hp21xx_gtkwave_filter.py')
        if not spec.origin or not Path(spec.origin).is_file():
            self.skipTest('Reference submodule not initialized')
        reference = importlib.util.module_from_spec(spec)
        previous = sys.dont_write_bytecode
        try:
            sys.dont_write_bytecode = True
            spec.loader.exec_module(reference)
        finally:
            sys.dont_write_bytecode = previous
        for loop in (False, True):
            rows = diag.program(loop)
            diag.check(rows, loop)
            decoded = [reference.mini_disasm(r[0]) for r in rows[:-1]]
            self.assertEqual(decoded[:2], ['CLF 00', 'CLC 15'])
            self.assertEqual(decoded[3], 'OTA 15')
            self.assertTrue(decoded[2].startswith('LDA '))
            self.assertFalse(any(x.startswith(('STC', 'OTB')) for x in decoded))
            # A wrong output channel must fail the instruction-flow check.
            broken = list(rows)
            broken[3] = (0o102614, 'OTA 14', '')
            with self.assertRaises(AssertionError): diag.check(broken, loop)

    def test_tape_payload_and_checksum(self):
        for loop in (False, True):
            words = [r[0] for r in diag.program(loop)]
            tape = abs_image(words, origin=diag.ORIGIN)
            self.assertEqual(tape[32], len(words))
            self.assertEqual(int.from_bytes(tape[34:36], 'big'), diag.ORIGIN)
            payload = [int.from_bytes(tape[i:i+2], 'big') for i in range(36, 36+2*len(words), 2)]
            self.assertEqual(payload, words)
            self.assertEqual(int.from_bytes(tape[36+2*len(words):38+2*len(words)], 'big'), sum(words,diag.ORIGIN)&65535)


if __name__ == '__main__': unittest.main()
