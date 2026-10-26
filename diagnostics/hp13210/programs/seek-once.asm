* One-shot SEEK; all numbers octal.
      ORG 76000B
       CLF  0B         Disable CPU interrupts
       LDA  ZERO       Cylinder 0
       OTA  14B        DADO: output cylinder before command
       STC  14B,C      DADO: start data channel and clear flag
       LDA  CMD        SEEK, drive 0
       OTA  15B        COMMD: output command
       CLC  15B        COMMD: clear control
       STC  15B,C      COMMD: set control and clear flag
WAIT1  SFC  14B        WAITD: skip if data flag is clear
       JMP  HEAD       Flag set: send second word
       JMP  WAIT1      Flag clear: keep waiting
HEAD   LDA  ZERO       Head 0, sector 0
       OTA  14B        DADO: output head/sector
       STC  14B,C      DADO: start data channel and clear flag
WAIT2  SFC  14B        WAITD: second-word acknowledgement
       JMP  SETTLE     Flag set: finish handshake
       JMP  WAIT2      Flag clear: keep waiting
SETTLE LDA  ZERO       Extra settling delay, not a diagnostic timing test
       STA  COUNT      Initialize private counter
DELAY  ISZ  COUNT      65536 increments; lets 4 ms seek worker finish
       JMP  DELAY      
WAITC  SFS  15B        Wait for command flag
       JMP  WAITC      No timeout: operator may halt to inspect P
       LIA  15B        Read attention only; does not issue status command
DONE   HLT  0B         Checkpoint: A should be 000001; not automatic PASS
       JMP  DONE       CONTINUE re-halts without starting another seek
ZERO   OCT  0B         
CMD    OCT  30000B     
COUNT  OCT  0B         Only memory word modified by test
      END
