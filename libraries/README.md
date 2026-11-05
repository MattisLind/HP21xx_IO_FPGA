# Project connector footprints

## Full-size SD socket candidate

**SHOU HAN SD-CARD 11P / C7529393** is a short-body, full-size SD push-pull
socket intended for evaluation as the common socket on this board and a future
pendant. Its body is approximately 27.8 mm wide, 16.5 mm deep and 2.9 mm high.
It has mechanical card-detect and write-protect switches. It is listed in the
[JLCPCB assembly library](https://jlcpcb.com/partdetail/SHOUHAN-SD_CARD11P/C7529393).

The footprint is
`HP21xx_Connectors:SD_SHOUHAN_SD-CARD-11P`.
In KiCad's **Manage Footprint Libraries → Project Specific Libraries**, add
the `HP21xx_Connectors.pretty` directory alongside this README with the nickname
`HP21xx_Connectors`. Use a project-relative path when adding it to a board
project. There is no need to modify the installed KiCad libraries.

Use KiCad 10's `Connector:SD_Card_Receptacle` symbol with this footprint:

| Pads | Function |
| --- | --- |
| 1–9 | Standard SD contacts: DAT3, CMD, GND, VDD, CLK, GND, DAT0, DAT1, DAT2 |
| 10 | Mechanical card detect; closes to shell/GND with a card inserted |
| 11 | Mechanical write protect; closes to shell/GND with an unlocked card |
| SH, four lands | Common shell/switch ground; connect to GND |

The current board's PC7 card-detect and PB1 write-protect assignments can be
retained, with pull-ups to the MCU supply. Pin 1's legacy SD signal name
`CD/DAT3` is distinct from the mechanical detect switch on pad 10.

The contact and shell lands, numbering, locating holes and insulation area
were transcribed from SHOU HAN drawing **FP-100090, revision A/0**, pages 1–2
of the [supplier data sheet](https://www.lcsc.com/datasheet/C7529393.pdf).
The downloaded drawing is also available at
[this supplier PDF](https://datasheet.lcsc.com/datasheet/pdf/205c75655f9098343d6dd157d86292c5.pdf?productCode=C7529393).
Dimensions were cross-checked against the **JLCEDA/EasyEDA Official Library**
([JLCEDA](https://lceda.cn/), [EasyEDA](https://easyeda.com/)); its four separate
shell pad numbers have been consolidated into pad SH for the KiCad symbol.

The fab/silkscreen body outline is an approximate envelope. The dashed
Dwgs.User rectangle marks the drawing's insulation area: retain solder mask
or other suitable insulation over copper there. It is not a prohibition on
covered tracks. The courtyard covers the socket and solder lands; reserve
additional space for the card, insertion travel and fingers during layout.

**Enclosure fit remains to be checked with a sample.** The drawing does not
dimension the seated card's outer edge relative to the socket. The short body
is a promising way to leave more card exposed, but exact usable grip length
also depends on the card stop, PCB edge, enclosure wall thickness and socket
setback. Do not calculate guaranteed exposure solely as 32 mm minus 16.5 mm.
There is no verified seated-card outline or STEP model in this footprint.

This candidate has not replaced the existing SD selection in the design/BOM.
