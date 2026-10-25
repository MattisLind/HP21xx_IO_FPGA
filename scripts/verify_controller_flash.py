#!/usr/bin/env python3
"""Compare the built controller with SPI flash, then reload the existing flash image."""
import json
import datetime
import sys
import subprocess
import controller_board
import spi_flash
import fpga


def verify():
    meta = controller_board.validated()
    spi_flash.evidence()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    # The STM32 must be halted/stopped while the FPGA temporarily runs this
    # bridge instead of the FSMC interface. No erase or flash write is issued.
    try:
        status = spi_flash.spi('controller-check-' + stamp,
                               [str(controller_board.OUT/'controller.bit') + ':v:0:BIT'], load=True)
    finally:
        fpga.run([fpga.require_tool('xc3sprog'), '-c', 'xpc', '-R'],
                 log=controller_board.OUT/'flash-check-reconfigure.log')
    receipt = {'verified_utc': fpga.timestamp(), 'matches_current_build': True,
               'bitstream_sha256': meta['bitstream_sha256'], 'flash_written': False,
               'status': status, 'reconfiguration_requested': True}
    fpga.write_json(controller_board.OUT/'flash-verified.json', receipt)
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    try:
        verify()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print('ERROR:', error, file=sys.stderr)
        sys.exit(1)
