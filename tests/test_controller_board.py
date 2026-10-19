"""Protect physical pin allocation and reject stale flash programming inputs."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import controller_board as board


class LocatedControllerValidation(unittest.TestCase):
    def test_pin_map_covers_board_and_reserves_configuration_pins(self):
        pins = board.pinmap()
        self.assertEqual(len(pins), 89)
        self.assertEqual(pins['stm32_fsmc_ad<0>']['pin'], 'P100')
        self.assertEqual(pins['stm32_fsmc_ad<15>']['pin'], 'P80')
        self.assertEqual(pins['stm32_fsmc_ad<0>']['direction'], 'inout')
        self.assertEqual(pins['stm32_fsmc_nadv']['pin'], 'P75')
        self.assertEqual(pins['stm32_fsmc_nwe']['pin'], 'P78')
        self.assertEqual(pins['stm32_fsmc_noe']['pin'], 'P79')
        self.assertEqual(pins['iob_in<4>']['pin'], 'P57')
        self.assertEqual(pins['iob_in<12>']['pin'], 'P58')
        self.assertEqual(pins['flash_cs_n']['pin'], 'P38')
        self.assertEqual(pins['clk']['pin'], 'P56')
        self.assertEqual(pins['edt']['pin'], 'P123')
        self.assertEqual(pins['edt']['direction'], 'input')
        self.assertEqual(len({v['pin'] for v in pins.values()}), len(pins))
        self.assertFalse({v['pin'] for v in pins.values()} & {'P37', 'P60', 'P64', 'P65', 'P69', 'P70'})

    def test_changed_inputs_or_bitstream_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / 'controller.bit').write_bytes(b'validated image')
            receipt = {'inputs': board.inputs(), 'pins': board.pinmap(),
                       'bitstream_sha256': board.sha(out / 'controller.bit')}
            (out / 'success.json').write_text(json.dumps(receipt))
            with patch.object(board, 'OUT', out):
                board.validated()
                with patch.object(board, 'inputs', return_value={'modified': True}):
                    with self.assertRaises(RuntimeError):
                        board.validated()
                (out / 'controller.bit').write_bytes(b'modified image')
                with self.assertRaises(RuntimeError):
                    board.validated()
