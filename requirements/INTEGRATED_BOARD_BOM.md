# Integrated-board BOM notes

Revision 0.9, 2026-11-08. Companion to the
[design review](INTEGRATED_BOARD_DESIGN.md).

The [functional CSV](INTEGRATED_BOARD_BOM.csv) is the editable master: 144
lines describe the board's devices and support circuits. The
[purchasing CSV](INTEGRATED_BOARD_PURCHASING_BOM.csv) groups identical parts
and sums their quantities into 76 lines. Its `Functional_items` column links
each total back to the master. There are 60 distinct LCSC identities and
seven TME ordering codes. Neither file is a released assembly BOM: the
integrated schematic and PCB placement do not yet exist.

## Reading the CSVs

- `Quantity` means fitted pieces per board, excluding buying multiples,
  assembly attrition and spares. A blank quantity means unresolved, never zero.
- `Quantity_basis` distinguishes channel-derived counts, explicit design
  requirements and provisional placement allowances. Initial bypass counts,
  bulk capacitors and signal-conditioning positions must be reconciled with
  the schematic and layout.
- `Fit=DNP` means zero initially fitted parts; the notes identify reserved
  footprints. `Fit=PCB feature` means copper pads, not purchased hardware.
- `Selected` retains the agreed device or topology. `Proposed` identifies a
  new support-part selection awaiting circuit/footprint review. Neither status
  claims electrical validation. `TBD` identifies an unresolved design or
  sourcing decision explicitly instead of supplying an invented part number.
- `Library_status` distinguishes a checked JLCPCB listing, an LCSC identity
  whose JLCPCB assembly eligibility still needs checking, and a mapping
  inherited from the earlier design review. An LCSC number alone does not
  establish JLCPCB assembly availability. Exact manufacturer and package
  must match; similarly named parts from another manufacturer are not assumed
  interchangeable.
- `Catalog_URL` and `Datasheet_URL` provide source references. Research was
  performed on 2026-11-08; accessible pages include cached regional listings.
  Stock, prices, Basic/Extended classification and assembly eligibility need
  a refresh at ordering. Stock counts are deliberately not frozen into the BOM.

No reference designators or placement coordinates have been invented. Add
these from the actual schematic and PCB before generating a JLCPCB upload
and placement file. The purchasing CSV is for procurement planning; it does
not supply missing references or certify the proposed circuitry.

## Scope and count derivation

The scope is one integrated HP 21xx I/O board: FPGA, STM32, all 43 HP receiver
channels and 24 output-driver channels, three buck supplies, clock/reset
support, USB-C, full-size SD, pendant RS-232 and spare channels, Ethernet,
debug headers, configuration jumpers and expansion provisions. It does not
include a separate pendant PCB, external programmers, cables or an SD card.
Those accessories need their own selected designs or procurement requirements.

The HP interface is derived from the locally saved
`build/reference/receiver-driver/netlist.xml` topology and design section 3.2.5:

| Circuit | Per channel | Board total |
| --- | --- | --- |
| Receiver | One NPN, one reverse-BE clamp diode, 1 kΩ base series, 2 kΩ input termination, 220 Ω collector pull-up | 43 of each |
| Driver | One NPN, one Schottky base clamp, 22 Ω collector feed, 220 Ω base bias, 2 kΩ logic-input pull-up | 24 of each |
| Driver logic | Six ACT inverters per IC | Four 74ACT04 ICs |

This is a topology reference, not a claim that the saved netlist is the
newest upstream revision. Its driver-input pull-ups still connect to +5 V;
the BOM explicitly uses the corrected **+3V3_HP** connection. The module's
LDOs and DIP carrier connectors are omitted because the integrated board
supplies those rails centrally. Driver 220 Ω bias resistors are proposed in
1206 / 0.25 W rather than the source's 0402 package, because the estimated
inactive dissipation is about 90 mW per channel.

The HP circuits use 67 MMBT2369A-family transistors; a separate proposed HP
power detector and the 1.2 V power LED sensing transistor reuse that part,
making 69 in the purchasing view. Receiver
diodes are proposed as 1N4148WS/SOD-323 and Schottkys as DIOTEC
BAT54WS/SOD-323. The source's `BAT54J` value, SOD-523 footprint and LCSC
field are not a consistent ordering identity; they are not copied blindly.
Verify the proposed substitutions' forward drops, dynamics and footprints.

Initial FPGA bypass allowance is **21 × 100 nF**, based on five VCCINT,
five VCCAUX and eleven VCCO pins in the package-pin CSV. Initial MCU bypass
allowance is **six VDD capacitors**, plus separate VBAT, analog supply and
VCAP support. These are explicit planning counts, subject to manufacturer
PDN guidance and actual placement. Bulk capacitors are additional local
positions, not accidental copies of the regulator output capacitors.

## Sourcing and cost choices

Electrically through-hole parts are assigned to **TME**, including unresolved
expansion hardware. The user-selected **HRO TYPE-C-31-M-12/C165948 USB-C**
connector is supplied and soldered by **JLCPCB** in SMT assembly, including
its specified retention footprint. SMT components use **JLCPCB** where matched. The custom PCB and
its HP edge fingers are fabrication items, not a purchased card-edge socket.

- Pendant: **Molex 95501-2441**, TME **MX-95501-2441**, 11.5 mm nominal.
- Ethernet jack: **Adam Tech MTJ-885X1**, TME **MTJ-885X1**, about 11.7 mm
  nominal; unshielded, no magnetics, no LEDs. TME showed no stock, so its
  orderability is an explicit procurement gap. Do not substitute a taller
  jack without mechanical review.
- External Ethernet magnetics: **Pulse H1102NLT, C18584**, JLCPCB Extended.
  Pulse lists LAN8720A among compatible PHYs. The 12.7 × 7.1 mm catalog body
  does not describe the full lead span; use the manufacturer footprint.
- Seven board LEDs use the accepted **KT-0603R/C2286** type, each with a
  separate **470 Ω/C23179** resistor: FPGA, MCU, Ethernet link/activity,
  Ethernet speed/status, +3V3_HP, +3V3_MCU and +1V2_FPGA power indication.
  PHY LED polarity and strap sampling still need circuit review. The 1.2 V
  indicator uses the sensing circuit below.
- Common 100 nF capacitors use **YAGEO CC0603KRX7R9BB104/C14663**, verified
  as JLCPCB Basic, instead of the earlier Samsung C1591 Extended listing.
  Both are nominal 100 nF / 50 V / X7R / 10% / 0603. Common resistors, LEDs
  and links use checked Basic listings where available to reduce feeder fees.
- User-accepted low-cost TME debug headers are CONNFLY **ZL231-14PG** and
  **ZL231-20KG**, replacing the unspecified FPGA header and Samtec SWD
  purchasing choice. Verify installed height, pin numbering, cable keying
  and mating clearances.
- USB-C is restored to **HRO TYPE-C-31-M-12/C165948**, accepted for supply
  and SMT soldering by JLCPCB. The GCT/TME proposal is removed from both CSVs.
- The **100 nF C14663** capacitors, **C2286 LEDs**, debug headers and
  **Pulse H1102NLT/C18584** external magnetics are recorded as accepted.

### Regulator power LEDs

Each independent 3.3 V output has a rail -> 470 Ω -> red LED -> GND
indicator. A red LED cannot run directly from the 1.2 V output. Its indicator
therefore uses **+3V3_HP -> 470 Ω -> LED -> NPN collector**, emitter to GND,
with **1 kΩ from +1V2_FPGA to base** and **100 kΩ from base to GND**.
The proposed NPN is the existing MMBT2369ALT1G/C94404. This indicator needs
+3V3_HP as well as the 1.2 V rail; it is a presence indicator, not a calibrated
undervoltage detector. Check startup, low-current gain and visibility on hardware.
Allocate approximately 3 mA for each LED branch and up to 0.6 mA for core-rail
base drive. The core LED branch itself loads +3V3_HP.

### Additional TME RJ45 research

| Part | Installed-height information | Assessment |
| --- | --- | --- |
| **Molex 85503-5001 / MX-85503-5001** | **11.5 mm nominal**; 1.3 mm nominal headroom | **Recommended stocked alternative**: Cat 5e, unshielded, right-angle THT, PCB retention, no LEDs/magnetics. TME showed stock; indicative net US$2.14 at one, US$1.85 at ten. Manufacturer maximum-height drawing and footprint still need approval. Recorded as a zero-quantity alternative, pending user selection. |
| Adam Tech MTJ-880X1 | 0.498 inch (about 12.65 mm) catalog family height | Only about 0.15 mm nominal headroom; insufficient margin to approve without maximum installed-height drawing. TME showed no stock. |
| Adam Tech MTJ-889X1 | About 12.3 mm nominal | Unshielded THT, less margin than MTJ-885X1; TME showed no stock. |
| TE 1116503-2 | 9.58 mm catalog height | Rejected for this request: manufacturer confirms a metal shield; TME showed no stock. |
| TE 1-1705951-1 | 11.5 mm nominal | Stocked and cheaper (indicative US$1.25 at one), but cataloged Cat 3 rather than Cat 5e; not recommended for this 100BASE-TX interface without manufacturer qualification. |

[Molex at TME](https://www.tme.eu/en/details/mx-85503-5001/rj-connectors/molex/85503-5001/),
[Molex height/retention/shielding specifications](https://www.molex.com/en-us/products/part-detail/855035001),
[Adam Tech catalog](https://app.adam-tech.com/resources/download/65/ecatalog-2025-1.pdf),
[MTJ-880X1 at TME](https://www.tme.eu/en/details/mtj-880x1/rj-connectors/adam-tech/),
[TE shield specification](https://www.te.com/en/product-1116503-2.html),
[TE Cat 3 listing](https://www.tme.eu/en/details/1-1705951-1/rj-connectors/te-connectivity/).
Prices/availability are regional page observations, not a guaranteed live quote.


The connector heights above are nominal, not maximum tolerance acceptance.
The installed limit remains **12.8 mm above the 1.6 mm PCB**. Header/shunt
heights, connector latch access and adjacent-card solder tails must also be
checked. Most small SMT parts have ample nominal headroom, but their exact
mechanical drawings still govern footprints and installed heights.

Useful primary sourcing references:

- [Pulse magnetics at JLCPCB](https://jlcpcb.com/partdetail/PulseElec-Pulse_ElecH1102NLT/C18584)
  and [Pulse LAN8720A compatibility/height](https://productfinder.pulseeng.com/product/H1102NL).
- [Unshielded THT jack at TME](https://www.tme.eu/en/details/mtj-885x1/rj-connectors/adam-tech/).
- [Basic common bypass capacitor](https://jlcpcb.com/partdetail/C14663).
- [ACT04 JLCPCB category listing](https://jlcpcb.com/parts/2nd/Logic/Inverters_2567).

## Decisions still needed before release

The master has six explicit TBD lines: the final hardware UART isolation
enable connection, pendant current-limit resistor, cable-side Ethernet
protection network, expansion connector, wire-wrap posts and card mounting
hardware. Some have no fixed quantity because the circuit or mechanical
layout is not yet specified. The pendant TVS, current-limit switch and
other proposed protection parts also need electrical coordination, not just
an ordering identity.

The expansion requirement includes 25 FPGA/shared nets, 25 MCU spare nets,
six spare RS-232 logic nodes, six RS-232 line nodes, grounds and supply access.
Do not count AUX1/AUX2 twice. The top connector allocation and proper
wire-wrap post fit/height are layout decisions; the prototype's 5,379 pad
count is not a requirement to buy 5,379 posts.

The PHY reset proposal uses **TPS3808G33DBVR/C43698** with **100 kΩ from
CT to VDD**, selecting 300 ms typical / 180 ms minimum delay. Leaving CT
open gives only 12 ms minimum and does not meet the PHY's 25 ms requirement.
This is a support-circuit proposal; verify supply ramp, external clock,
straps and MCU reset interaction in the schematic.

Reconcile every line with schematic references; validate resistor dissipation,
capacitor bias/ESR, crystal startup, isolation/ESD topology and partial-power
behavior; then refresh exact JLCPCB/TME orderability and buying quantities.
Regenerate the purchasing view after any functional-BOM change.
