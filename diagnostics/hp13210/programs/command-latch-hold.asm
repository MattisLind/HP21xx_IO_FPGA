* Generated command-latch stimulus; all numbers octal.
      ORG 76000B
      CLF 0            Disable CPU interrupts
      CLC 15           Clear command-channel control once
      LDA 076006       Load command pattern
      OTA 15           Write command latch; no STC
      HLT 00           Checkpoint only; inspect FPGA command register
      JMP 076002       Repeat until operator stops
      OCT 030000       Seek opcode, drive 0; no seek is started
      END
