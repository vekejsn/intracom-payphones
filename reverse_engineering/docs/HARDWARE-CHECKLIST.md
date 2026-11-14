# Things to Verify on Real Hardware

Every claim in these docs comes from the firmware image and an emulator.
This list collects the claims that a real board can confirm or overturn, ordered
so that the cheapest and safest checks come first. It assumes an **incomplete
phone**: a main board with the ROM, maybe a keypad and display, but possibly no
card reader, line interface or handset.

Record results by editing the relevant doc and changing the confidence label
(Hypothesis → Verified, or correct the claim). A negative result is as useful as
a positive one.

---

## 0. Before you power anything

- **Back up first.** Read both chips and keep the dumps untouched: the program
  flash (AT29C020, `firmwares/R4R1C/SOURCE.BIN` is the expected content) and the
  configuration EEPROM (a 32 KiB part, we think an AT28C256). Several service
  commands and any settings write change the EEPROM.
- Note whether the EEPROM is the original. A blank or foreign EEPROM changes what
  you see at boot (§3).

---

## 1. Inspection and photos (no power)

| Check | Settles |
|---|---|
| CPU part number and package | The "68HC11, variant unknown" gap in [PHONE.md](PHONE.md) §1 |
| Crystal frequency | The 1 MHz E-clock and 8 ms tick hypothesis (a 4 MHz crystal gives 1 MHz) |
| Part numbers: EEPROM, clock chip, any modem/line IC, address decode logic | The "candidate" device names in [PHONE.md](PHONE.md) §3 |
| Silkscreen: `SW700`, `CUN701`, other switches, jumpers, test points | Switch identities (§2) |
| Connector pinouts (keypad, display, card reader, line) | Keypad matrix wiring; which connector carries what |
| Label and markings on the ROM sticker (`R4R1C`) | Firmware/version naming; any date code |

Add the photos under `pictures/`.

---

## 2. Continuity checks (no power, multimeter)

| Check | Settles |
|---|---|
| **CPU PA5 → flash A17.** Continuity from the CPU pin to the flash's A17 pin (check the datasheet for pin numbers on your package) | Whether PA5 really selects the flash half, i.e. the A/B update model ([FIRMWARE-UPDATE.md](FIRMWARE-UPDATE.md) §1). The biggest single check. |
| **SW700**: which pins it connects to, and which CPU or scanner pin that net reaches | Whether SW700 is the service input (candidate: input byte 1 bit 2) or the self-test input (bit 0). See [CONFIGURATION.md](CONFIGURATION.md) §1. |
| Other switches and jumpers on the board | The remaining unidentified inputs: self-test (bit 0), the sleep/"nothing to do" input (bit 4), input 11 |
| Card-removal contact (candidate: `$4080` mask `20`) | [PHONE.md](PHONE.md) §3 table |
| Keypad connector → row/column lines | The `123A456B789C*0#D` matrix and what the fourth column (`A B C D`) is wired to, if anything |
| Clock chip address pins and bus pins | The PD3/PD4 clock bus (wire address `A0/A1`) |

---

## 3. Power-on observations (bench supply, current limited)

With the display and keypad connected:

| Observation | What it tells you |
|---|---|
| Display text right after power-up | Blank EEPROM → `Init` with animated `. o O` for about a minute; faulty EEPROM → `NU FUNCTIONEAZA`; a valid one with other parts missing → likely `ASTEPTATI`, then `EROARE 520` |
| `EROARE 520` appearing when nothing is attached | Matches the emulator ([PHONE.md](PHONE.md) §4). If the real board shows idle `INTRODUCETI CARTELA` instead, the cause of 520 is a missing peripheral and the emulator is wrong about which one. |
| Current draw at idle and whether the CPU enters `STOP` | The `STOP` / wake behaviour in [PHONE.md](PHONE.md) §2 |
| LCD behaviour: contrast, glyphs, 2×20 layout | Display assumptions |

### Service menu, read-only checks

Only after a backup. Set SW700 (or a candidate switch) **before** reset:

1. Reset with SW700 in one position, then the other. Which gives
   `TIPARESTE CODUL`? Does the other give `TESTARE` directly?
2. At the prompt, press `A` repeatedly. Does the language cycle
   (Romanian → English → French → German)? Does it stop after about ten presses?
3. Enter `555657#`, then `336633#` on a separate boot. Do both open `TESTARE`?
4. Read-only commands: `000#`, `004#`, `060#`, `062#`, `250#`, `256#`, `260#`,
   `261#`, `267#`, each followed by `*` to leave. Compare with your EEPROM dump.
5. Diagnostics: `900#` (keypad echo), `901#` (LCD pattern), `907#` (update
   state and image checksums), `920#`.

`907#` is especially useful: it prints the checksums of both flash halves. On the
real phone, equal values would agree with the A/B model, and each value should
match the additive checksum of that half of the flash dump (sum of all bytes after
the first `$0800`, 16-bit).

### Do not run on the real phone

`930#`, `970#`–`972#`, `979#`, `990#`–`992#`, `994#`, `996#`–`999#`, and the `9`
key in the `951#` browser. They clear or reset state. See
[CONFIGURATION.md](CONFIGURATION.md) §5. Don't write settings you don't understand;
if you do write one, record the old value first.

---

## 4. Dumps and comparisons

| Check | Settles |
|---|---|
| Read the flash in a programmer **and** in-circuit if possible. Are the halves still identical? | Real A/B copy versus an artefact of how the chip was read |
| Does the flash content equal `SOURCE.BIN` (SHA-256 `b180326613fae35c773d5c593c59e1085161961446e36f3767b3129e0fe76b3a`)? | Same firmware build as the one analysed |
| Dump the EEPROM and look at `$1100` onward in logical order (the 8 KiB window may need un-paging) | Whether the catalog's logical addresses ([SETTINGS.md](SETTINGS.md)) match real data: `$1100` is dialing mode, `$1104` pulse timing, `$113C` terminal ID, `$127F` maintenance time A, `$128C` prefix, `$128F` destination A |
| Compare the EEPROM against the four unlabelled `AT28C256E` dumps | Which belongs to this firmware, and whether any holds a real destination number or authentication inputs (297/298) |
| Logical `$4000` onward, and the header at `$0C7A` | Pending call-record slots (28 bytes each) on a phone that has been used: real dialled numbers, timestamps and amounts ([ACCOUNTING.md](ACCOUNTING.md)) |

If you find real stored values for 130–159, 200–247 or 114/115, they will say more
about the tariff parameters than the lab values do.

---

## 5. Signals (logic analyser or scope, optional)

| Signal | Settles |
|---|---|
| Writes to `$4080` at reset | Bank latch behaviour; bit assignment (bits 0–1 ROM bank, 2–3 EEPROM window, `E0` inputs) |
| PA5 level after reset, and with the stored `$0DFB` byte changed on a *copy*/spare EEPROM | The half selector end to end |
| Keypad scan lines | Scan order, timing, and the SPI-like transaction assumptions |
| Clock bus (PD3/PD4) | Clock chip identity and address |
| SCI TX/RX, and PD0/PD1 control bus | The framing, 1200 bit/s assumption and the shared-pin behaviour |
| Hook/line/card-presence inputs, if their parts are present | The `STOP` wake condition and the "reply pending" line |

---

## 6. Needs the missing parts

These can't be checked on an incomplete phone, but would settle the biggest gaps:

- **Line interface and modem:** the actual modulation (V.23 per the brochure),
  carrier handshake, and whether the `06 30` start token appears. A capture of one
  real call to a server would let us test everything in [SERVER.md](SERVER.md).
- **Card reader and card:** the real card protocol, credit units and what a card
  write looks like on the wire.
- **Handset/hook and metering input:** the answer-supervision modes
  ([SETTINGS.md](SETTINGS.md) §4.3) and real pulse polarity.
- **A working server or recorded session:** the login gate and the real
  authentication flow, still the largest open question.

---

## 7. Results log

Copy this table into a new section of whichever doc you update.

| Date | Check | Result | Doc and label changed |
|---|---|---|---|
| | | | |
