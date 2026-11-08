#!/usr/bin/env python3
"""Reproducible initial capture. Generated KiCad files are editable after capture.

This script is a seed generator, not a round-trip schematic editor. Regeneration
requires --force and overwrites generated sheets; preserve manual edits first.
Uses the installed KiCad symbol library, no Python packages required.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import re
import uuid
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'hardware/integrated'
LIB = Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols')
NS = uuid.UUID('10515202-78cf-4879-97b8-3ae2d8f644d6')


def uid(key):
    return str(uuid.uuid5(NS, key))


def snap(v):
    return round(round(v/1.27)*1.27,4)


def q(s):
    return json.dumps(str(s), ensure_ascii=False)


def parse(text):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[^\s()]+|[()]', text)
    stack = [[]]
    for t in tokens:
        if t == '(':
            a = []; stack[-1].append(a); stack.append(a)
        elif t == ')':
            stack.pop()
        else:
            stack[-1].append(json.loads(t) if t.startswith('"') else t)
    assert len(stack) == 1
    return stack[0][0]


def sexp(node):
    if isinstance(node, list):
        return '(' + ' '.join(sexp(x) for x in node) + ')'
    # Numeric values and KiCad keywords are atoms; names and text are strings.
    if isinstance(node, Atom):
        return str(node)
    return q(node)


class Atom(str):
    pass


def atomize(text):
    """Keep quoted strings distinct when reading library definitions."""
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[^\s()]+|[()]', text)
    stack = [[]]
    for t in tokens:
        if t == '(':
            a = []; stack[-1].append(a); stack.append(a)
        elif t == ')':
            stack.pop()
        else:
            stack[-1].append(json.loads(t) if t.startswith('"') else Atom(t))
    assert len(stack) == 1
    return stack[0][0]


def sub(node, tag):
    return [x for x in node if isinstance(x, list) and x and x[0] == tag]


def one(node, tag, default=None):
    a = sub(node, tag)
    return a[0] if a else default


class Symbols:
    def __init__(self):
        self.files = {}; self.cache = {}; self.custom = {}

    def load(self, lib_id):
        if lib_id in self.custom:
            return copy.deepcopy(self.custom[lib_id])
        if lib_id in self.cache:
            return copy.deepcopy(self.cache[lib_id])
        lib, name = lib_id.split(':')
        if lib not in self.files:
            self.files[lib] = (LIB / (lib + '.kicad_sym')).read_text()
        text = self.files[lib]
        m = re.search(r'\n\t\(symbol ' + re.escape(q(name)) + r'\s', text)
        if not m:
            raise ValueError(f'Missing KiCad symbol {lib_id}')
        start = m.start() + 2
        depth = 0; quoted = False; escape = False
        for i in range(start, len(text)):
            c = text[i]
            if escape:
                escape = False; continue
            if quoted and c == '\\':
                escape = True; continue
            if c == '"': quoted = not quoted
            if not quoted:
                if c == '(': depth += 1
                elif c == ')':
                    depth -= 1
                    if depth == 0: break
        result = atomize(text[start:i+1])
        parent = one(result, 'extends')
        if parent:
            base = self.load(lib + ':' + parent[1])
            overridden = {x[1] for x in sub(result, 'property')}
            base = [x for x in base if not (isinstance(x,list) and x and x[0]=='property' and x[1] in overridden)]
            base[1] = name
            for child in sub(base, 'symbol'):
                child[1] = re.sub(r'^.*?(?=_[0-9]+_[0-9]+$)', name, child[1])
            base.extend(x for x in result[2:] if not (isinstance(x,list) and x[0]=='extends'))
            result = base
        result[1] = lib_id
        self.cache[lib_id] = copy.deepcopy(result)
        return result

    def pins(self, lib_id, unit=1):
        result = []
        for child in sub(self.load(lib_id), 'symbol'):
            m = re.search(r'_(\d+)_(\d+)$', child[1])
            if m and int(m[1]) in [0,unit] and int(m[2]) in [0,1]:
                for pin in sub(child, 'pin'):
                    result.append(dict(number=one(pin,'number')[1], name=one(pin,'name')[1],
                        x=float(one(pin,'at')[1]),y=float(one(pin,'at')[2]),angle=float(one(pin,'at')[3]),kind=pin[1]))
        return result

    def box(self, name, pins, width=20.32, reference='U'):
        """Explicit custom pin map: (number, name, side, electrical type)."""
        groups = {side:[p for p in pins if p[2]==side] for side in ['L','R']}
        height = max(len(x) for x in groups.values()) * 2.54 + 5.08
        h = math.ceil(height/5.08)*2.54
        w = width/2
        text=f'''(symbol {q(name)} (pin_names (offset 0.635)) (in_bom yes) (on_board yes)
        (property "Reference" {q(reference)} (at 0 {h+2.54} 0) (effects (font (size 1.27 1.27))))
        (property "Value" {q(name)} (at 0 {-h-2.54} 0) (effects (font (size 1.27 1.27))))
        (symbol {q(name+'_0_1')} (rectangle (start {-w} {h}) (end {w} {-h}) (stroke (width 0.254) (type default)) (fill (type background)))))'''
        root = atomize(text)
        unit = [Atom('symbol'),name+'_1_1']
        for side, items in groups.items():
            for j,(number,pname,_,kind) in enumerate(items):
                y = h-3.81-j*2.54; x = -w-2.54 if side=='L' else w+2.54
                angle = 0 if side=='L' else 180
                unit.append(atomize(f'''(pin {kind} line (at {x} {y} {angle}) (length 2.54)
                 (name {q(pname)} (effects (font (size 0.9 0.9))))
                 (number {q(number)} (effects (font (size 0.9 0.9)))))'''))
        root.append(unit); root[1]='HP21xx:'+name
        self.custom['HP21xx:'+name]=root
        return 'HP21xx:'+name


S = Symbols()
BOM = list(csv.DictReader((ROOT/'requirements/INTEGRATED_BOARD_BOM.csv').open()))
BF = {r['Function']:r for r in BOM}


def bom(fn):
    return BF[fn]


POWER = {'GND','HP_5V','HP_N2V','HP_P12V','HP_N12V','+3V3_HP','+1V2_FPGA','+3V3_MCU','USB_VBUS','MCU_VIN','PENDANT_5V'}
ROOT_ID = uid('FPGA')
COUNTERS=Counter()
CAPTURE=[]


class Sheet:
    def __init__(self,name,number):
        self.name=name; self.number=number; self.id=uid(name); self.objects=[]; self.libs={}; self.ports={}; self.components=[]
        self.counter=defaultdict(lambda:1000*(number-1))

    def text(self,text,x,y,size=1.1,bold=False):
        self.objects.append(f'(text {q(text)} (at {x} {y} 0) (effects (font (size {size} {size}) {"(bold yes)" if bold else ""}) (justify left top)) (uuid {q(uid(self.name+text+str((x,y))))}))')

    def wire(self,a,b):
        a=tuple(snap(v) for v in a); b=tuple(snap(v) for v in b)
        if a==b: return
        self.objects.append(f'(wire (pts (xy {a[0]:.4f} {a[1]:.4f}) (xy {b[0]:.4f} {b[1]:.4f})) (stroke (width 0) (type default)) (uuid {q(uid(self.name+str((a,b))+str(len(self.objects))))}))')

    def label(self,net,xy,angle=0,global_=False,size=0.8):
        xy=tuple(snap(v) for v in xy)
        typ='global_label' if global_ else 'label'
        shape='(shape input)' if global_ else ''
        justify='left bottom' if angle==0 else 'right bottom'
        self.objects.append(f'({typ} {q(net)} {shape} (at {xy[0]:.4f} {xy[1]:.4f} {angle}) (effects (font (size {size} {size})) (justify {justify})) (uuid {q(uid(self.name+net+str(xy)+str(len(self.objects))))}))')

    def nc(self,xy):
        xy=tuple(snap(v) for v in xy)
        self.objects.append(f'(no_connect (at {xy[0]:.4f} {xy[1]:.4f}) (uuid {q(uid(self.name+"nc"+str(xy)))}))')

    def place(self,lib_id,x,y,nets,fn=None,value=None,ref=None,unit=1,angle=0,footprint=None,review='',compact=False):
        x=snap(x); y=snap(y)
        definition=S.load(lib_id); self.libs[lib_id]=definition
        metadata=bom(fn) if fn else {}
        if ref is None:
            prop=one(definition,'property'); prefix=prop[2] if prop else 'U'
            # Reference is not necessarily the first property on inherited symbols.
            prefix=next((p[2] for p in sub(definition,'property') if p[1]=='Reference'),'U')
            self.counter[prefix]+=1; ref=prefix+str(self.counter[prefix])
        inst_id=uid(self.name+ref+str(unit))
        val=value or metadata.get('MPN') or next((p[2] for p in sub(definition,'property') if p[1]=='Value'),lib_id.split(':')[1])
        fp=footprint if footprint is not None else next((p[2] for p in sub(definition,'property') if p[1]=='Footprint'),'')
        fields={'Reference':ref,'Value':val,'Footprint':fp,'Datasheet':metadata.get('Datasheet_URL','') or metadata.get('Catalog_URL','')}
        for f in ['Manufacturer','MPN','LCSC','TME','Source','Selection_status']:
            fields[f]=metadata.get(f,'')
        fields['BOM_Item']=metadata.get('Item',''); fields['Review']=review
        parts=[]
        for k,v in fields.items():
            visible=k in ['Reference','Value']
            px=x; py=y-3.0 if k=='Reference' else y+3.0
            if not compact and k=='Reference': py=y-5.0
            if not compact and k=='Value': py=y-3.5
            if not compact and k in ['Reference','Value']:
                # Keep large-device fields above their bodies instead of over pins.
                original=next((p for p in sub(definition,'property') if p[1]==k),None)
                if original and (lib_id.startswith('HP21xx:') or len(S.pins(lib_id,unit))>12):
                    at=one(original,'at')
                    if at:
                        px=x+float(at[1]); py=y-float(at[2])
            # Only small, readable displayed values; exact ordering data in MPN field.
            parts.append(f'(property {q(k)} {q(v)} (at {px} {py} 0) (effects (font (size {0.7 if compact else 0.9} {0.7 if compact else 0.9})) {"" if visible else "(hide yes)"}))')
        path='/'+ROOT_ID if self.number==1 else '/'+ROOT_ID+'/'+self.id
        pins=S.pins(lib_id,unit)
        pin_inst=' '.join(f'(pin {q(p["number"])} (uuid {q(uid(inst_id+p["number"]))}))' for p in pins)
        inbom='no' if lib_id.startswith('power:') or lib_id=='Connector:TestPoint' else 'yes'
        onboard='no' if lib_id.startswith('power:') else 'yes'
        self.objects.append(f'''(symbol (lib_id {q(lib_id)}) (at {x} {y} {angle}) (unit {unit})
        (in_bom {inbom}) (on_board {onboard}) (dnp no) (uuid {q(inst_id)}) {' '.join(parts)} {pin_inst}
        (instances (project "HP21xx_IO" (path {q(path)} (reference {q(ref)}) (unit {unit})))))''')
        rad=math.radians(angle)
        connected={}
        drawn=set(); rail_ends={}
        for p in pins:
            # Library coordinates use upward-positive Y, schematic uses downward-positive.
            dx=p['x']*math.cos(rad)-p['y']*math.sin(rad)
            dy=-(p['x']*math.sin(rad)+p['y']*math.cos(rad))
            pos=(round(x+dx,4),round(y+dy,4)); net=nets.get(p['number'])
            connected[p['number']]=net
            if pos in drawn: continue
            drawn.add(pos)
            if net is None: self.nc(pos); continue
            direction=math.radians(p['angle']+angle+180)
            end=(round(pos[0]+2.54*math.cos(direction),4),round(pos[1]-2.54*math.sin(direction),4))
            self.wire(pos,end)
            if net in POWER and abs(math.cos(direction))<0.01:
                key=(net,end[1])
                if key in rail_ends:
                    self.wire(rail_ends[key],end); continue
                rail_ends[key]=end
            # All pin stubs get labels; power names are global, signals sheet-local.
            self.label(net,end,0 if math.cos(direction)>=-0.01 else 180,net in POWER,size=0.65 if compact else 0.8)
        entry=dict(sheet=self.name,reference=ref,unit=unit,lib_id=lib_id,value=val,footprint=fp,bom_item=metadata.get('Item',''),pins=connected,review=review)
        self.components.append(entry); CAPTURE.append(entry)
        return ref

    def two(self,lib_id,x,y,a,b,fn,value,angle=0,footprint=None):
        return self.place(lib_id,x,y,{'1':a,'2':b},fn,value,angle=angle,footprint=footprint,compact=True)

    def r(self,x,y,a,b,fn,value,angle=0):
        size='1206' if '1206' in bom(fn)['Package'] else '0805' if '0805' in bom(fn)['Package'] else '0603'
        fp={'0603':'R_0603_1608Metric','0805':'R_0805_2012Metric','1206':'R_1206_3216Metric'}[size]
        return self.two('Device:R_Small',x,y,a,b,fn,value,angle,'Resistor_SMD:'+fp)

    def c(self,x,y,a,b,fn,value):
        size='1206' if '1206' in bom(fn)['Package'] else '0805' if '0805' in bom(fn)['Package'] else '0603'
        fp={'0603':'C_0603_1608Metric','0805':'C_0805_2012Metric','1206':'C_1206_3216Metric'}[size]
        return self.two('Device:C_Small',x,y,a,b,fn,value,footprint='Capacitor_SMD:'+fp)

    def caps(self,fn,n,rail,x,y,cols=10,dx=10.16,dy=15.24,value='100n'):
        for i in range(n): self.c(x+(i%cols)*dx,y+(i//cols)*dy,rail,'GND',fn,value)

    def led(self,x,y,anode,cathode,fn):
        return self.place('Device:LED',x,y,{'1':cathode,'2':anode},fn,value='RED',footprint='LED_SMD:LED_0603_1608Metric',compact=True)

    def port(self,net,x,y,shape='bidirectional'):
        x=snap(x); y=snap(y)
        if net in POWER: return
        self.ports[net]=shape
        self.objects.append(f'(hierarchical_label {q(net)} (shape {shape}) (at {x} {y} 0) (effects (font (size 0.75 0.75)) (justify left)) (uuid {q(uid(self.name+"port"+net))}))')
        self.wire((x,y),(x+2.54,y)); self.label(net,(x+2.54,y))

    def port_bank(self,nets,x,y,columns=1,rows=30,step=3.81,dx=50):
        pending=0
        for n in dict.fromkeys(nets):
            # Export an existing pin-net stub directly; avoid duplicate page-edge
            # banks of long labels and keep the hierarchical interface readable.
            prefix='(label '+q(n)+' '
            for i,obj in enumerate(self.objects):
                if obj.startswith(prefix):
                    obj=obj.replace(prefix,'(hierarchical_label '+q(n)+' (shape bidirectional) ',1)
                    obj=obj.replace('(justify left bottom)','(justify left)').replace('(justify right bottom)','(justify right)')
                    self.objects[i]=obj; self.ports[n]='bidirectional'; break
            else:
                self.port(n,x+(pending//rows)*dx,y+(pending%rows)*step); pending+=1

    def child(self,child,x,y,w,h):
        x=snap(x); y=snap(y); w=snap(w); h=snap(h)
        port_items=list(child.ports.items())
        parts=[]
        # Pins on both sides keep individual sheet symbols within the A3 height.
        count=math.ceil(len(port_items)/2)
        for i,(n,shape) in enumerate(port_items):
            right=i>=count; j=i-count if right else i
            px=x+w if right else x; py=y+5.08+j*2.54
            parts.append(f'(pin {q(n)} {shape} (at {px} {py} {0 if right else 180}) (effects (font (size 0.65 0.65)) (justify {"right" if right else "left"})) (uuid {q(uid(child.id+n))}))')
            end=(px+2.54 if right else px-2.54,py); self.wire((px,py),end); self.label(n,end,0 if right else 180,size=0.65)
        h=max(h,count*2.54+10.16)
        self.objects.append(f'''(sheet (at {x} {y}) (size {w} {h})
        (stroke (width 0.254) (type default)) (fill (color 0 0 0 0)) (uuid {q(child.id)})
        (property "Sheetname" {q(child.name)} (at {x} {y-1.27} 0) (effects (font (size 1.1 1.1)) (justify left bottom)))
        (property "Sheetfile" {q(child.name+'.kicad_sch')} (at {x} {y+h+1.27} 0) (effects (font (size 0.8 0.8)) (justify left top)))
        {' '.join(parts)}
        (instances (project "HP21xx_IO" (path {q('/'+ROOT_ID)} (page {q(child.number)})))))''')

    def save(self):
        header=f'''(kicad_sch (version 20250114) (generator "eeschema") (generator_version "9.0")
        (uuid {q(self.id)}) (paper "A3")
        (title_block (title {q('HP 21xx integrated I/O - '+self.name)}) (date "2026-11-08") (rev "0.1 capture")
         (comment 1 "DRAFT - electrical and footprint review required") (comment 2 "12.8mm component-height limit; THT from TME; HRO USB from JLCPCB"))
        (lib_symbols {' '.join(sexp(d) for d in self.libs.values())})'''
        inst='(sheet_instances (path "/" (page "1")))' if self.number==1 else ''
        filename='HP21xx_IO' if self.number==1 else self.name
        (OUT/(filename+'.kicad_sch')).write_text(header+'\n'+'\n'.join(self.objects)+'\n'+inst+'\n)\n')


def inspect():
    ids=['FPGA_Xilinx_Spartan6:XC6SLX9-TQG144','MCU_ST_STM32F4:STM32F407VGTx',
        'Regulator_Switching:TLV62569DBV','Transistor_BJT:MMBT2222A','Diode:1N4148WS',
        '74xx:74LS04','74xGxx:74LVC2G125','74xx:74LVC125','Connector:USB_C_Receptacle_USB2.0_16P',
        'Power_Protection:USBLC6-2SC6','Interface_Ethernet:LAN8720A','Power_Supervisor:TPS3808DBV',
        'Memory_Flash:W25Q16JVSS','Connector:SD_Card_Receptacle','74xGxx:74LVC1G32']
    for k in ids:
        try:
            print(k)
            d=S.load(k)
            for u in sorted({int(re.search(r'_(\d+)_\d+$',c[1])[1]) for c in sub(d,'symbol')} - {0}):
                print(' unit',u,[(p['number'],p['name'],(p['x'],p['y']),p['kind']) for p in S.pins(k,u)])
        except Exception as e: print(e)


def aliases():
    for original,name in [('Transistor_BJT:MMBT2222A','MMBT2369ALT1G'),('74xx:74LS04','74ACT04SCX'),
                          ('Memory_Flash:W25Q16JVSS','GD25Q16ESIG'),('Device:D_Schottky','BAT54WS')]:
        d=S.load(original); oldname=original.split(':')[1]; d[1]='HP21xx:'+name
        for child in sub(d,'symbol'): child[1]=child[1].replace(oldname,name)
        for prop in sub(d,'property'):
            if prop[1]=='Value': prop[2]=name
            if prop[1]=='Datasheet': prop[2]=''
        S.custom['HP21xx:'+name]=d
    S.box('CDCLVC1104PWR', [('1','CLKIN','L','input'),('2','1G','L','input'),('4','GND','L','power_in'),
        ('6','VDD','L','power_in'),('3','Y0','R','output'),('8','Y1','R','output'),('5','Y2','R','output'),('7','Y3','R','output')])
    S.box('OSC_3V3_50MHz',[('1','OE','L','input'),('2','GND','L','power_in'),('4','VDD','R','power_in'),('3','OUT','R','output')],10.16,reference='Y')
    S.box('SN75185DWR',[(str(n),name,'L' if n<=10 else 'R',kind) for n,name,kind in [
        (1,'VDD +12V','power_in'),(2,'RA1','input'),(3,'RA2','input'),(4,'RA3','input'),(5,'DY1','output'),(6,'DY2','output'),
        (7,'RA4','input'),(8,'DY3','output'),(9,'RA5','input'),(10,'VSS -12V','power_in'),
        (20,'VCC +5V','power_in'),(19,'RY1','output'),(18,'RY2','output'),(17,'RY3','output'),(16,'DA1','input'),
        (15,'DA2','input'),(14,'RY4','output'),(13,'DA3','input'),(12,'RY5','output'),(11,'GND','power_in')]])
    S.box('SD_106M',[('1','DAT3','L','bidirectional'),('2','CMD','L','bidirectional'),('3','VSS','L','power_in'),
        ('4','VDD','L','power_in'),('5','CLK','L','input'),('6','VSS','L','passive'),('7','DAT0','R','bidirectional'),
        ('8','DAT1','R','bidirectional'),('9','DAT2','R','bidirectional'),('10','CD switch','R','passive'),('11','WP switch','R','passive')],reference='J')
    # This is the board-side electrical contact numbering, not an assumed mating face.
    S.box('HP_EDGE_86',[(str(i),str(i),'L' if i<=43 else 'R','passive') for i in range(1,87)],10.16,reference='J')


def regulator(sh,x,y,rail,vin,index):
    sw=f'BUCK{index}_SW'; fb=f'BUCK{index}_FB'; en=f'BUCK{index}_EN'
    sh.text(rail+' / TLV62569 DBV (no PG)',x-20,y-19,1.0,True)
    sh.place('Regulator_Switching:TLV62569DBV',x,y,{'1':en,'2':'GND','3':sw,'4':vin,'5':fb},'Independent buck stages',value='TLV62569DBVR')
    sh.r(x-20,y+5,vin,en,'Buck enable links','0')
    sh.c(x-30,y,vin,'GND','Buck input capacitors','4.7u/10V')
    sh.c(x-40,y,vin,'GND','Buck input HF bypass','100n')
    sh.two('Device:L_Small',x+20,y-5,sw,rail,'Buck power inductors','2.2uH',90,
        '')
    sh.c(x+30,y+2,rail,'GND','Buck output capacitors','22u/25V')
    if rail=='+1V2_FPGA':
        fn1=fn2='1.2V buck feedback pair'; v1=v2='100k'
    else: fn1='3.3V buck feedback upper'; fn2='3.3V buck feedback lower'; v1='330k'; v2='73.2k'
    sh.r(x+14,y+10,rail,fb,fn1,v1); sh.r(x+25,y+16,fb,'GND',fn2,v2)


def read_maps():
    fp=list(csv.DictReader((ROOT/'requirements/INTEGRATED_BOARD_FPGA_PINS.csv').open()))
    mc=list(csv.DictReader((ROOT/'requirements/INTEGRATED_BOARD_STM32_PINS.csv').open()))
    hp=[]; fpn={}; mcn={}
    # Fixed package-number assignments already reviewed in the design.
    special={37:'PON_RESET_N',38:'FLASH_CS_N',39:'FPGA_INIT_N',56:'CLK50_FPGA',60:'FPGA_M1',
        64:'FLASH_MOSI',65:'FLASH_MISO',69:'FPGA_M0',70:'FLASH_CLK',71:'FPGA_DONE',
        73:'GND',106:'FPGA_TDO',107:'FPGA_TMS',109:'FPGA_TCK',110:'FPGA_TDI',143:'FPGA_LED',144:'GND'}
    fsmc_pads=[100,99,98,97,95,94,93,92,88,87,85,84,83,82,81,80]
    special.update({p:f'FSMC_AD{i}' for i,p in enumerate(fsmc_pads)})
    special.update({79:'FSMC_NOE',78:'FSMC_NWE',75:'FSMC_NADV',67:'FPGA_AUX1',74:'FPGA_AUX2'})
    for r in fp:
        p=int(r['Package_pin']); name=r['Pin_name']; fn=r['Function']
        if r['Usage']=='POWER':
            net='GND' if name=='GND' else '+1V2_FPGA' if name=='VCCINT' else '+3V3_HP'
        elif p in special: net=special[p]
        elif r['Usage']=='HP-BUS':
            m=re.match(r'HP (.*?)(?: (?:RX|TX))?; HP contact (\d+)',fn)
            if not m: raise ValueError(fn)
            signal=m[1].replace(' ','_'); direction=r['Direction']
            net=f'HP_{signal}_{"RX" if direction=="I" else "TX"}'
            hp.append(dict(pad=p,contact=int(m[2]),signal=signal,direction=direction,net=net))
        elif r['Expansion'] in ['Yes','Conditional']: net=f'FPGA_P{p}'
        else: net=None
        fpn[str(p)]=net
    for r in mc:
        p=r['Package_pin']; name=r['Pin_name']; fn=r['Function']; usage=r['Usage']
        if usage=='POWER':
            net='GND' if name in ['VSS','VSSA'] else 'MCU_'+name if name.startswith('VCAP') else 'MCU_VDDA' if name in ['VDDA','VREF+'] else '+3V3_MCU'
        elif usage=='UNCOMMITTED': net='MCU_'+name
        elif usage in ['FPGA-FSMC','FPGA-CONTROL']: net='MCU_'+fn
        elif usage=='FPGA-JTAG' and fn!='FPGA_TDO': net='MCU_'+fn
        elif usage=='RESET': net='MCU_NRST'
        elif name=='PH0': net='HSE_IN'
        elif name=='PH1': net='HSE_OUT'
        elif name=='BOOT0': net='MCU_BOOT0'
        elif name=='PB2': net='MCU_BOOT1'
        elif name=='PA0': net='HP_ABSENT'
        else: net=fn
        mcn[p]=net
    assert len(fpn)==144 and len(mcn)==100
    assert Counter(x['direction'] for x in hp)=={'I':43,'O':24}
    return fp,mc,fpn,mcn,hp


def hp_sheet(sh,hp):
    sh.text('43 inverting receiver channels',9,7,1.5,True)
    sh.text('24 ACT04 + emitter-output drivers',153,7,1.5,True)
    ins=[x for x in hp if x['direction']=='I']; outs=[x for x in hp if x['direction']=='O']
    for i,c in enumerate(ins):
        x=12+(i//15)*46; y=22+(i%15)*17
        raw='HP_C'+str(c['contact']); base=f'RXB{i}'; out=c['net']
        sh.text(f'HP{c["contact"]} {c["signal"]} -> P{c["pad"]}',x-4,y-8,0.8)
        sh.r(x,y,raw,'HP_N2V','Receiver input termination to -2V','2k')
        sh.r(x+12,y,raw,base,'Receiver base series resistors','1k',90)
        sh.place('HP21xx:MMBT2369ALT1G',x+24,y,{'1':base,'2':'GND','3':out},'HP receiver transistors',value='2369A',compact=True,footprint='Package_TO_SOT_SMD:SOT-23')
        sh.r(x+36,y,out,'+3V3_HP','Receiver collector pull-ups to +3V3_HP','220')
        sh.two('Diode:1N4148WS',x+12,y+6,base,'GND','HP receiver reverse-BE clamp diodes','4148WS',footprint='Diode_SMD:D_SOD-323')
    gates={}; gatepins=[('1','2'),('3','4'),('5','6'),('9','8'),('11','10'),('13','12')]
    for i,c in enumerate(outs):
        x=160+(i//12)*65; y=23+(i%12)*21
        raw='HP_C'+str(c['contact']); base=f'DRV_B{i}'; coll=f'DRV_C{i}'; inv=f'DRV_INV{i}'
        sh.text(f'P{c["pad"]} -> HP{c["contact"]} {c["signal"]}',x-8,y-9,0.8)
        sh.r(x-3,y,c['net'],'+3V3_HP','Driver input pull-ups to +3V3_HP','2k')
        chip=i//6; u=i%6+1; pi,po=gatepins[u-1]
        ref=sh.place('HP21xx:74ACT04SCX',x+14,y,{pi:c['net'],po:inv},'HP output hex inverters',value='ACT04',unit=u,ref=gates.get(chip),compact=True,footprint='Package_SO:SOIC-14_3.9x8.7mm_P1.27mm')
        gates[chip]=ref
        sh.place('HP21xx:MMBT2369ALT1G',x+43,y,{'1':base,'2':raw,'3':coll},'HP output emitter transistors',value='2369A',compact=True,footprint='Package_TO_SOT_SMD:SOT-23')
        sh.r(x+57,y-3,'HP_5V',coll,'Driver collector feed resistors','22')
        sh.r(x+30,y+6,'HP_5V',base,'Driver +5V base-bias resistors','220/0.25W')
        sh.two('HP21xx:BAT54WS',x+14,y+7,inv,base,'Driver Schottky base clamps','BAT54WS',footprint='Diode_SMD:D_SOD-323')
    sh.text('Driver supplies / rail entry / PON conditioner',300,7,1.3,True)
    for i,ref in gates.items():
        sh.place('HP21xx:74ACT04SCX',310+i*22,29,{'7':'GND','14':'HP_5V'},'HP output hex inverters',value='ACT04',unit=7,ref=ref,compact=True,footprint='Package_SO:SOIC-14_3.9x8.7mm_P1.27mm')
        sh.c(310+i*22,53,'HP_5V','GND','ACT04 local supply bypass','100n')
    edge={str(i):None for i in range(1,87)}
    for c in hp: edge[str(c['contact'])]='HP_C'+str(c['contact'])
    for pins,net in [([1,2,85,86],'GND'),([39,40],'HP_5V'),([47,48],'HP_N2V'),([43,44],'HP_P12V'),([69,70],'HP_N12V')]:
        for n in pins: edge[str(n)]=net
    sh.place('HP21xx:HP_EDGE_86',354,126,edge,'Integrated PCB and HP card-edge fingers',value='HP edge / logical numbering',footprint='',review='Verify physical finger numbering/orientation against mechanical PCB; +28V unused')
    # PON is raw HP contact 66; a separate protocol receiver above also reads it.
    sh.r(305,204,'HP_C66','PON_SER','PON input and reference-bias resistors','470')
    sh.two('Diode:1N4148WS',326,204,'PON_SER','PON_RESET_N','PON signal diodes','4148WS',footprint='Diode_SMD:D_SOD-323')
    sh.r(347,204,'+3V3_HP','PON_RESET_N','PON reset pull-up','1k')
    sh.r(305,225,'+3V3_HP','RESET_CLAMP_REF','PON input and reference-bias resistors','470')
    sh.two('Diode:1N4148WS',326,225,'GND','RESET_CLAMP_REF','PON signal diodes','4148WS',footprint='Diode_SMD:D_SOD-323')
    sh.two('Diode:1N4148WS',350,225,'PON_RESET_N','RESET_CLAMP_REF','PON signal diodes','4148WS',footprint='Diode_SMD:D_SOD-323')
    # Hierarchical ports have same sheet-local names as the captured channel nets.
    sh.port_bank([c['net'] for c in hp]+['PON_RESET_N'],300,244,rows=9,step=2.54,dx=12.7)
    sh.text('Draft: clamp timing/levels; ACT sink currents; 22R load power; edge mapping need review.',12,282,1.0)


def fpga_sheet(sh,fpn):
    sh.text('FPGA pin allocation / Master SPI / clocks / FPGA rails',10,7,1.6,True)
    for unit,(x,y) in enumerate([(70,66),(205,66),(50,137),(185,143)],1):
        sh.place('FPGA_Xilinx_Spartan6:XC6SLX9-TQG144',x,y,fpn,'FPGA',ref='U1',unit=unit,value='XC6SLX9-2TQG144C')
    sh.counter['U']=1
    sh.place('HP21xx:GD25Q16ESIG',115,150,{'1':'FLASH_CS_N','2':'FLASH_MISO','3':'FLASH_WP_N','4':'GND','5':'FLASH_MOSI','6':'FLASH_CLK','7':'FLASH_HOLD_N','8':'+3V3_HP'},'FPGA SPI configuration flash',value='GD25Q16ESIG',footprint='Package_SO:SOIC-8_5.3x5.3mm_P1.27mm',review='Confirm 208mil footprint against GigaDevice drawing')
    for i,n in enumerate(['FLASH_CS_N','FLASH_WP_N','FLASH_HOLD_N']): sh.r(14+i*12.7,177,'+3V3_HP',n,'Flash inactive-state pull-ups','10k')
    for i,n in enumerate(['FPGA_INIT_N','FPGA_DONE']): sh.r(58+i*12.7,177,'+3V3_HP',n,'INIT_B and DONE pull-ups','4.7k')
    sh.r(84,177,'+3V3_HP','FPGA_M0','Master SPI mode straps','10k'); sh.r(97,177,'FPGA_M1','GND','Master SPI mode straps','10k')
    jtag={'1':'GND','2':'+3V3_HP','3':'GND','4':'FPGA_TMS','5':'GND','6':'FPGA_TCK','7':'GND','8':'FPGA_TDO','9':'GND','10':'FPGA_TDI','11':'GND','12':None,'13':None,'14':None}
    sh.place('Connector_Generic:Conn_02x07_Odd_Even',258,140,jtag,'FPGA JTAG header',value='JTAG 2x7 / TME',footprint='',review='Accepted CONNFLY exact footprint and maximum height to verify')
    for i,n in enumerate(['FPGA_TCK','FPGA_TMS','FPGA_TDI']):
        sh.r(180+i*25,172,'MCU_'+n,n,'MCU JTAG branch series resistors','100',90)
        sh.r(180+i*25,187,n,'GND' if n=='FPGA_TCK' else '+3V3_HP','JTAG inactive-state bias','10k')
    regulator(sh,52,222,'+3V3_HP','HP_5V',1); regulator(sh,181,222,'+1V2_FPGA','HP_5V',2)
    sh.caps('FPGA supply-pin bypass',5,'+1V2_FPGA',12,262,cols=5)
    sh.caps('FPGA supply-pin bypass',16,'+3V3_HP',72,262,cols=16)
    for i,rail in enumerate(['+1V2_FPGA','+3V3_HP','+3V3_HP']): sh.c(245+i*13,262,rail,'GND','FPGA rail local bulk','4.7u')
    sh.c(258,239,'+3V3_HP','GND','Configuration flash bypass','100n')
    for i,n in enumerate(['FPGA_LED','+3V3_HP']):
        fn='FPGA LED current limiter' if i==0 else '3.3V regulator power LED resistors'
        led='FPGA activity LED' if i==0 else '3.3V regulator power LEDs'
        sh.r(260+i*18,230,n,f'LED_FP_{i}',fn,'470'); sh.led(260+i*18,244,f'LED_FP_{i}','GND',led)
    sh.r(250,190,'+3V3_HP','CORE_LED_A','1.2V power LED series resistor','470')
    sh.led(267,190,'CORE_LED_A','CORE_LED_C','1.2V regulator power LED')
    sh.place('HP21xx:MMBT2369ALT1G',275,211,{'1':'CORE_LED_B','2':'GND','3':'CORE_LED_C'},'1.2V power LED sensing transistor',value='2369A',footprint='Package_TO_SOT_SMD:SOT-23',compact=True)
    sh.r(250,211,'+1V2_FPGA','CORE_LED_B','1.2V power LED base resistor','1k')
    sh.r(266,211,'CORE_LED_B','GND','1.2V power LED base discharge resistor','100k')
    sh.place('HP21xx:OSC_3V3_50MHz',111,116,{'1':'CLK_OE','2':'GND','3':'OSC50','4':'+3V3_HP'},'Shared 50MHz oscillator',value='50MHz CMOS',footprint='',review='Confirm YXC 3225 pin numbering and footprint')
    sh.place('HP21xx:CDCLVC1104PWR',159,115,{'1':'OSC50','2':'+3V3_HP','3':'CLK0_SRC','4':'GND','5':'CLK2_SRC','6':'+3V3_HP','7':None,'8':'CLK1_SRC'},'Clock fan-out buffer',value='CDCLVC1104',footprint='Package_SO:TSSOP-8_3x3mm_P0.65mm',review='Pin map checked against TI data sheet; supply filter link still to capture')
    sh.r(93,130,'+3V3_HP','CLK_OE','Oscillator OE pull-up','10k')
    for i,n in enumerate(['CLK50_FPGA','CLK50_PHY','ETH_RMII_REF_CLK']): sh.r(201+i*28,116,f'CLK{i}_SRC',n,'Clock output source termination','10',90)


def mcu_sheet(sh,mc,mcn):
    sh.text('STM32F407VG / independent USB recovery domain',9,7,1.5,True)
    sh.place('MCU_ST_STM32F4:STM32F407VGTx',52,96,mcn,'MCU',value='STM32F407VGT6')
    # Independent HSE network; pin numbering is explicit for the four-pad crystal.
    sh.place('Device:Crystal_GND24_Small',24,195,{'1':'HSE_DRIVE','2':'GND','3':'HSE_IN','4':'GND'},'Independent HSE crystal',value='8MHz / CL12p',footprint='',review='Confirm Lucki 5032 crystal pad numbers, CL and drive level')
    sh.r(49,192,'HSE_OUT','HSE_DRIVE','HSE drive-limiting position','0',90)
    sh.c(12,213,'HSE_IN','GND','HSE crystal load capacitors','18p'); sh.c(35,213,'HSE_DRIVE','GND','HSE crystal load capacitors','18p')
    sh.caps('MCU VDD pin bypass',6,'+3V3_MCU',11,240,cols=6)
    sh.c(73,240,'+3V3_MCU','GND','MCU VBAT bypass','100n'); sh.c(86,240,'+3V3_MCU','GND','MCU local bulk','4.7u')
    for i in [1,2]: sh.c(12+i*18,264,'MCU_VCAP_'+str(i),'GND','MCU VCAP capacitors','2.2u/16V')
    sh.two('Device:FerriteBead_Small',73,264,'+3V3_MCU','MCU_VDDA','VDDA filter bead','600R@100M',footprint='Inductor_SMD:L_0603_1608Metric')
    sh.c(88,264,'MCU_VDDA','GND','VDDA local low-frequency bypass','1u')
    sh.c(102,240,'MCU_VDDA','GND','VDDA and VREF+ HF bypass','100n'); sh.c(102,264,'MCU_VDDA','GND','VDDA and VREF+ HF bypass','100n')
    # USB orientation is preserved; both D+ and D- contacts are connected.
    sh.text('HRO USB-C / JLCPCB SMT assembly',104,13,1.2,True)
    unets={p['number']:None for p in S.pins('Connector:USB_C_Receptacle_USB2.0_16P')}
    for p in unets:
        if p in ['A1','A12','B1','B12']: unets[p]='GND'
        elif p in ['A4','A9','B4','B9']: unets[p]='USB_VBUS'
        elif p in ['A6','B6']: unets[p]='USB_DP_CONN'
        elif p in ['A7','B7']: unets[p]='USB_DM_CONN'
    unets.update(A5='USB_CC1',B5='USB_CC2',SH='USB_SHELL')
    sh.place('Connector:USB_C_Receptacle_USB2.0_16P',120,51,unets,'USB-C receptacle',value='HRO TYPE-C-31-M-12',footprint='Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12')
    sh.r(151,25,'USB_CC1','GND','USB-C CC pull-downs','5.1k'); sh.r(165,25,'USB_CC2','GND','USB-C CC pull-downs','5.1k')
    sh.place('Power_Protection:USBLC6-2SC6',164,50,{'1':'USB_DP_CONN','6':'USB_DP_CONN','3':'USB_DM_CONN','4':'USB_DM_CONN','2':'GND','5':'USB_VBUS'},'USB protection',value='GOODWORK USBLC6',review='ST-shaped symbol; verify GOODWORK C21713975 pinout before release')
    sh.r(150,70,'USB_DP_CONN','USB_FS_DP','USB D+/D- series positions','0',90)
    sh.r(175,70,'USB_DM_CONN','USB_FS_DM','USB D+/D- series positions','0',90)
    sh.r(151,88,'USB_VBUS','USB_VBUS_PRESENT','USB VBUS sense upper resistor','1.8k'); sh.r(168,88,'USB_VBUS_PRESENT','GND','USB VBUS sense lower resistor','3.3k')
    sh.r(188,88,'USB_SHELL','GND','USB shell-to-board-ground option','0')
    sh.c(188,65,'USB_VBUS','GND','Connector-side VBUS ESD reference bypass','100n')
    # SD card symbol uses exact 1-11 contact functions; shell footprint is pending.
    sh.place('HP21xx:SD_106M',126,127,{'1':'SDIO_DAT3','2':'SDIO_CMD','3':'GND','4':'+3V3_MCU','5':'SDIO_CK','6':'GND','7':'SDIO_DAT0','8':'SDIO_DAT1','9':'SDIO_DAT2','10':'SD_CARD_PRESENT_N','11':'SD_WRITE_PROTECT'},'Full-size SD holder',value='SD-106M / CD10 WP11',footprint='',review='Exact shell pads, switch commons and SD-106M footprint still to verify')
    for i,n in enumerate(['SDIO_CMD','SDIO_DAT0','SDIO_DAT1','SDIO_DAT2','SDIO_DAT3']): sh.r(103+i*17,169,'+3V3_MCU',n,'SDIO CMD and DAT pull-ups','47k')
    sh.r(155,113,'+3V3_MCU','SD_CARD_PRESENT_N','SD card-detect and write-protect pull-ups','10k')
    sh.r(175,113,'+3V3_MCU','SD_WRITE_PROTECT','SD card-detect and write-protect pull-ups','10k')
    sh.c(155,140,'+3V3_MCU','GND','SD card local supply bulk','4.7u'); sh.c(175,140,'+3V3_MCU','GND','SD card local HF bypass','100n')
    # Schottky OR and third buck.
    sh.two('Device:D_Schottky',120,196,'MCU_VIN','HP_5V','MCU input power OR diodes','SS14',footprint='Diode_SMD:D_SMA')
    sh.two('Device:D_Schottky',152,196,'MCU_VIN','USB_VBUS','MCU input power OR diodes','SS14',footprint='Diode_SMD:D_SMA')
    regulator(sh,151,231,'+3V3_MCU','MCU_VIN',3)
    sh.r(107,266,'+3V3_MCU','MCU_PWR_LED_A','3.3V regulator power LED resistors','470'); sh.led(128,266,'MCU_PWR_LED_A','GND','3.3V regulator power LEDs')
    sh.r(153,266,'+3V3_MCU','MCU_LED_A','MCU LED current limiter','470'); sh.led(174,266,'MCU_LED_A','MCU_LED_N','MCU status LED')
    # SWD and jumpers.
    hdr={str(i):None for i in range(1,21)}
    for i in [1,2]: hdr[str(i)]='+3V3_MCU'
    for i in [3,4,5,6,8,10,12,14,16,18,20]: hdr[str(i)]='GND'
    hdr.update({'7':'SWDIO','9':'SWCLK','15':'MCU_NRST'})
    sh.place('Connector_Generic:Conn_02x10_Odd_Even',224,40,hdr,'STM32 ST-LINK SWD header',value='SWD 2x10 / TME',footprint='',review='Accepted CONNFLY exact footprint to verify')
    for i,net in enumerate(['MCU_BOOT0','DEV_MODE']):
        sh.place('Connector_Generic:Conn_01x02',264+i*24,25,{'1':'+3V3_MCU','2':net},'BOOT0 and DEV jumper headers',value='BOOT0' if i==0 else 'DEV',footprint='Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical',review='Confirm accepted header dimensions and shunt height')
    for i,net in enumerate(['MCU_BOOT0','MCU_BOOT1','DEV_MODE']): sh.r(209+i*22,80,net,'GND','BOOT0 BOOT1 and DEV pull-downs','10k')
    # Hardware HP presence and power-aware PON reset gate.
    sh.place('HP21xx:MMBT2369ALT1G',219,110,{'1':'HP_SENSE_B','2':'GND','3':'HP_ABSENT'},'HP power detector transistor',value='2369A',footprint='Package_TO_SOT_SMD:SOT-23',compact=True)
    sh.r(199,106,'HP_5V','HP_SENSE_B','HP detector base input resistor','47k')
    sh.r(200,125,'HP_SENSE_B','GND','HP detector base discharge resistor','100k')
    sh.r(240,110,'+3V3_MCU','HP_ABSENT','HP detector collector pull-up','10k')
    sh.place('74xGxx:74LVC1G32',231,153,{'1':'PON_RESET_N','2':'HP_ABSENT','3':'GND','4':'MCU_PON_RELEASE','5':'+3V3_MCU'},'MCU PON reset gate',value='SN74LVC1G32',footprint='Package_TO_SOT_SMD:SOT-23-5')
    sh.two('HP21xx:BAT54WS',269,153,'MCU_PON_RELEASE','MCU_NRST','MCU reset isolation Schottky','BAT54WS',footprint='Diode_SMD:D_SOD-323')
    sh.r(264,174,'+3V3_MCU','MCU_NRST','MCU NRST pull-up','10k'); sh.c(283,174,'MCU_NRST','GND','MCU NRST capacitor','100n')
    sh.place('Switch:SW_Push',223,186,{'1':'MCU_NRST','2':'GND'},'MCU reset pushbutton',value='RESET',footprint='',review='Exact XKB switch footprint to verify')
    sh.c(249,186,'+3V3_MCU','GND','MCU reset OR-gate bypass','100n')
    # Capture the selected transceiver with its independently verified pinout.
    serial={1:'HP_P12V',2:'PENDANT_RX_RS232',3:'RS232_RX2',4:'RS232_RX3',5:'PENDANT_TX_RS232',6:'RS232_TX2',7:'RS232_RX4',8:'RS232_TX3',9:'RS232_RX5',10:'HP_N12V',11:'GND',12:'UART_RX5_5V',13:'UART_TX3',14:'UART_RX4_5V',15:'UART_TX2',16:'UART_TX1_5V',17:'UART_RX3_5V',18:'UART_RX2_5V',19:'UART_RX1_5V',20:'HP_5V'}
    sh.place('HP21xx:SN75185DWR',329,49,{str(k):v for k,v in serial.items()},'Externally supplied RS232',value='SN75185DWR',footprint='Package_SO:SOIC-20W_7.5x12.8mm_P1.27mm')
    for i,(rail) in enumerate(['HP_5V','HP_P12V','HP_N12V']): sh.c(310+i*20,93,rail,'GND','SN75185 rail bypass','100n')
    for i,rail in enumerate(['HP_P12V','HP_N12V']): sh.c(317+i*25,111,rail,'GND','SN75185 +/-12V local bulk','1u/50V')
    dual=sh.place('74xGxx:74LVC2G125',332,137,{'1':'UART_ENABLE_N_TBD','2':'USART1_TX','6':'UART_TX1_5V'},'UART level/isolation buffer',value='LVC2G125',unit=1,footprint='Package_SO:VSSOP-8_2.3x2mm_P0.5mm',review='B085 hardware /OE network not yet captured')
    sh.place('74xGxx:74LVC2G125',332,166,{'7':'UART_ENABLE_N_TBD','5':'UART_RX1_5V','3':'USART1_RX'},'UART level/isolation buffer',value='LVC2G125',unit=2,ref=dual,footprint='Package_SO:VSSOP-8_2.3x2mm_P0.5mm')
    sh.place('74xGxx:74LVC2G125',376,142,{'4':'GND','8':'+3V3_MCU'},'UART level/isolation buffer',value='LVC2G125',unit=3,ref=dual,footprint='Package_SO:VSSOP-8_2.3x2mm_P0.5mm')
    sh.c(378,166,'+3V3_MCU','GND','UART buffer local bypass','100n')
    sh.r(365,185,'+3V3_HP','UART_TX1_5V','Pendant UART logic bias and default-disable positions','10k')
    sh.r(390,185,'+3V3_MCU','USART1_RX','Pendant UART logic bias and default-disable positions','10k')
    # Spare line receivers are 5V logic at the SN75185; translate before posts.
    quad=None; quadpins=[('1','2','3'),('4','5','6'),('10','9','8'),('13','12','11')]
    for i,(oe,inp,out) in enumerate(quadpins):
        quad=sh.place('74xx:74LVC125',225+(i%2)*65,241+(i//2)*30,
            {oe:'GND',inp:f'UART_RX{i+2}_5V',out:f'UART_RX{i+2}'},'Spare RS232 receiver translation',
            value='SN74LVC125A',unit=i+1,ref=quad,footprint='Package_SO:TSSOP-14_4.4x5mm_P0.65mm')
    sh.place('74xx:74LVC125',371,241,{'7':'GND','14':'+3V3_HP'},'Spare RS232 receiver translation',
        value='SN74LVC125A',unit=5,ref=quad,footprint='Package_SO:TSSOP-14_4.4x5mm_P0.65mm')
    sh.c(393,242,'+3V3_HP','GND','UART buffer local bypass','100n')
    for i,n in enumerate(['UART_TX2','UART_TX3']):
        sh.r(362+i*25,273,'+3V3_HP',n,'Pendant UART logic bias and default-disable positions','10k')
    sh.text('H10 OPEN: pendant numbered pinout; current limit; /OE hardware gate; connector protection.',202,212,0.9,True)
    sh.text('H06 OPEN: PHY line-side magnetics/straps/ESD and RJ45 selection need circuit review.',202,219,0.9,True)
    sh.text('Ethernet PHY/magnetics capture remains open; no fabricated cable pin numbers.',202,226,0.8)


def expansion_sheet(sh,mc,fpn):
    sh.text('Expansion / reusable FSMC / spare RS-232',10,8,1.8,True)
    sh.text('Logical access pads only. H02: final top connector, posts and numbered contacts remain open.',10,17,1.1)
    sh.text('Do not drive shared FPGA/MCU nets until BOTH endpoints are released. RS-232 is bipolar.',10,23,1.1)
    nets=[fpn[str(p)] for p in [59,61,62,66,67,74]]+[f'FSMC_AD{i}' for i in range(16)]+['FSMC_NOE','FSMC_NWE','FSMC_NADV']
    nets += ['MCU_'+r['Pin_name'] for r in mc if r['Usage']=='UNCOMMITTED']
    nets += ['UART_TX2','UART_TX3']+[f'UART_RX{i}' for i in range(2,6)]
    nets += ['RS232_TX2','RS232_TX3']+[f'RS232_RX{i}' for i in range(2,6)]
    sh.port_bank(nets,15,40,rows=25,step=7.62,dx=125)
    for i,n in enumerate(nets):
        # Accessible net labels, not fictitious unselected connector contacts.
        x=78+(i//25)*125; y=40+(i%25)*7.62
        sh.place('Connector:TestPoint',x,y,{'1':n},'Configuration and rail test pads',value=n,footprint='',compact=True,review='Logical access placeholder; final top contact/post or PCB pad at H02')
    for i,n in enumerate(['+3V3_HP','+3V3_MCU','+1V2_FPGA','HP_5V','GND','HP_P12V','HP_N12V']):
        sh.place('Connector:TestPoint',30+i*52,253,{'1':n},'Configuration and rail test pads',value=n,footprint='',compact=True,review='Supply access position/count pending layout')
    sh.text('This sheet does not invent a production connector footprint or contact allocation.',10,276,1.2,True)


def capture(force=False):
    if (OUT/'HP21xx_IO.kicad_sch').exists() and not force:
        raise SystemExit('Schematic exists; preserve manual edits before invoking --force.')
    OUT.mkdir(parents=True,exist_ok=True); aliases()
    fp,mc,fpn,mcn,hp=read_maps()
    root=Sheet('FPGA',1); stm=Sheet('STM32',2); host=Sheet('HP_Interface',3); exp=Sheet('Expansion',4)
    fpga_sheet(root,fpn); hp_sheet(host,hp); mcu_sheet(stm,mc,mcn); expansion_sheet(exp,mc,fpn)
    # FPGA/MCU transport disconnect links and series JTAG branches are on the root.
    transport=[f'FSMC_AD{i}' for i in range(16)]+['FSMC_NOE','FSMC_NWE','FSMC_NADV','FPGA_AUX1','FPGA_AUX2']
    for i,n in enumerate(transport):
        root.r(32+(i%11)*24,272 if i<11 else 283,'MCU_'+n,n,'FSMC and AUX disconnect links','0',90)
    stm_shared=['MCU_'+n for n in transport]+['MCU_FPGA_TCK','MCU_FPGA_TMS','MCU_FPGA_TDI','FPGA_TDO','FPGA_DONE','PON_RESET_N','ETH_RMII_REF_CLK','CLK50_PHY']
    stm_shared += ['MCU_'+r['Pin_name'] for r in mc if r['Usage']=='UNCOMMITTED']
    stm_shared += ['UART_TX2','UART_TX3']+[f'UART_RX{i}' for i in range(2,6)]+['RS232_TX2','RS232_TX3']+[f'RS232_RX{i}' for i in range(2,6)]
    stm.port_bank(stm_shared,202,235,rows=17,step=2.54,dx=45)
    # Root child-sheet borders occupy a separate right-hand area.
    root.child(stm,306,19,25,108); root.child(host,368,19,25,108); root.child(exp,335,149,25,95)
    for i,n in enumerate(['HP_5V','HP_N2V','HP_P12V','HP_N12V','GND']):
        host.place('power:PWR_FLAG',304+i*18,191,{'1':n},value=n,compact=True)
    for sh,rail,x,y in [(root,'+3V3_HP',231,252),(root,'+1V2_FPGA',231,238),(stm,'+3V3_MCU',184,249),(stm,'MCU_VIN',183,196),(stm,'USB_VBUS',182,22),(stm,'MCU_VDDA',91,281)]:
        sh.place('power:PWR_FLAG',x,y,{'1':rail},value=rail,compact=True)
    root.text('Initial capture: review pin maps and draft circuits before PCB work.',12,12,1.0)
    for sh in [root,stm,host,exp]: sh.save()
    custom='(kicad_symbol_lib (version 20241209) (generator "kicad_symbol_editor")\n'+'\n'.join(sexp([*d[:1],k.split(':')[1],*d[2:]]) for k,d in S.custom.items())+'\n)\n'
    (OUT/'HP21xx.kicad_sym').write_text(custom)
    (OUT/'sym-lib-table').write_text('(sym_lib_table (lib (name "HP21xx") (type "KiCad") (uri "${KIPRJMOD}/HP21xx.kicad_sym") (options "") (descr "Project pin-map symbols and verified standard aliases")))\n')
    (OUT/'HP21xx_IO.kicad_pro').write_text(json.dumps({'meta':{'filename':'HP21xx_IO.kicad_pro','version':1},'net_settings':{'classes':[{'name':'Default','clearance':0.2,'track_width':0.25,'via_diameter':0.6,'via_drill':0.3}],'version':3},'schematic':{'meta':{'version':1}}},indent=2)+'\n')
    (OUT/'capture_manifest.json').write_text(json.dumps(CAPTURE,indent=2)+'\n')
    print(f'Generated four A3 sheets; {len(CAPTURE)} symbol units, {len(set(c["reference"] for c in CAPTURE))} references.')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--inspect',action='store_true'); ap.add_argument('--force',action='store_true')
    args=ap.parse_args()
    if args.inspect: inspect()
    else: capture(args.force)
