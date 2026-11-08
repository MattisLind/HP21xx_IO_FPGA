#!/usr/bin/env python3
"""Check the exported KiCad netlist against the initial capture manifest.

Export a fresh netlist/ERC report first; see hardware/integrated/README.md.
This checks connectivity, not analog/timing behavior or PCB manufacture.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from kicad_capture import ROOT, OUT, atomize, one, sub


def check(netlist, erc):
    capture=json.loads((OUT/'capture_manifest.json').read_text())
    native=atomize(Path(netlist).read_text())
    expected={}
    for c in capture:
        if c['reference'].startswith('#'): continue
        for pin,net in c['pins'].items():
            if net is not None:
                key=(c['reference'],pin)
                assert key not in expected or expected[key]==net, key
                expected[key]=net
    actual={}; merges=[]
    for n in one(native,'nets')[1:]:
        labels=defaultdict(list)
        for node in sub(n,'node'):
            key=(one(node,'ref')[1],one(node,'pin')[1])
            if key in expected:
                labels[expected[key]].append(key)
                actual[key]=one(n,'name')[1]
        if len(labels)>1: merges.append(dict(net=one(n,'name')[1],expected=dict(labels)))
    assert not merges, f'Unintended net merges: {merges}'
    missing=set(expected)-set(actual)
    assert not missing, f'Pins lost from exported netlist: {sorted(missing)}'

    byref=defaultdict(list)
    for c in capture: byref[c['reference']].append(c)
    plan=list(csv.DictReader((ROOT/'requirements/INTEGRATED_BOARD_BOM.csv').open()))
    ids={r['Function']:r['Item'] for r in plan}
    counts=Counter()
    for units in byref.values():
        if units[0]['bom_item']: counts[units[0]['bom_item']]+=1
    for fn,n in [('HP receiver transistors',43),('HP output emitter transistors',24),
                 ('HP output hex inverters',4),('Independent buck stages',3),
                 ('FPGA supply-pin bypass',21),('MCU VDD pin bypass',6),
                 ('MCU VCAP capacitors',2),('FSMC and AUX disconnect links',21),
                 ('MCU JTAG branch series resistors',3),('3.3V regulator power LEDs',2),
                 ('1.2V regulator power LED',1)]:
        assert counts[ids[fn]]==n,(fn,counts[ids[fn]],n)
    for fn,n in [('FPGA',144),('MCU',100)]:
        units=[c for c in capture if c['bom_item']==ids[fn]]
        assert len({p for c in units for p in c['pins']})==n
    # Verify the actual pads used by the accepted USB footprint, not only labels.
    usb=next(c for c in capture if c['bom_item']==ids['USB-C receptacle'])
    assert usb['footprint']=='Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12'
    assert usb['pins']['A6']==usb['pins']['B6']=='USB_DP_CONN'
    assert usb['pins']['A7']==usb['pins']['B7']=='USB_DM_CONN'
    assert usb['pins']['A5']=='USB_CC1' and usb['pins']['B5']=='USB_CC2'
    for filename in ['HP21xx_IO','STM32','HP_Interface','Expansion']:
        sch=atomize((OUT/(filename+'.kicad_sch')).read_text())
        assert one(sch,'paper')[1]=='A3'
    # Validate hierarchical references exported by KiCad, including root.
    assert len(sub(one(native,'design'),'sheet'))==4

    violations=[v for s in json.loads(Path(erc).read_text())['sheets'] for v in s['violations']]
    summary=Counter(v['type'] for v in violations)
    # Allow no generated grid errors, accidental NCs, or missing footprint links.
    for problem in ['endpoint_off_grid','no_connect_connected','footprint_link_issues']:
        assert not summary[problem],(problem,summary[problem])
    coverage=[]
    for row in plan:
        n=counts[row['Item']]
        want=row['Quantity']
        if row['Fit'] in ['PCB feature','DNP','Alternative']:
            state='PCB feature / not fitted'
        elif not want: state='Unresolved quantity'
        elif n==int(want): state='Count captured; circuit/footprint review remains'
        elif n==0: state='Not captured yet'
        else: state='Partial capture / reconcile count'
        coverage.append(dict(Item=row['Item'],Function=row['Function'],Planned_quantity=want,
                             Captured_references=n,
                             Captured_designators='; '.join(ref for ref,units in byref.items() if units[0]['bom_item']==row['Item']),
                             Status=state))
    with (OUT/'bom_capture_coverage.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=coverage[0].keys(),lineterminator='\n'); w.writeheader();w.writerows(coverage)
    report=dict(kicad_version='10.0.5',drawing_sheets=4,paper='A3',symbol_units=len(capture),
        annotated_references=len(byref),checked_exported_pins=len(actual),unintended_net_merges=0,
        erc_errors=sum(v['severity']=='error' for v in violations),
        erc_warnings=sum(v['severity']=='warning' for v in violations),erc_by_type=dict(summary),
        release_status='Initial capture; incomplete; not for PCB manufacture',
        limitations=['Ethernet PHY/magnetics/straps/protection circuit not captured',
            'Pendant connector pinout/current limiting/protection and hardware /OE network not captured',
            'Selected connector, crystal, flash, oscillator and inductor footprints require exact drawing review',
            'Expansion access is logical test-pad placeholders; top connector/post allocation open',
            'Coverage CSV lists every BOM item not yet or only partially captured'])
    (OUT/'capture_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--netlist',default='build/bom-review/initial-schematic.net')
    p.add_argument('--erc',default='build/bom-review/initial-erc.json')
    a=p.parse_args();check(a.netlist,a.erc)
