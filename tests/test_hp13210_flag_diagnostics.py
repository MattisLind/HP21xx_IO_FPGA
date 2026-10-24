"""Check manual diagnostic code paths and the paper-tape record checksums."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import hp13210_flag_diagnostics as diag


class FlagDiagnostics(unittest.TestCase):
    def test_pass_and_failure_paths(self):
        for name, program in diag.programs().items():
            words = program.words()
            first = 0o11 if name == 'flags-15' else 1
            with self.subTest(name=name):
                self.assertEqual(diag.run_model(words), None if name.startswith('scope-') else 0)
                self.assertEqual(diag.run_model(words, 'no-skf'), first)
                self.assertEqual(diag.run_model(words, 'flag-stuck-set'), first)
                if not name.startswith('scope-'):
                    self.assertEqual(diag.run_model(words, 'skf-stuck-asserted'), first+1)
                    self.assertEqual(diag.run_model(words, 'flag-stuck-clear'), first+2)
        self.assertEqual(diag.run_model(diag.programs()['flags-both'].words(),
                                        'cross-coupled'), 0o21)
        # Actual slot uses data 14 / command 15, both octal.
        self.assertEqual(diag.programs()['flags-14'].words()[2:4], [0o103114, 0o102214])
        self.assertEqual(diag.programs()['flags-15'].words()[2:4], [0o103115, 0o102215])

    def test_absolute_tape_round_trip(self):
        for name, program in diag.programs().items():
            data = diag.abs_image(program.words())
            pos = 32
            recovered = []
            while data[pos:pos+2] != b'\0\0':
                count = data[pos]
                self.assertEqual(data[pos+1], 0)
                address = int.from_bytes(data[pos+2:pos+4], 'big')
                self.assertEqual(address, diag.ORIGIN+len(recovered))
                pos += 4
                block = [int.from_bytes(data[pos+2*i:pos+2*i+2], 'big') for i in range(count)]
                pos += 2*count
                self.assertEqual(int.from_bytes(data[pos:pos+2], 'big'), sum(block, address)&65535)
                recovered.extend(block)
                pos += 2
            self.assertEqual(recovered, program.words(), name)
            self.assertEqual(data[pos:], bytes(128))


if __name__ == '__main__':
    unittest.main()
