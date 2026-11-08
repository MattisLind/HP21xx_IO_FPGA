# Integrated-board power calculation and component selection

Revision **0.8 — 2026-11-08 — for review**. Companion to
[INTEGRATED_BOARD_DESIGN.md](INTEGRATED_BOARD_DESIGN.md).

The HP supply ratings supplied by the user are **4.85 V / 50 A** and
**−2 V / 15 A** for the machine. These establish available source capacity,
not the current rating of an individual card-edge contact or this PCB.
The board also has +12 V and −12 V available for RS-232. +28 V is unused.

## 1. Recommended supply arrangement

Use three independent buck stages: **TI TLV62569DBVR, C141836,
SOT-23-5, 2 A** for all three; their feedback dividers set their different
voltages. Complete the regulator support components and layout during schematic capture.
Its 2.5–5.5 V input range accommodates the diode-reduced MCU supply; a part
requiring at least 4.5 V input would have little or no margin on that branch.
[TI data sheet](https://www.ti.com/lit/ds/symlink/tlv62569.pdf),
[JLCPCB listing](https://jlcpcb.com/partdetail/TLV62569DBVR/C141836).

| Rail | Source | Loads | Calculated/planning load | Regulator rating |
| --- | --- | --- | --- | --- |
| `+3V3_HP` | HP 4.85 V | FPGA VCCO/VCCAUX, receivers, driver bias, flash, shared clock and Ethernet | **1.21 A including 50 mA shared clock and 200 mA Ethernet allowances** | 2 A buck |
| `+1V2_FPGA` | HP 4.85 V | FPGA VCCINT | Allocate 1.0 A initially; actual demand needs Xilinx Power Estimator and measurement | 2 A buck |
| `+3V3_MCU` | Schottky-OR of HP 4.85 V and USB VBUS | STM32, SD card, MCU-side bias/LED/support | 0.50 A planning allowance | Separate 2 A buck; 1 A would also cover this allowance |

The 2 A rating is capacity, not a prediction of continuous consumption.
FPGA current depends on the loaded design, I/O loading and clocks; the 1 A
core allowance and 200 mA auxiliary/I/O allowance below are engineering
allocations, not data-sheet maximums. Recheck for each supported platform
profile. The receiver pull-up calculation is based on actual resistor values.
[Spartan-6 electrical requirements](https://docs.amd.com/api/khub/documents/5xGMdRIxMi0ioQ1azGBsvQ/content).

```text
HP 4.85 V ------------------------> buck -> +3V3_HP
          +-----------------------> buck -> +1V2_FPGA
          +---->|----+
USB VBUS ------>|----+--> MCU_VIN -> separate buck -> +3V3_MCU
            power Schottkys

+3V3_HP   -> FPGA/interface and Ethernet PHY/clock/magnetics drive
HP 4.85 V -> HP output-driver circuits and protected pendant +5 V
HP ±12 V  -> RS-232 transceiver
HP −2 V   -> receiver input termination
```

Both diode **anodes face their sources**, with cathodes joined at `MCU_VIN`.
Use **MDD SS14/C2480**, SMA, **1 A / 40 V**, for both OR diodes.
Their catalog/data-sheet forward limit is 0.55 V at 1 A; 0.35 V is the planning
estimate at the approximately 0.41 A operating input. Verify hot leakage and
copper temperature. The 1 A input path is sized for the **500 mA at 3.3 V**
MCU-domain budget; it does not expose the buck IC's full 2 A output capability.
At the MCU/SD allowance this gives about 0.41 A through the selected input
diode and **0.14 W** diode loss. The higher source wins; this arrangement does
not prioritize HP power if USB is higher.

Keep the three outputs separate. USB powers the MCU recovery domain; it must
not energize the FPGA, HP output drivers, pendant or backplane through either
power wiring or GPIO/reset paths. SD is on `+3V3_MCU` so the resident loader can access it during bench recovery. Enable SD only within the USB
source's permitted current/inrush budget. Rd resistors alone do not establish
permission to draw 1.5 A or 3 A. Account for USB enumeration and suspend.

## 2. Pull-ups and the FPGA-side 3.3 V load

The inspected
[receiver/driver source](https://github.com/MattisLind/HP21xxReceiverDriver/tree/fc92e9d4aa22cc9dab332444d343fde6f802ec13)
uses **220 Ω receiver collector pull-ups to 3.3 V**, **2 kΩ driver logic-input
pull-ups to 3.3 V**, and **220 Ω driver base-bias resistors from +5 V**.
The integrated board needs 43 receiver and 24 driver channels.

For a conservative pull-up calculation, take the sinking transistor/output
voltage as zero: `I = N × V / R`. This overestimates current slightly.

| Load on `+3V3_HP` | Calculation or allocation | Current |
| --- | --- | --- |
| 43 receiver pull-ups, all sinking | `43 × 3.3 / 220` | **645.0 mA** |
| 24 driver-input pull-ups, all pulled low | `24 × 3.3 / 2000` | **39.6 mA** |
| Transport/startup bias allowance | Upper allowance equivalent to `19 × 3.3 / 4700`; actual fitted pull-ups to be enumerated | 13.4 mA |
| PON conditioner | `3.3 / 470 + 3.3 / 1000`, conservative | 10.4 mA |
| FPGA VCCAUX plus VCCO internal/switching load, excluding the external resistor currents above | Planning allocation pending power estimate | 200 mA |
| Configuration flash, including programming | GD25Q16E industrial-grade program/erase maximum | 25 mA |
| Shared oscillator plus fan-out | Source and three buffered 50 MHz branches; see section 9 | 50 mA |
| FPGA LED | Allocation; final resistor depends on LED voltage/brightness | 5 mA |
| Other bias, support and expansion reserve | Includes about 6 mA for HP 3.3V and core-presence power LED branches | 25 mA |
| Existing FPGA/interface subtotal | Before Ethernet | **1,013.4 mA** |
| Ethernet PHY, magnetics drive and LEDs | New engineering allowance; see section 7 | **200 mA** |
| **Total shared HP-side 3.3 V rail** | Including Ethernet | **1,213.4 mA ≈ 1.21 A** |

Do not increase the 220 Ω values simply to reduce consumption without
checking receiver rise time, loading and HP bus timing. At all 43 receivers
low, the pull-up network alone dissipates **2.13 W**, distributed across the
resistors: `3.3² / 220 = 49.5 mW` each. Select resistor packages with suitable
temperature derating; 0603 or 0805 provides more margin than a 62.5 mW 0402.
Also verify receiver transistor collector/base drive at this load.

An LDO supplying the revised 1.2134 A rail from 4.85 V would dissipate
`(4.85 − 3.3) × 1.2134 = 1.88 W`. At assumed 90% buck efficiency, regulator
loss is about `3.3 × 1.2134 × (1/0.9 − 1) = 0.44 W`. This motivates a buck
even though the HP has ample input current available. Efficiency here is an
estimate, not a guaranteed value for the final layout.

## 3. MCU, SD and 1.2 V allowances

Budget **150 mA for STM32**, **300 mA for the SD card**, and **50 mA for
LED/bias/other MCU-side support**, totaling 500 mA at 3.3 V. These are design
allowances; the chosen card must meet the operating/transient limit. A full-size
socket does not set a card's current consumption. At 4.50 V after the Schottky
and 90% conversion efficiency, input current is
`3.3 × 0.50 / (4.50 × 0.90) = 0.407 A`.

Recheck the 150 mA MCU allowance with Ethernet MAC/DMA active. The PHY and
line-side allowance is on the HP-side rail, outside the USB recovery domain.

That load is close enough to a USB 2.0 500 mA allowance that inrush, pre-
enumeration operation and SD load scheduling need explicit firmware/power-path
design. The buck's 2 A capability does not authorize drawing 2 A from USB.
With a low USB input of 4.4 V and an assumed diode drop of 0.4 V, 4.0 V remains
at the regulator input, comfortably above its 2.5 V minimum and above 3.3 V;
include cable, protection and diode worst cases in the schematic check.

For 1.2 V at the provisional 1.0 A core allowance, an LDO from 4.85 V would
dissipate **3.65 W**. A buck at an assumed 85% efficiency loses about **0.21 W**.
The 2 A stage leaves capacity for startup and other FPGA designs,
but is not a substitute for a device/design-specific startup/dynamic check.

### 3.1 Selected buck support components

Use the same LC topology for all three **TLV62569DBVR** stages. These are
circuit selections; nominal values alone do not replace layout, bias and
transient validation. [TI design procedure, sections 8.2.2.2–8.2.2.5][buck-ds].

| Component | Selection | Per stage / total |
| --- | --- | --- |
| Inductor | **Bourns SRP5030T-2R2M/C1329375**, 2.2 µH ±20%, shielded, 5.7 × 5.2 mm, 3.0 mm maximum height | 1 / **3** |
| Input ceramic | **Murata GRM21BR71A475KA73L/C86039**, 4.7 µF, 10 V, X7R, ±10%, 0805 | 1 / **3** |
| Input HF bypass | **YAGEO CC0603KRX7R9BB104/C14663**, 100 nF, 50 V, X7R, ±10%, 0603 | 1 / **3** |
| Output ceramic | **Samsung CL31A226KAHNNNE/C12891**, 22 µF, 25 V, X5R, ±10%, 1206 | 1 / **3** |
| EN link | **UNI-ROYAL 0603WAF0000T5E/C21189**, 0 Ω, 0603, EN to that stage's VIN | 1 / **3** |
| Optional feed-forward position | Small capacitor footprint across upper feedback resistor, **DNP initially** | 1 footprint per stage |

The 2.2 µH / 22 µF nominal combination is in TI's validated LC matrix for
both 1.2 V and 3.3 V. Preserve at least the allowed effective capacitance
through tolerance, temperature and DC bias; account for all downstream rail
capacitance, including distributed bypassing and the SD card, in the final LC
and load-step check; TI's table anticipates up to 50%
capacitance reduction. Check the chosen MLCC curves at actual bias and fit
additional output capacitance only after checking the LC/transient response.
X5R is suitable for the intended board temperature range; thermal acceptance
includes the capacitors' 85°C limit.

The **SRP5030T-2R2M** manufacturer ratings are **35 mΩ maximum DCR,
5.5 A Irms and 9 A Isat**. At 4.85 V/1.5 MHz, ripple is approximately
**0.32 A peak-to-peak at 3.3 V** and **0.27 A at 1.2 V**. A 2 A output
has about 2.16 A nominal peak. An additional design check using 5.5 V input,
1.54 µH effective inductance and an assumed 1.2 MHz switching frequency
gives about **2.36 A peak** at 3.3 V/2 A. The frequency is an engineering
sensitivity case, not a specified minimum. The selected inductor has ample
current headroom; verify hot saturation and actual switch-current limit.
[Bourns data sheet][inductor-ds].

### 3.2 Feedback and startup connections

`VOUT = 0.6 × (1 + Rupper/Rlower)`; use **1%, 0603 Yageo RC** resistors:

| Stage | Upper resistor: output to FB | Lower resistor: FB to GND | Nominal output |
| --- | --- | --- | --- |
| `+3V3_HP` | **RC0603FR-07330KL**, 330 kΩ | **RC0603FR-0773K2L**, 73.2 kΩ | **3.3049 V** |
| `+3V3_MCU` | **RC0603FR-07330KL**, 330 kΩ | **RC0603FR-0773K2L**, 73.2 kΩ | **3.3049 V** |
| `+1V2_FPGA` | **RC0603FR-07100KL**, 100 kΩ | **RC0603FR-07100KL**, 100 kΩ | **1.200 V** |

Thus the two 3.3 V stages need two 330 kΩ and two 73.2 kΩ resistors; the
1.2 V stage needs two 100 kΩ. Keep each feedback divider close to FB and
route its output sense after the inductor, away from SW. The IC integrates
its switching MOSFETs and soft start. EN is tied to VIN through the fitted
0 Ω link; provide access for controlled startup/supervision if required.
Use the **DBVR five-pin symbol**, which has no power-good output.

Place the input ceramic/HF bypass directly at VIN–GND, keep the SW/inductor
loop compact, and connect output returns with short wide copper. Use ground
planes and thermal copper. Verify input transients, USB plug-in/inrush,
output overshoot, load steps and cross-domain reset sequencing on the PCB.

### 3.3 Local MCU and reset supply support

At the MCU use **CL10A225KO8NNNC/C23630**, 2.2 µF/16 V X5R, at each VCAP
pin, plus **CC0603KRX7R9BB104/C14663** at each VDD and a local **4.7 µF
GRM21BR71A475KA73L** bulk capacitor. Apply the ST VDDA/VREF decoupling rules.
At MCU_NRST fit **10 kΩ (the BOM proposes UNI-ROYAL C25804)** to +3V3_MCU,
**100 nF C14663 to GND**, reset button and BAT54 anode. The BAT54 cathode connects to the PON
branch through **SN74LVC1G32DBVR** on +3V3_MCU, implementing
`PON_RESET_N OR HP_ABSENT`; use a local 100 nF bypass at the gate.
The local RC does not release a reset held low by an unpowered PON branch.
[Reset gate][reset-ds].

## 4. Direct HP loads and total input estimate

The +5 V driver base-bias load is separate from the 3.3 V pull-ups. With a
provisional 0.4 V Schottky/output clamp, 24 inactive channels draw
`24 × (4.85 − 0.4) / 220 = 0.485 A` directly from HP +5 V. A 220 Ω resistor
then dissipates about **90 mW**. Do not blindly copy a 62.5 mW 0402 footprint
for these resistors; the expanded BOM proposes 1206 / 0.25 W for
additional margin. Verify hot derating.
Include the ACT gate sink currents and transistor loading in the circuit
review. The TI ACT04 data sheet permits 200 mA continuous package VCC/GND
current and specifies TTL inputs, but the actual chosen manufacturer's part
must be checked. [TI ACT04](https://www.ti.com/lit/ds/symlink/sn74act04.pdf).

HP output emitter current adds collector current through each 22 Ω feed
resistor. Its total depends on the asserted channels and the real HP loads;
it is **not included** in the 0.485 A bias figure. Size those resistors and
the input copper for the resulting load, not just FPGA consumption.

The receiver's 2 kΩ bus-to-−2 V resistors sink, at a 2.5 V high bus level,
`43 × (2.5 + 2) / 2000 = 96.8 mA` into −2 V; at a 3.3 V bus high it is
114 mA. PON conditioning and other connected terminations add to that.
Use the existing HP −2 V supply directly.

Using the allowances above, 90% conversion for both 3.3 V stages, 85% for
1.2 V, and 30 mA RS-232 +5 V current:

```text
HP-side 3.3 V incl. Ethernet  0.917 A
FPGA 1.2 V buck input        0.291 A
MCU/SD buck input via diode  0.407 A
24 driver base-bias paths    0.485 A
RS-232 logic supply          0.030 A
                            -------
Estimated subtotal          2.131 A, approximately 2.13 A at 4.85 V

Add HP output collector currents, pendant current, other loads and margin.
Individual displayed currents are rounded; subtotal uses unrounded values.
```

This is a planning operating envelope, not a measured typical draw or complete
worst case. The machine's 50 A capacity is sufficient for this scale of load;
complete the per-card power path/contact/trace/thermal budget when HP output
and pendant currents are fixed.

## 5. RS-232 using the available ±12 V

**TI SN75185DWR, C2671047, SOIC-20 wide** uses external supplies: +4.85 V on VCC, +12 V on VDD, −12 V on VSS, and ground. It has
three drivers/five receivers: one pair serves the pendant and the remaining
two transmitters/four receivers serve expansion and the external/top connector.
It accepts 3.3 V TX logic (driver VIH minimum 1.9 V). Its receiver produces
5 V-domain logic, so use an **SN74LVC2G125DCUR/C21404** powered by `+3V3_MCU` for
RX level conversion and controlled isolation of the TX branch. Its inputs
accept 5.5 V and it supports partial-power-down isolation. Define output
enable from HP power presence, with outputs disabled by default.
[TI SN75185](https://www.ti.com/lit/ds/symlink/sn75185.pdf),
[TI buffer](https://www.ti.com/lit/ds/symlink/sn74lvc2g125.pdf).

At ±12 V, the transceiver's specified no-load envelope is up to 19 mA from
each ±12 V rail (depending on logic state), plus up to 30 mA from +5 V.
Allow **50 mA per ±12 V rail for three loaded transmitters plus static current**;
short circuits need their own dissipation check. No ±12 V regulator/charge pump is
needed. The part's data-rate conditions support considering 115200 baud on a
short pendant cable; validate the actual cable/load and fit any required slew
control components. The RS-232 port/pendant are HP-powered and unavailable
on USB alone. USB DFU remains the independent recovery route.

Use **SN74LVC125APWR/C7813** on `+3V3_HP` to translate the four spare
receiver outputs to 3.3 V logic posts. Expose the two spare TX logic inputs,
four translated RX outputs, and their RS-232 line sides in the wire-wrap area;
route line sides to the external/top connector. Add 10 kΩ idle bias on spare
TX inputs. Keep HP-off power-domain behavior defined for user-patched signals.
[TI receiver buffer](https://www.ti.com/lit/ds/symlink/sn74lvc125a.pdf).

## 6. Component identities and references

Exact selected identities and LCSC ordering codes are in the
[component list](INTEGRATED_BOARD_BOM.csv). Stock counts and inventory
snapshots are not part of the design record. Resolve unavailable components
when preparing an order, checking substitutions against electrical and footprint
requirements.

The SD holder is **SD-106M/C266603**: pad 10 CD to PC7 and pad 11 WP to
PB1, both switches to GND with MCU-rail pull-ups. The flash is
**GD25Q16ESIG/C2693492**, 208 mil SOP-8, JEDEC **C8 40 15**, QE initially
zero; provide /WP and /HOLD bias and respect its 1 ms power-up readiness.
Implement its part-specific programming support. USB ESD **C21713975** is
**GOODWORK USBLC6-2SC6**; use that manufacturer's diagram.

- [SD holder drawing](https://datasheet.lcsc.com/datasheet/pdf/62635050394eda24b10fdd0591981087.pdf)
- [Flash data sheet](https://datasheet.lcsc.com/datasheet/pdf/6b8a460d13f4182b5e51681bc7a2ff41.pdf)
- [USB protection drawing](https://datasheet.lcsc.com/datasheet/pdf/82dbd0924d2527ec12064b134baa37c9.pdf)
- [Input capacitor reference in TI's design][buck-ds]
- [Samsung output-capacitor specification](https://media.digikey.com/pdf/Data%20Sheets/Samsung%20PDFs/CL31A226KAHNNNE_Spec.pdf)
- [Yageo 73.2 kΩ specification](https://www.yageogroup.com/component-documentation/download/specsheet/RC0603FR-0773K2L)

## 7. Ethernet allowance and implementation checks

Allocate **200 mA at 3.3 V** for the LAN8720A, magnetics drive,
external board LEDs and margin. The shared clock has a separate 50 mA allocation.
The PHY's REF_CLK-input-mode table
lists 49 mA maximum chip current for 100BASE-TX; magnetics add about 41 mA
typically. At 10BASE-T, the corresponding figures are 24 mA maximum chip
current and about 100 mA typical magnetics current. The latter is the larger
load. These figures exclude LEDs; the allocation includes LED current and margin.
The jack is now the TME-sourced unshielded **MTJ-885X1** with external
**Pulse H1102NLT/C18584** transformer/choke module and two external LEDs.
The load allowance is retained; verify it with the new line-side network.

The 200 mA total is an engineering allocation mixing maxima and typical
magnetics figures, not a guaranteed worst-case specification. Verify it with
both link speeds, traffic and the chosen LED/termination network.
[Microchip data sheet, section 5.4](https://ww1.microchip.com/downloads/aemDocuments/documents/UNG/ProductDocuments/DataSheets/LAN8720A-LAN8720Ai-Data-Sheet-DS00002165.pdf).

Supply this branch from `+3V3_HP`. Keep its internal 1.2 V regulator output
local to the PHY; it is not another source for `+1V2_FPGA`. The
common 50 MHz clock drives PHY CLKIN and MCU PA1. The hardware power-on reset
delay must meet the PHY's 25 ms requirement before release, even if MCU
firmware has not started; PE5 can assert an additional reset. During USB-only
operation release MCU outputs toward this unpowered branch.

## 8. Presence sensing and configuration bias

USB VBUS sensing uses **PB0** with **1.8 kΩ to VBUS / 3.3 kΩ to GND**, 1%.
The divider draws about **0.98 mA at 5 V**, directly from USB VBUS. PB0 is
an FT digital input, active high, with internal pulls and ADC/analog use
disabled. With 1% resistors and 4.4–5.5 V VBUS, the node spans approximately
**2.827–3.584 V**, below 4 V even while the MCU supply is zero.
[ST pin/electrical limits](https://www.st.com/resource/en/datasheet/stm32f407vg.pdf),
[ST VBUS guidance](https://www.st.com/resource/en/application_note/an4879-introduction-to-usb-hardware-and-pcb-guidelines-using-stm32-mcus-stmicroelectronics.pdf).

HP presence remains a hardware NPN detector on PA0, supplying the reset gate
as well as MCU status. **HSWAPEN/P144 is grounded** to enable FPGA weak
pull-ups before configuration; **SUSPEND/P73 is grounded**. Include weak-pull
loads in startup checks. Retain external receiver, driver-input and control
bias; HSWAPEN does not define post-configuration I/O pulls.

## 9. Shared 50 MHz clock supply allowance

One **YXC OT2EL4C4JI-111OLP-50M/C5203552** drives a
**CDCLVC1104PWR/C485518** fan-out buffer. Three independent outputs feed
FPGA P56, PHY CLKIN and STM32 PA1. Power both from `+3V3_HP`; fit a 0 Ω
supply link, 100 nF at each IC, and 4.7 µF local buffer bulk. Tie buffer 1G
high and pull oscillator OE high with 10 kΩ. Use 10 Ω source-series positions
on the three clock branches. Keep the unused output unconnected.

Allocate **50 mA total** for oscillator, fan-out internal switching, capacitive
loads and margin. The oscillator's sheet gives 12 mA maximum; the buffer's
static maximum is 10 mA, with dynamic load depending on clock frequency and
receiver/trace capacitance. This is a planning allowance, not a guaranteed
maximum independent of load. Qualify clock loading, supply noise, frequency
and jitter on the final routing. [TI clock buffer][clock-ds],
[YXC drawing](https://datasheet.lcsc.com/datasheet/pdf/b336a5b52993e15e0134a8f3d7decec7.pdf).

[buck-ds]: https://www.ti.com/lit/ds/symlink/tlv62569.pdf
[inductor-ds]: https://www.bourns.com/docs/Product-Datasheets/SRP5030T.pdf
[clock-ds]: https://www.ti.com/lit/ds/symlink/cdclvc1104.pdf
[reset-ds]: https://www.ti.com/lit/ds/symlink/sn74lvc1g32.pdf

## 10. Accepted regulator power indicators

Fit three **KT-0603R/C2286** LEDs, each with its own **470 Ω/C23179**,
for +3V3_HP, +3V3_MCU and +1V2_FPGA. Each 3.3 V output drives its own
indicator directly. The 1.2 V indicator instead uses an NPN sensing circuit
powered from +3V3_HP: LED/resistor to collector, emitter to GND, 1 kΩ from
core rail to base and 100 kΩ base-to-GND. Reuse MMBT2369ALT1G/C94404.
This LED requires the HP 3.3 V rail and signals presence rather than a
calibrated 1.2 V tolerance threshold.

Allocate about 3 mA per LED branch and up to 0.6 mA base drive from 1.2 V.
The two HP-side LED branches fit within the existing 25 mA support reserve;
the MCU LED branch fits within its existing 50 mA support allowance. The
1 A provisional core allowance includes the small sensing load. The rail
planning totals are retained; verify actual brightness, VBE/gain and startup.
