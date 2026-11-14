# How the Phone Works

What the firmware is, how it is built, what the phone does when it boots,
takes a card and makes a call, and what we still don't know.

The firmware image came from a Romanian (Intrarom) INT 200 (see
`firmwares/R4R1C/README.txt`). Everything below is from that image, read
statically and run in an emulator. No schematic has been consulted and no
physical phone has been probed, so hardware identities are inferred from how
the ROM behaves, not read off a board.

Confidence labels as in [SERVER.md](SERVER.md): **Verified** (ROM executed in
the emulator and observed), **Traced** (followed in the disassembly),
**Hypothesis** (plausible, unconfirmed). "Verified" always means with simulated
peripherals.

Related: [SERVER.md](SERVER.md) (protocol), [SETTINGS.md](SETTINGS.md)
(parameters), [CONFIGURATION.md](CONFIGURATION.md) (service menu and
provisioning).

---

## 1. The firmware image

| | |
|---|---|
| File | `firmwares/R4R1C/SOURCE.BIN`, 262,144 bytes, from an AT29C020 flash chip |
| SHA-256 | `b180326613fae35c773d5c593c59e1085161961446e36f3767b3129e0fe76b3a` |
| Unscrambled | `UNSCRAMBLED.BIN`, SHA-256 `6659dbe1…161e47` |
| CPU code | Motorola 68HC11 (exact variant and clock not established) |

**Scrambling.** The raw dump has data lines D4 and D5 swapped in every byte.
Swapping them back gives coherent ASCII, valid 68HC11 code, reset code and
vectors. The swap is its own inverse (`tools/scramble.py`). We don't know
whether this comes from the board wiring, the dumping adapter or something
else; the dump alone can't say.

**Two copies.** The two 128 KiB halves of the dump are byte-identical. That
fits an A/B arrangement, where the phone holds two firmware images and an
update downloads into whichever is inactive (§7). It could also just mean
address line A17 wasn't connected when the chip was read. **Hypothesis.**

**Vintage.** A text string at file offset `$000006` reads `COMUNICI MAI MULT CU
CARTELA DE 15 RON! AI BONUS INCLUS 10000 UNITATI!` ("Talk more with the 15 RON
card! Bonus included, 10000 units!"). The currency name RON came into use in
2005, so this build is no earlier than that. It's an inference from one
string, not a version number.

**Version information.** A scan of every printable string in the 128 KiB image
finds no version number, build date, copyright text, model name or the label
`R4R1C`. The only identity-like data are:

- A 4-byte **identifier `EA 77 9D 00`** in a data block at file `$4346`
  (copied to RAM `$0100` at start-up). The update code compares it with a
  stored copy to decide whether to replicate the image
  ([FIRMWARE-UPDATE.md](FIRMWARE-UPDATE.md) §3), so it behaves like a
  firmware ID plus a one-byte revision. Whether it is also sent to the server
  is not established.
- The image's **additive checksum** (all bytes from `$0800`, 16-bit): **`E663`**.
  This is what `907#` displays for an unmodified half, so it works as a
  fingerprint for this build. Together with the SHA-256 above, record both
  when comparing against other dumps.
- The text at `$0006` (the RON advertisement) is preceded by a six-byte
  header (`02 00 4B 05 04 06`) and sits inside the first `$0800` bytes, which
  the update checksum skips. Since the CSMS is described as downloading
  advertising messages, this looks like replaceable data and not part of the
  firmware's identity. **Hypothesis.**

So the `R4R1C` sticker is the only name we have, and it exists only on the
chip. A phone can change its running image over the line, so the sticker
can't be trusted to match what the chip now holds. The checksum and
identifier can.

### Memory map

Established from the reset code, repeated vector tables and the alignment of
far-call targets (**Traced**, parts **Verified** by booting):

| CPU range | Contents |
|---|---|
| `$0000–$00FF`, etc. | On-chip RAM and registers. The startup test writes alternating `$AAAA`/`$5555` over `$0050–$00AF`; a mismatch executes `SWI`. |
| `$2000–$3FFF` | 8 KiB window onto the **configuration EEPROM** (32 KiB part). Selected by bits 2–3 of `$4080`. |
| `$4040`, `$40C0`, `$4080` | External latches and inputs (§3). |
| `$4100–$7FFF` | **Common code**, always visible: reset, far-call helper, interrupt stubs, drivers. Reset entry `$4142`. |
| `$8000–$FFFF` | **Banked code**, four 32 KiB banks chosen by bits 0–1 of `$4080`. |

The bank selector is the *inverse* of the physical 32 KiB chunk number:

| Selector | File chunk | File offsets |
|---:|---:|---|
| 3 | 0 | `$00000–$07FFF` |
| 2 | 1 | `$08000–$0FFFF` |
| 1 | 2 | `$10000–$17FFF` |
| 0 | 3 | `$18000–$1FFFF` |

`file_offset = (3 − selector) × $8000 + cpu_address − $8000`. Routines in these
docs are named by selector and CPU address, e.g. "selector 2 `$EA47`".

Code in one bank calls another through a **far-call helper** at `$5080`: it
reads an inline selector byte and 16-bit destination after the `JSR`, switches
bank, calls, and restores. The helper preserves the other bits of `$4080`.

Each bank ends in an identical 64-byte vector table (file `$007FC0`, `$00FFC0`,
`$017FC0`, `$01FFC0`) with reset → `$4142`. Vector `$FFE2` points at `$6CDF`
instead of the regular stub `$6C24`; the reason is unexplained.

### The configuration EEPROM

Settings and persistent state live in a separate 32 KiB EEPROM, addressed by
"logical" addresses `$1100` upward (see [SETTINGS.md](SETTINGS.md)). Four
32 KiB dumps (`AT28C256E@PLCC32-read*.BIN`) exist in the research folder and
are not in this repository; all differ, and none has been tied to this
firmware yet. All emulator runs use
a synthetic configuration generated by the ROM itself.

The EEPROM is programmed in **64-byte pages** using the usual `AA/55/A0`
unlock sequence at logical `$5555/$2AAA/$5555`. The ROM self-tests it on boot
with an AA/55 pattern over `$2080–$20BF`; if that fails it displays
`NU FUNCTIONEAZA` ("does not work") and stops. **Verified.**

---

## 2. Software structure

The firmware is a small cooperative multitasking system on top of a
timer-driven scheduler.

- **Tick:** the timer prescaler is /16 and the scheduler ticks every **8 ms**
  (500 counts) under a 1 MHz E-clock hypothesis. 125 ticks = one nominal second.
- **Tasks and queues:** each task owns a message queue. Messages are 16-bit
  words, the high byte a type (`10xx` = keypad character, `A0xx` = metering
  pulse, `85xx` = card removal, `3C0C`/`3C17`/`3C1C` = call-UI events, …).
  Tasks seen so far: keypad/UI, line (dialling and supervision), metering
  (charging), card, and a maintenance-session task started by the `93x#`
  service commands.
- **Timers:** a generic timer list walked from `$E617` serves everything that
  waits.
- **Interrupts:** 32 stub vectors at `$6BE0–$6C5F` all load an interrupt number
  and enter a shared bank-aware dispatcher at `$6C60`.
- **`STOP`:** the ROM executes the HC11 `STOP` instruction when it has nothing
  to do (with a hook/line/card-presence-like input in the idle state). Waking
  is by an external interrupt that the emulator doesn't model. **Traced.**

The firmware contains no TCP/IP. Everything the lab calls TCP is a stand-in for
the modem line (§5).

---

## 3. Hardware as the ROM sees it

All identities here are **candidates** from behaviour.

### Keypad and front-panel inputs

A 4×4 matrix with a `123A456B789C*0#D` layout (table at file `$43FE`):

| | col 1 | col 2 | col 3 | col 4 |
|---|---|---|---|---|
| row 1 | 1 | 2 | 3 | A |
| row 2 | 4 | 5 | 6 | B |
| row 3 | 7 | 8 | 9 | C |
| row 4 | * | 0 | # | D |

The scanner at common `$4669` shifts three SPI-style bytes twice, writing
column selectors `01 02 04 08` to latch `$0322` and reading rows from `$0325`.
Debounce needs consecutive identical samples; a recognised key becomes a
`$1000 | ASCII` event. **Verified** for every key.

Besides keys, the same scan line carries control bits (input byte 1 at
`$0326`). We found them by forcing each bit low during reset:

| Bit | Effect | Candidate meaning |
|---:|---|---|
| 2 | Boot goes to the PIN prompt (`TIPARESTE CODUL`) | Service switch |
| 0 | Boot goes to the `TESTARE` self-test menu | Self-test switch |
| 4 | CPU executes `STOP` | "Nothing to do" / sleep condition |

Bits 1, 3 and 5–7 showed no effect. Separately, **input 11** (active low)
launches another routine (`$DE42`) and is not the same as the service switch.
**Verified** behaviour; physical identities unestablished. The working
assumption is that the service switch is **SW700**, the switch next to the
`CUN701` connector on the main board (judged from a photo, not from tracing
the circuit). Which of the service and self-test inputs it drives is not
confirmed.

The keypad's fourth column (`A B C D`) has no known physical legend. In
practice the card-change message mentions a "K" button.

### Buses and peripherals

| Interface | Pins / address | What the ROM does |
|---|---|---|
| Keypad / input scanner | SPI-like, `$4040`/`$40C0` latches | Described above |
| Clock chip | PD3 data, PD4 clock, wire address `A0/A1` | Reads five bytes sec/min/hour/year-day/month; layout matches a PCF8583-style clock |
| Controller bus | PA3 data, PA4 clock, wire address `64/65` | Initialisation `81 80 01`, record queries (`88`, `90`); identity unknown |
| Control bus | PD0 data, inverted PD1 clock, address `48`, shared with SCI pins | ACK-only control writes |
| Card reader | Two-wire exchanges with checksummed packets (type `80` identity, `1E` setup, credit writes) | Models a memory card with balance; real smart-card protocol not recovered |
| Modem / line | SCI (UART), 1200 bit/s candidate | Carrier detect, then framed protocol ([SERVER.md](SERVER.md)) |
| Metering input | External PORTA bit 2 → `$0333` bit 4 → software filter | Pulse input used by one supervision mode |
| Card removal contact | `$4080` mask `20` (scanner input 5) | Posts `85xx` to the card task |
| Reply-pending line | `$4080` bit `40`, active low | Gates the serial receive path |

`$4080` is both a bank latch (output bits `1F`) and an input port (bits `E0`);
a model that overwrites the whole byte corrupts bank selection.

The LCD is 2×20 characters. Characters render through glyph tables; `901#`
shows a test pattern.

---

## 4. Boot and idle

1. Reset: interrupts off, `$4080 = 0`, RAM check, register setup, branch to
   `$5590` (hardware setup and RAM test).
2. If the configuration EEPROM is blank (all `FF`), the ROM **initialises
   itself**: the display shows `Init` with an animated `. o O`, taking about
   66 s of emulated time, and queues a first-contact session (flag `$0C75 = 1`,
   mode 60) for the server to complete.
3. With a valid configuration it registers the keypad and shows `ASTEPTATI`
   ("please wait") while the tasks start.
4. Normal idle shows **INSERT CARD** (§6).

Holding the service or self-test input during reset diverts to the PIN prompt
or the self-test, §3 and [CONFIGURATION.md](CONFIGURATION.md) §1.

In the emulator, with no card reader, line or controller attached, the idle UI
task times out waiting for a reply and the phone shows `EROARE 520`. That error
is a generic "the task never got the message it was waiting for", not a card
or UART fault (the serial transmit buffer stays empty on that path). What the
real phone is waiting for in the unattended case is still open. **Traced.**

---

## 5. Talking to the server

The phone has its own maintenance client. It is the *phone* that places the
call, both for scheduled maintenance and for the technician-triggered
`93x#` commands; the central system then drives the session with read/write
commands. [SERVER.md](SERVER.md) covers framing, message types, CRC, status
codes and uploads. The parts worth knowing from the phone's side:

- **Dialling out** uses 260 (prefix), pause 264 and 261 or 267 (destination),
  through the same dial path as customer calls.
- **Carrier handshake.** The ROM checks for a low-RXD interval then a stable
  high interval before it enables serial receive; the peer's first bytes are
  `06 30`. Timings in the lab are assumptions, not measured.
- **Authentication** is single-DES. The phone encrypts the 8-byte value in
  setting 297 with a key derived from 298 and sends the ciphertext in a type
  `0C` frame (details in [SETTINGS.md](SETTINGS.md) §4.2). The first
  initialisation call (group 1) has no authentication stage at all.
- **Settings, tariff tables, firmware** all arrive as server commands, written
  by the phone's own code into the EEPROM and flash.
- **Records** go the other way: the phone uploads accounting records, status
  lists and a change journal.

Still unresolved: the real line modulation (V.23 per the marketing material),
the real server, how a real session is authorised past the parameter masks, and
whether the real handshake matches the lab model.

---

## 6. What a customer sees

### Messages

Nineteen user messages, each in four languages. Index 03 and 18 share the same
text but are separate situations to the ROM.

| # | Romanian | English | Notes |
|--:|---|---|---|
| 00 | INTRODUCETI CARTELA | INSERT CARD | Idle |
| 01 | CONT | CREDIT | Followed by the balance |
| 02 | FORMATI NUMARUL | DIAL NUMBER | Card accepted |
| 03 | ASTEPTATI | PLEASE WAIT | |
| 04 | NU FUNCTIONEAZA | OUT OF ORDER | Also the EEPROM self-test failure |
| 05 | CONVORBIRI GRATUITE | ONLY FREE CALLS | Free calls only |
| 06 | TELEFON DISPONIBIL | TELEPHONE READY | Idle without needing a card |
| 07 | NU SCOATETI CARTELA | DO NOT REMOVE CARD | Mid-transaction |
| 08 | APEL NETAXABIL | TOLL FREE CALL | Free category |
| 09 | CARTELA RESPINSA | CARD REJECTED | |
| 10 | MINIM LEI: | MINIMUM CREDIT: | Backing parameter not traced |
| 11 | CARTELA NOUA:APASA K | FOR NEW CARD:PRESS K | |
| 12 | SCHIMBATI CARTELA | CHANGE CARD | |
| 13 | TESTARE | TEST | Service menu title |
| 14 | TIPARESTE CODUL | ENTER PIN NUMBER | PIN prompt |
| 15 | EROARE | ERROR | |
| 16 | EROARE _ | ERROR _ | Followed by a code |
| 17 | SCOATETI CARTELA | REMOVE CARD | End of call |
| 18 | ASTEPTATI | PLEASE WAIT | |

French and German equivalents are in the firmware (selector 2, pointer tables
at file `$00FE88` Romanian, `$00FEAE` English, `$00FED4` French, `$00FEFA`
German; strings from `$00FA39`). The Romanian minimum-credit message says
"LEI" while the German says "EINHEITEN" (units): the same slot, but a
different noun per language.

French: INSEREZ LA CARTE SVP · COMPOSEZ NUMERO SVP · APPAREIL EN PANNE ·
APPEL GRATUIT · CARTE REJETEE · CHANGEZ LA CARTE SVP · ENTREZ NUM. DE CODE.
German: KARTE EINSCHIEBEN · NUMMER WAEHLEN · APPARAT DEFEKT · GEBUEHRENFREIER
RUF · KARTE UNGUELTIG · KARTE WAECHSELN · CODENUMMER EINGEBEN.

### Language

Language is a RAM selector (`$078B`), 0 Romanian, 1 English, 2 French, 3 German.
Pressing matrix `A` at the PIN prompt cycles it. It resets to Romanian on every
boot, so there is no stored language preference we know of. In the tested path
only the first ten `A` presses changed the language. Parameter 231 is **not**
the language setting. **Verified.**

### A call, step by step

All of this is **Verified** in the emulator with a modelled card, clock and
line; none of it has been watched on a real phone.

1. **Card in.** The ROM asks the reader for the card's identity, matches it
   against the downloaded **card-range** rows, and reads the balance. An
   unknown card gives `CARTELA RESPINSA`.
2. **Dial.** Digits are classified as they arrive (§ Dial plan, below).
3. **Free call:** no answer supervision, no card write, no accounting record,
   at least under the default logging mask. This works even with no card.
4. **Paid call:** the metering task waits for the configured *answer
   supervision* condition (setting 114/115: a pulse, a line transition, a
   timer, or a key) before charging.
5. **Charging.** The phone debits an *initial charge* when charging starts
   and then a *repeat charge* every period, writing the new balance back to
   the card each time. All amounts and periods are settings (§4.3 of
   [SETTINGS.md](SETTINGS.md)). Prices can be adjusted by time of day and
   date window, and a card range can switch to an alternate price bank.
6. **Low credit.** The ROM caps the last debit to what is left and shortens
   the period to match, then closes the call at exhaustion.
7. **Failed card writes.** A write that gets no reply is retried: the same
   request is sent three times in total, after which the call closes
   (`3C1C`) and the record shows the *last acknowledged* balance.
8. **Hang-up or card removal.** The phone appends a 26-byte accounting record
   and shows `REMOVE CARD`. Removal mid-call (contact `$4080` mask `20`)
   closes the call and records what was actually debited.

### Dial plan

The phone classifies numbers *as the digits are typed*. A category result is
kept; later digits don't re-run the check once a category is accepted.

| Raw code | Meaning |
|---|---|
| `01`–`0A` | Paid category 0–9 (the classifier subtracts one) |
| `20` | Free |
| `10` | Barred |
| `FF` / `AA` | Unresolved / no valid route (internal results) |

With no dial plan downloaded (`$2076 ≠ 1`) the ROM uses a built-in fallback:

| Prefixes | Category |
|---|---|
| `911 961 981 922 930 931 932 955` | Free |
| `971 99` | Barred |
| `00` | Paid, category 2 |
| `01`–`09` | Paid, category 1 |

These are literal decoded prefixes. They are not claims about Romanian
numbering or which service a number reaches. In particular `0800…` resolves at
`08` to a *paid* category, so a free `0800` needs a downloaded plan.

The classifier intersects per-digit candidate masks and needs a unique match at
a stored length. It is not longest-prefix-wins. A broad `08` paid rule next to
a narrower `0800` free rule is not safe to assume: a real plan has to
cover the whole numbering scheme with non-overlapping prefixes.

### Accounting records

Each call that is charged ends with a 26-byte record
([SERVER.md](SERVER.md) §7). Records queue in the phone until a session
uploads them (up to eight per frame); the pending count is committed after the
server acknowledges each batch. Record contents:

- sequence number, dialled digits, date and time,
- a four-digit quantity, three six-digit values and a status/class byte.

In the emulated calls the first field held the card-range ID, the second
four-digit field the call length in nominal units, the first six-digit field
the amount debited and the second the balance left (a 20-unit call off a 100
card was stored as debit 20, balance 80); the outer six-digit value held the
card serial. That's the pattern from lab-driven calls, not a proven
definition. Full detail: [ACCOUNTING.md](ACCOUNTING.md).

---

## 7. Firmware update model

The phone can take a complete new image from the server (`1F`–`31` family,
[SERVER.md](SERVER.md) §8). In the emulator the full path works end to end:
all 512 pages of 256 bytes are sent into an initially erased inactive half,
the image checksum is verified, activation is requested, and on the next reset
the ROM runs from the new half. A post-boot step then copies the image and
checks it, ending in **state 4** (success) or **state 5** (a write failed).

Things worth knowing:

- State 5 does not roll back. The phone stays on the image it tried and a
  fresh download is the recovery.
- `2F` clears the state but is explicitly not a rollback.
- `907#` in the service menu shows the two image checksums, a selection
  indicator and the state byte.
- The dial-plan table lives in flash (`$8400…$87FF`) outside the checksummed
  executable region, programmed to *both* halves.
- None of this has been run on a real flash chip. Erase timing, power failure
  during programming, the unlock sequence on real silicon and automatic retry
  are all untested.

---

## 8. Error codes

| Display | Meaning |
|---|---|
| `EROARE 520` | The UI task timed out waiting on its queue. Generic. |
| `EROARE 572`, `802`, `803` | `TESTARE` self-test failures. The numbers match the RAM status addresses tested (`802` = `$0322`, the keypad column latch). |
| `EROARE:751` … `:790` | Fixed-string fault table; most are not linked to a condition. Known: `773` = repeated link-control exchange failing during upload (all records stay pending); `788` = session terminated before the completion command; `790` = session finished with the wrong completion command. |
| Internal `3C0C`, `3C17`, `3C1C` | Call-UI events: no credit, credit exhausted, card write failed |

---

## 9. Open questions

1. How a real session gets past the access masks (the login handler isn't
   found).
2. The physical identity of every switch, contact and the `A B C D` keys.
3. Real units of the accounting fields and of credit/charge numbers.
4. What the real line and modem do: modulation, handshake, timings.
5. Whether the firmware's behaviour with a real card and a real hook/line
   matches the lab model.
6. Meaning of most settings and of the `120–129` accumulators.
7. The `EROARE:751–790` table and how the idle `EROARE 520` condition is
   avoided on real hardware.
8. None of the hardware inferences have been cross-checked against the
   photos in `pictures/`.
