"""Verify one-shot HP SEEK stimulus flow and the exact I/O ordering."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import hp13210_seek_diagnostic as diag


def run(missing=None):
    _,labels,words=diag.program()
    memory=dict(enumerate(words,diag.ORIGIN)); pc=diag.ORIGIN; a=0
    pending=0; deadline=0; tick=0; increments=0; trace=[]; writes=[]
    for tick in range(150000):
        here=pc; w=memory[pc];pc+=1
        op=w&0o176000; addr=(here&~1023)|(w&1023)
        if op==0o062000: a=memory[addr]
        elif op==0o072000: memory[addr]=a; writes.append(addr)
        elif op==0o036000:
            memory[addr]=(memory[addr]+1)&65535;increments+=1;writes.append(addr)
            if memory[addr]==0: pc+=1
        elif op==0o026000: pc=addr
        elif w==0o103100: pass
        elif w in (0o102614,0o102615): trace.append(('OTA',w&63,a))
        elif w==0o106715: trace.append(('CLC',0o15))
        elif w in (0o103714,0o103715):
            trace.append(('STC,C',w&63))
            if w==0o103714: pending+=1; deadline=tick+5
        elif w==0o102214:
            if pending==missing or tick<deadline: pc+=1
        elif w==0o102315:
            if missing!='command':pc+=1
        elif w==0o102515: a=1;trace.append(('LIA',0o15))
        elif w==0o102000:
            return a,pc,trace,increments,set(writes)
        else: raise AssertionError(f'Unexpected instruction {w:06o}')
    return None,pc,trace,increments,set(writes)


class SeekDiagnostic(unittest.TestCase):
    def test_complete_sequence(self):
        a,pc,trace,increments,writes=run()
        _,labels,_=diag.program()
        self.assertEqual(trace,[('OTA',0o14,0),('STC,C',0o14),
                         ('OTA',0o15,0o030000),('CLC',0o15),('STC,C',0o15),
                         ('OTA',0o14,0),('STC,C',0o14),('LIA',0o15)])
        self.assertEqual(a,1)
        self.assertEqual(pc,labels['DONE']+1)
        self.assertEqual(increments,65536)
        self.assertEqual(writes,{labels['COUNT']})

    def test_missing_handshakes_do_not_fall_through(self):
        _,labels,_=diag.program()
        for missing,label in [(1,'WAIT1'),(2,'WAIT2'),('command','WAITC')]:
            a,pc,trace,_,_=run(missing)
            self.assertIsNone(a)
            self.assertIn(pc,range(labels[label],labels[label]+3))
            self.assertNotIn(('LIA',0o15),trace)


if __name__=='__main__':unittest.main()
