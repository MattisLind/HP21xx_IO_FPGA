#!/usr/bin/env python3
"""One-shot SEEK stimulus matching DSN151302 I/O ordering; no hardware access."""
from pathlib import Path
from hp13210_flag_diagnostics import abs_image

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 0o76000


def program():
    rows = []
    labels = {}
    def label(name): labels[name] = ORIGIN+len(rows)
    def emit(op, arg=0, comment=''): rows.append((op,arg,comment))
    emit('CLF',0,'Disable CPU interrupts')
    emit('LDA','ZERO','Cylinder 0')
    emit('OTA',0o14,'DADO: output cylinder before command')
    emit('STC,C',0o14,'DADO: start data channel and clear flag')
    emit('LDA','CMD','SEEK, drive 0')
    emit('OTA',0o15,'COMMD: output command')
    emit('CLC',0o15,'COMMD: clear control')
    emit('STC,C',0o15,'COMMD: set control and clear flag')
    label('WAIT1')
    emit('SFC',0o14,'WAITD: skip if data flag is clear')
    emit('JMP','HEAD','Flag set: send second word')
    emit('JMP','WAIT1','Flag clear: keep waiting')
    label('HEAD')
    emit('LDA','ZERO','Head 0, sector 0')
    emit('OTA',0o14,'DADO: output head/sector')
    emit('STC,C',0o14,'DADO: start data channel and clear flag')
    label('WAIT2')
    emit('SFC',0o14,'WAITD: second-word acknowledgement')
    emit('JMP','SETTLE','Flag set: finish handshake')
    emit('JMP','WAIT2','Flag clear: keep waiting')
    label('SETTLE')
    emit('LDA','ZERO','Extra settling delay, not a diagnostic timing test')
    emit('STA','COUNT','Initialize private counter')
    label('DELAY')
    emit('ISZ','COUNT','65536 increments; lets 4 ms seek worker finish')
    emit('JMP','DELAY')
    label('WAITC')
    emit('SFS',0o15,'Wait for command flag')
    emit('JMP','WAITC','No timeout: operator may halt to inspect P')
    emit('LIA',0o15,'Read attention only; does not issue status command')
    label('DONE')
    emit('HLT',0,'Checkpoint: A should be 000001; not automatic PASS')
    emit('JMP','DONE','CONTINUE re-halts without starting another seek')
    label('ZERO'); emit('OCT',0)
    label('CMD'); emit('OCT',0o030000)
    label('COUNT'); emit('OCT',0,'Only memory word modified by test')
    codes={'CLF':0o103100,'OTA':0o102600,'CLC':0o106700,
           'STC,C':0o103700,'SFC':0o102200,'SFS':0o102300,
           'LIA':0o102500,'HLT':0o102000}
    memory={'LDA':0o062000,'STA':0o072000,'ISZ':0o036000,'JMP':0o026000}
    words=[]
    for op,arg,_ in rows:
        if op in memory:
            address=labels[arg]
            assert address//1024==ORIGIN//1024
            words.append(memory[op]|(address&1023))
        elif op=='OCT': words.append(arg)
        else: words.append(codes[op]|arg)
    return rows,labels,words


def generate():
    rows,labels,words=program()
    folder=ROOT/'diagnostics/hp13210/programs'
    listing=['Address Word   Instruction          Meaning (all numbers octal)']
    assembly=['* One-shot SEEK; all numbers octal.', f'      ORG {ORIGIN:o}B']
    inverse={v:k for k,v in labels.items()}
    for i,(op,arg,comment) in enumerate(rows):
        address=ORIGIN+i
        operand=f'{labels[arg]:06o}' if isinstance(arg,str) else f'{arg:06o}'
        mnemonic='STC' if op=='STC,C' else op
        if op=='STC,C': operand+=',C'
        listing.append(f'{address:06o}  {words[i]:06o} {mnemonic:4s} {operand:10s} {comment}')
        symbolic=arg if isinstance(arg,str) else f'{arg:o}B'
        if op=='STC,C': symbolic+=',C'
        assembly.append(f'{inverse.get(address, ""):6s} {mnemonic:4s} {symbolic:10s} {comment}')
    assembly.append('      END')
    for suffix,text in [('lst',listing),('asm',assembly)]:
        (folder/('seek-once.'+suffix)).write_text('\n'.join(text)+'\n')
    (folder/'seek-once.abs').write_bytes(abs_image(words, origin=ORIGIN))
    print(f'Generated {len(words)} words; start={ORIGIN:06o}, checkpoint={labels["DONE"]:06o}')


if __name__=='__main__': generate()
