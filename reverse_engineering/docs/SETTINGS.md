# Settings Reference

The configuration parameters ("settings") of the R4R1C firmware: how they are
addressed, encoded and protected, which ones we can put a name to, and the raw
table of all the rest.

Everything here comes from the unscrambled firmware image
(`firmwares/R4R1C/UNSCRAMBLED.BIN`) run in an emulator. No real phone has been
configured and no real server conversation has been captured. See
[SERVER.md](SERVER.md) for the protocol these settings travel over and
[CONFIGURATION.md](CONFIGURATION.md) for how to change them.

Confidence labels, as in `SERVER.md`:

| Label | Meaning |
|---|---|
| **Verified** | Reproduced by running the original ROM code and observing the result. |
| **Traced** | Found in the disassembly by following the code path; not executed end-to-end. |
| **Hypothesis** | Consistent with the ROM, but not confirmed. |

"Verified" always means *in the emulator*, with simulated card reader, clock,
modem and server. It says the ROM does this when fed these inputs; it does not
say a physical phone has been seen doing it.

---

## 1. The parameter space

The firmware has **700 parameter slots**, IDs 0–699. Each has a descriptor in a
table in ROM saying where it lives, how wide it is, who may touch it and what
values it accepts.

| IDs | Name | Slots | Slots with storage | Notes |
|---|---|---:|---:|---|
| 0–299 | Base | 300 | 245 | Ordinary settings. Read and written locally and remotely. |
| 300–699 | Extended | 400 | 170 | Profile-dependent, read-only to ordinary writes. |

The other 285 slots are **zero-width placeholders**: they have a descriptor with
size 0 and access `00` (base) or `AB`/`03` (extended) and store nothing. A read
returns status `01`. Gaps in the numbering are normal.

Most of the 415 slots that do store something have no known purpose. The
mechanism for reading and writing every one of them is understood; what each
number *does* is known for only about 60 of them (§4).

### Descriptor fields

| Field | Meaning |
|---|---|
| **Address** | Logical NVM address, `$1100`–`$1BFF` range. Not a CPU address — the configuration EEPROM is paged into an 8 KiB window at CPU `$2000–$3FFF`. |
| **Internal bytes** | Bytes occupied in non-volatile memory. |
| **Wire bytes** | Bytes used in the protocol. Often different (see §2). |
| **Access** | Permission mask (§3). |
| **Format** | Index into the firmware's table of converters/validators. |
| **Range** | Internal numeric range the validator enforces. |

Format indices are not individually documented; the useful ones:

| Format | Wire shape | Range |
|---:|---|---|
| 0 | Opaque bytes, no numeric conversion (identifiers, BCD digit strings, keys) | — |
| 1 | 6 decimal digits in 3 BCD bytes (stored as a 4-byte binary value) | 0–999999 |
| 2 | 4 decimal digits in 2 BCD bytes | 0–9999 |
| 13 | 2 decimal digits in 1 BCD byte | 0–99 |
| 25 | 8 decimal digits in 4 BCD bytes | 0–99999999 |
| 6 | Boolean | 0–1 |
| 18 | Time of day `hh mm`, `FF FF` = disabled | — |
| 23 | Ten packed 0/1 digits in 5 wire bytes (a per-category mask, §4.3) | — |
| 24 | Date and time `YY MM DD hh mm`, 5 BCD bytes | — |

Other formats are small numeric validators with ranges like 1–30, 5–60 or
0–19; the range column in §6 is authoritative for those.

---

## 2. Encoding on the wire

- **Parameter IDs are plain big-endian binary.** Decimal 131 is `00 83`; decimal
  861 is `03 5D`. Not BCD.
- **Numeric values are usually BCD**, even where the phone stores plain binary.
  Parameter 4 = 64 is sent as `00 64` and stored as `0x40`. A 4-digit value is
  two wire bytes whatever its size internally.
- **Some small values are single plain bytes.** Settings 114 and 283 (small
  0–4 selectors) take a one-byte payload. Which converter applies is decided by
  the descriptor's format, not by a universal rule — always check the table.
- **Opaque fields are exempt**: 60, 61, 297 and 298 are raw bytes.
- **Digit strings** (260, 261, 267) are packed BCD, two digits per byte, padded
  with `F` nibbles. The consumer stops at the first `F`.
- Out-of-range values are rejected with status `03`, not clamped. The stored
  value is left alone. **Verified.**
- At most 16 settings can go in one ordinary request.

Full framing and status codes are in [SERVER.md](SERVER.md) §2 and §4.

**Width caveat for extended reads.** A value can be in the descriptor's range
and still not read back. ID 300 holds binary 2709 fine (`27 09`, status 0), but
2710 returns status 5. The ROM checks the converted output as well as the
nominal range. Don't treat the range column as a guarantee for extended IDs.

---

## 3. Access control

Each base descriptor has a one-byte permission mask. Each operation brings a
fixed flag and the engine ANDs it with the mask; a zero result is status `02`.

| Operation | Mask bit |
|---|---|
| Remote read (type `15`) | `02` |
| Remote write (type `17`) | `04` |
| Technician class 1 read / write | `20` / `10` |
| Technician class 2 read / write | `80` / `40` |

The two technician classes correspond to the two hard-coded PINs
(`555657#` → class 1, `336633#` → class 2; see
[CONFIGURATION.md](CONFIGURATION.md)). Class 2 can write settings class 1
can't, and can enter nine service commands class 1 is refused. The ROM doesn't
define a general hierarchy beyond that, so don't assume either class is a
read-only or "safe" mode.

Bits `08` and `01` appear in many masks but have no known meaning.

Masks in use among the stored slots:

| Mask | Count | Remote | Class 1 | Class 2 | Typical use |
|---|---:|---|---|---|---|
| `FE` | 105 | r/w | r/w | r/w | Ordinary configuration: dialing, timers, maintenance dial-out |
| `EE` | 121 | r/w | **read only** | r/w | Tariff parameters, terminal ID, 231 |
| `AB` | 167 | read only | read only | read only | Extended family (300–699) and base 50–58 |
| `A3` | 11 | read only | read only | read only | Extended 690–699 and base 299 |
| `CE` | 5 | r/w | none | r/w | 75–79 |
| `07` | 3 | r/w | none | none | 295, 296; remote-only switches |
| `87` | 1 | r/w | none | read only | 294 |
| `06` | 1 | r/w | none | none | 297 (authentication plaintext) |
| `FF` | 1 | all | all | all | 62, date/time |

**Verified**: `555657#231#02#` leaves 231 unchanged; `336633#231#02#` stores it.
Remote write to 299 (`A3`) returns status 2 and writes nothing.

**Extended slots (300–699)**: every stored extended descriptor carries `AB` or
`A3`, which excludes all three write bits. All 170 reject ordinary remote
writes with status `02`. The local editor shows them but has no write path.
Separate internal and table-maintenance operations can still change the storage;
those aren't covered by this ordinary-write limit.

**What this does not tell us.** These checks happen inside the parameter
handlers. They say nothing about whether an unauthenticated caller can *reach*
the handlers. The login/session gate (see `SERVER.md` §12) is still unresolved.

---

## 4. Settings with a known purpose

### 4.1 Dialing

| ID | Meaning | Wire | Range | Confidence |
|---:|---|---|---|---|
| 0 | Dialing method: `0`/`1` = tone (DTMF), `2`/`3` = pulse | 1 byte | 0–3 | Verified |
| 1 | Tone timing A | 1 byte | 8–99 | Traced; unit unproven |
| 2 | Tone timing B | 1 byte | 8–99 | Traced; unit unproven |
| 3 | Pulse timing, split into quotient/remainder after ÷10 | 1 byte | 11–99 | Traced |
| 4 | Pulse dialing timing/control | 2 bytes BCD | 50–200 | Verified |

### 4.2 Identity, clock, maintenance

| ID | Meaning | Wire | Notes | Confidence |
|---:|---|---|---|---|
| 60 | Terminal/session identifier | 5 raw bytes | Copied into the opening frame (`0A`). Mask `EE`: only class 2 may edit. | Traced |
| 62 | Date and time | 5 BCD bytes `YY MM DD hh mm` | No century. The ROM combines the RTC's two-bit year cycle with a stored year base. | Verified |
| 250 | Maintenance time A | 2 bytes `hh mm` | Scheduler code `10`; `FF FF` = disabled. Destination 261. | Verified |
| 256 | Maintenance time B | 2 bytes `hh mm` | Scheduler code `14`; `FF FF` = disabled. Destination 267. | Verified |
| 260 | Maintenance dial prefix | 3 bytes BCD, `F` pad | Up to six digits. | Verified (keypad + dial request) |
| 261 | Maintenance destination A | 5 bytes BCD, `F` pad | Up to ten digits. Used by modes 10, 20, 22, 30, 88. | Verified (keypad + dial request) |
| 267 | Maintenance destination B | 5 bytes BCD, `F` pad | Used by modes 14/15 (`935#`, schedule B). | Verified (keypad + dial request) |
| 264 | Delay between prefix and destination | 1 byte | 0–19. 0/1/2/3 gave 0/62/125/187 delay-helper ticks in isolation; real time unit unknown. | Traced |
| 295 | Allow accounting upload stage | Boolean | `0` skips the call-record upload. Does not stop recording or charging, and does not delete records. Mask `07`: remote only. | Verified |
| 296 | Allow change-journal upload stage | Boolean | The local `93x#` routes skip this stage regardless. Mask `07`. | Verified |
| 297 | Authentication plaintext | 8 raw bytes | Input to DES; see `SERVER.md`. Mask `06`. | Verified (emulator) |
| 298 | Authentication key source | 8 raw bytes | Bytes reordered `[2,0,1,3,7,6,5,4]`, XORed with `3C AF E2 12 46 B3 59 7D`, then used as the DES key. Mask `07`. | Verified (emulator) |

262 and 263 sit right after 260/261, with the same widths (3 and 5 bytes). That
is an observation about the layout, not a finding about purpose — nothing in
the ROM reads them yet, so don't call them backup numbers.

### 4.3 Tariffs, charging and free calls

This is the newest and largest group, from the tariff investigation. The phone
holds a **dial plan** and a **tariff engine** locally. Once configured, it
classifies the dialled number, decides whether it is free or paid, times the
call and debits the card itself, without asking the server per call.

```text
Digits → dial-plan category → permission / card checks
       → free-call path   OR   paid answer supervision
       → initial charge + timed repeat charges
       → card balance write → accounting record
```

Paid categories are numbered 0–9. In the formulas below, `z` is the
zero-based paid category.

| IDs | Meaning | Wire | Notes |
|---|---|---|---|
| 114 | Answer-supervision mode, categories 1–9 | 1 byte, 0–4 | See table below |
| 115 | Answer-supervision mode, category 0 | 1 byte, 0–4 | Same modes |
| **130 + z** | Initial charge (quantity debited at answer) | 4 digits | Format 2 |
| **140 + z** | Repeat charge (debited each further period) | 4 digits | Format 2 |
| **150 + z** | Pulse-count allowance | 2 digits | With 151 = 2, three accepted pulses debit 2, 3 instead of 2, 3, 3. Policy not fully characterised. |
| **200 + z** | Pre-answer supervision timer | 4 digits | 201 = 2 starts mode-2 charging with no answer signal |
| **210 + z** | First charged-period length | 4 digits | |
| **220 + z** | Repeat-period length | 4 digits | Capped at 524 by the consumer |
| 231 | Global metering-mode selector | 1 byte, 0–3 | The metering experiments all used 1. Mask `EE`: class 2 writable, class 1 not. Earlier notes guessed "language"; the ROM's real language selector is a RAM variable (§5). |
| 232 | Time-window adjustment: which categories | 5 wire bytes = ten 0/1 digits | `01 00 00 00 00` selects category 1 (internal mask `4000`) |
| 233 | Time-window adjustment: percentage | 2 bytes BCD, 1–100 | Interval ÷ (233/100), floor. 50 doubles intervals. Amounts are not scaled. |
| 235 | Per-category mask for the local timing branch | 5 wire bytes = ten 0/1 digits | Lab default enables categories 0–9 |
| 240 / 241 | Daily window start / end | `hh mm`, `FF FF` = off | Start-inclusive, end-exclusive; 22:00→06:00 wraps midnight |
| 246 / 247 | Date window start / end | `YY MM DD hh mm` | Adjustment applies only inside the window |
| 283 | Mode-4 confirmation key | 1 byte | 1 → `#`, 2 → matrix key B, 3 → matrix key C. Setting 1 doesn't work with ordinary dialing (an upstream filter drops `#`). |

**Answer-supervision modes** (114/115). Names are descriptive, not
commercial; the physical electrical meaning of each trigger is unvalidated.

| Mode | Charging starts on | Verified call debits (100 → ...) |
|---:|---|---|
| 0 | First external pulse on PORTA bit 2 (filtered) | 2, 3, 3 for three pulses |
| 1 | A transition on controller input 13, then local timed repeats | 2, then 3 each period |
| 2 | Pre-answer timer (200 + z), no external event | 2, 3, 3, 3, 3 |
| 3 | Pulse/timer routes exist in code | Not exercised |
| 4 | Matrix key B or C (per 283), after normal paid dialing | 2, 3, 3, 3 |

**Worked example** (category 1; 131 = 2, 141 = 3, 211 = 2, 221 = 3; credit
100): answer debits 131; after 211 units debit 141; after each further 221
units debit 141 again. Over the test run the card went
100 → 98 → 95 → 92 → 89 → 86 → 83 → 80, total 20. One nominal second is 125
scheduler ticks of 8 ms, but the harness clock is not calibrated against real
time. **Verified (emulator).**

**Alternate price bank.** The card-range row in the phone (§4.4) can set a flag
(byte 2, bit `08`) that makes the phone read initial and repeat charges from
**860 + z** and **870 + z** instead of 130 + z and 140 + z. Those are *aliases*
(§4.5), not new storage. With the flag set and 861 = 7, 871 = 11 the card went
100 → 93 → 82 → 71 → 60. **Verified (emulator).**

**Card scale.** The card-range row also carries a scale factor. Charges are
rounded up to whole card units by ceiling division, with a residual carried
between charges so rounding doesn't re-round up each time. Scale 3 with
quantities 2 and 2: seven requests totalling 14 produced five one-unit card
writes, saved as scaled debit 15. **Verified (emulator).**

**What 1 unit is worth is not known.** Neither credit 100 nor charge 2
corresponds to any currency or time. The values are lab choices.

**Low credit.** Credit smaller than the initial charge still allows a call: the
ROM caps the debit to what's left and shortens the interval. Credit 0 shows
message `3C0C` and doesn't dial; credit 1 and 4 each ran through to exhaustion
(`3C17`). Three failed card writes in a row produce `3C1C` and close the call.

### 4.4 Related tables that are not settings

These are downloaded with their own message types and are not parameters:

| Item | Message | Notes |
|---|---|---|
| Dial plan (number classification) | `1F` → `20` | Staged at EEPROM `$1C00`, then programmed into flash `$8400` after validation; `$2076 = 1` selects it. The `20` reply arrives *before* validation, so it doesn't prove installation. |
| Card-range rows (32 bytes each) | `3D` | Range identity, serial interval, scale, alternate-bank flag. Does not define free numbers. |

Table layout of the dial plan, fallback plan and how digits get classified are
described in [CONFIGURATION.md](CONFIGURATION.md) §6.

### 4.5 Alias block: 850–889

IDs 160–199 are rejected when addressed directly. The same storage is reachable
as **850–889** (`alias = id + 690`). The block mirrors the live 120–159 block
exactly in shape, in the same order:

| Live | Protected (direct ID / alias) | Shape | Known role |
|---|---|---|---|
| 120–129 | 160–169 / 850–859 | 6 digits (3 wire bytes) | Unknown |
| 130–139 | 170–179 / 860–869 | 4 digits | Initial charge, categories 0–9 (alias bank) |
| 140–149 | 180–189 / 870–879 | 4 digits | Repeat charge, categories 0–9 (alias bank) |
| 150–159 | 190–199 / 880–889 | 2 digits | Pulse allowance? (alias side untested) |

So the protected block is a second **price list** the card-range flag can
switch to. Earlier notes guessed "backup snapshot"; the alias-bank result
supports "alternative tariff bank" for 860–879 at least. 120–129 and the
880–889 role are still open. Writes to the alias IDs (e.g. 861, 871) work; the
low IDs are blocked.

---

## 5. Things that look like settings but aren't

- **Display language** is not a setting. It is a RAM selector (`$078B`) cycled
  by the keypad's fourth-column `A` key at the PIN screen and reset to Romanian
  at every boot. It does not follow 231.
- **Technician PINs** are constants in ROM, not parameters.
- **Date/time** (62) is mirrored into the external clock chip; writing it runs
  the clock setter as a side effect.

---

## 6. Extended family (300–699)

Profile-dependent. Logical byte `$1BC4` selects a slot 0–4; the read address is
the descriptor base plus an offset from the slot:

| IDs | Slot contribution |
|---|---|
| 300–446 | slot × internal stride |
| 447–649 | none (fixed address) |
| 650–689 | slot × internal stride |
| 690–699 | slot × internal stride × 10 |

Examples: ID 300 reads `$1400/$1402/$1404/$1406/$1408` for slots 0–4; ID 500
stays at `$1914`; ID 690 reads `$1B60/$1B74/$1B88/$1B9C/$1BB0`.

Reading all 400 IDs against a zero-filled image gives:

| Format | Count | Result |
|---|---:|---|
| 0 (placeholder) | 230 | status 1, nothing stored |
| 1 (6 digits) | 52 | status 0 (zero is allowed) |
| 2 (4 digits) | 116 | status **4** (zero data) |
| 25 (8 digits) | 2 | status **4** (zero data) |

Status 4 here means "numeric data is zero", not "not logged in". With non-zero
data seeded into every stored slot of every profile, all **170 stored
descriptors read back with status 0** (850 reads). **Verified (emulator).**

The shape is a series of runs of ten fields at a fixed byte stride, much like
the live/alias block in §4.5. That fits per-zone or per-service counters
(everything is read-only and `AB`/`A3`), but nothing names them. Bulk-clear
service commands (`970#`–`972#`, `979#`) wipe ranges of 300–599; see
[CONFIGURATION.md](CONFIGURATION.md) §5.

---

## 7. Practical notes

- To write a base parameter you need its descriptor row: ID, wire width, format.
  Then send type `17` with the value in wire format (§2). The write goes
  through the same range check as the keypad. Verified on 0, 4, 25 and 63.
- Check the Access column before trying a local edit. `EE` slots — most of the
  tariff block (130–159, 200–247) and the terminal ID (60) — can't be changed
  from class 1. 114, 115 and 283 are `FE`.
- A write that returns status `00` has been accepted by the handler. For
  parameters that feed downstream tables or schedules (250, 256, 232–247),
  check the behaviour too — two fields (250/256) also register a scheduler
  entry.
- There is no way known to read the dial plan back. Verify it by dialling.

---

## Appendix: catalog of all stored slots

Auto-extracted from the ROM descriptor tables. IDs with identical shape are
merged into one row. The 285 zero-width placeholder IDs are omitted. "Name" is
filled in only where the purpose is established (§4); "—" means unknown.
Wire/Int are internal and wire byte counts. For ranges of IDs the address is
that of the first slot.

| ID | Count | Name | Address | Int | Wire | Access | Format | Range |
|---|---:|---|---|---:|---:|---|---:|---|
| 0 | 1 | dialing mode | $1100 | 1 | 1 | `FE` | 3 | 0–3 |
| 1 | 1 | tone dialing timing A | $1101 | 1 | 1 | `FE` | 22 | 8–99 |
| 2 | 1 | tone dialing timing B | $1102 | 1 | 1 | `FE` | 22 | 8–99 |
| 3 | 1 | pulse dialing split-decimal timing | $1103 | 1 | 1 | `FE` | 16 | 11–99 |
| 4 | 1 | pulse dialing timing/control | $1104 | 1 | 2 | `FE` | 20 | 50–200 |
| 5–6 | 2 | — | $1105 | 1 | 2 | `FE` | 14 | 1–100 |
| 10 | 1 | — | $1107 | 1 | 1 | `FE` | 6 | 0–1 |
| 11 | 1 | — | $1108 | 1 | 1 | `FE` | 11 | 1–30 |
| 12 | 1 | — | $1109 | 1 | 1 | `FE` | 12 | 5–60 |
| 13 | 1 | — | $110A | 1 | 1 | `FE` | 10 | 1–9 |
| 15 | 1 | — | $110B | 2 | 2 | `FE` | 0 | — |
| 16 | 1 | — | $110D | 1 | 1 | `FE` | 21 | 1–60 |
| 20 | 1 | — | $110E | 1 | 1 | `FE` | 7 | 0–10 |
| 21 | 1 | — | $110F | 1 | 1 | `FE` | 19 | 0–5 |
| 22 | 1 | — | $1110 | 1 | 1 | `FE` | 27 | 5–12 |
| 24 | 1 | — | $1111 | 1 | 1 | `FE` | 21 | 1–60 |
| 25–26 | 2 | — | $1112 | 1 | 1 | `FE` | 6 | 0–1 |
| 28 | 1 | — | $1114 | 2 | 5 | `FE` | 23 | — |
| 30–39 | 10 | — | $1116 | 1 | 1 | `FE` | 5 | 0–19 |
| 40–49 | 10 | — | $1120 | 1 | 1 | `FE` | 11 | 1–30 |
| 50–51 | 2 | — | $112A | 3 | 3 | `AB` | 0 | — |
| 52 | 1 | — | $1130 | 2 | 2 | `AB` | 0 | — |
| 55 | 1 | — | $1132 | 3 | 3 | `AB` | 0 | — |
| 56 | 1 | — | $1135 | 2 | 2 | `AB` | 0 | — |
| 57 | 1 | — | $1137 | 3 | 3 | `AB` | 0 | — |
| 58 | 1 | — | $113A | 2 | 2 | `AB` | 0 | — |
| 60 | 1 | terminal identifier | $113C | 5 | 5 | `EE` | 0 | — |
| 61 | 1 | — | $1141 | 5 | 5 | `EE` | 0 | — |
| 62 | 1 | date/time | $1146 | 5 | 5 | `FF` | 24 | — |
| 63 | 1 | — | $114B | 1 | 1 | `EE` | 9 | 0–2 |
| 70 | 1 | — | $114C | 1 | 1 | `FE` | 11 | 1–30 |
| 71 | 1 | — | $114D | 1 | 1 | `FE` | 21 | 1–60 |
| 75–79 | 5 | — | $114E | 3 | 3 | `CE` | 0 | — |
| 80–83 | 4 | — | $115D | 1 | 1 | `FE` | 13 | 0–99 |
| 85 | 1 | — | $1161 | 1 | 1 | `FE` | 7 | 0–10 |
| 86 | 1 | — | $1162 | 1 | 1 | `FE` | 6 | 0–1 |
| 88–89 | 2 | — | $1163 | 1 | 1 | `FE` | 11 | 1–30 |
| 90 | 1 | — | $1165 | 1 | 1 | `FE` | 13 | 0–99 |
| 91 | 1 | — | $1166 | 1 | 1 | `FE` | 6 | 0–1 |
| 92 | 1 | — | $1167 | 1 | 1 | `FE` | 10 | 1–9 |
| 95–96 | 2 | — | $1168 | 1 | 1 | `FE` | 13 | 0–99 |
| 97–98 | 2 | — | $116A | 2 | 2 | `FE` | 2 | 0–9999 |
| 100 | 1 | — | $116E | 1 | 1 | `FE` | 15 | 1–99 |
| 101 | 1 | — | $116F | 1 | 1 | `FE` | 17 | 5–99 |
| 102 | 1 | — | $1170 | 1 | 2 | `FE` | 8 | 0–199 |
| 110 | 1 | — | $1171 | 1 | 1 | `FE` | 29 | 0–30 |
| 111 | 1 | — | $1172 | 1 | 1 | `FE` | 30 | 0–60 |
| 112–113 | 2 | — | $1173 | 1 | 1 | `FE` | 6 | 0–1 |
| 114 | 1 | answer-supervision mode (cat 1-9) | $1175 | 1 | 1 | `FE` | 4 | 0–4 |
| 115 | 1 | answer-supervision mode (cat 0) | $1176 | 1 | 1 | `FE` | 4 | 0–4 |
| 116 | 1 | — | $1177 | 1 | 1 | `FE` | 6 | 0–1 |
| 117–119 | 3 | — | $1178 | 1 | 1 | `FE` | 13 | 0–99 |
| 120–129 | 10 | — | $117B | 4 | 3 | `EE` | 1 | 0–999999 |
| 130–139 | 10 | initial charge, cat z=id-130 | $11A3 | 2 | 2 | `EE` | 2 | 0–9999 |
| 140–149 | 10 | repeat charge, cat z=id-140 | $11B7 | 2 | 2 | `EE` | 2 | 0–9999 |
| 150–159 | 10 | pulse allowance, cat z=id-150 | $11CB | 1 | 1 | `EE` | 13 | 0–99 |
| 160–169 (alias 850–859) | 10 | — | $11D5 | 4 | 3 | `EE` | 1 | 0–999999 |
| 170–179 (alias 860–869) | 10 | alias bank: initial charge | $11FD | 2 | 2 | `EE` | 2 | 0–9999 |
| 180–189 (alias 870–879) | 10 | alias bank: repeat charge | $1211 | 2 | 2 | `EE` | 2 | 0–9999 |
| 190–199 (alias 880–889) | 10 | — | $1225 | 1 | 1 | `EE` | 13 | 0–99 |
| 200–209 | 10 | pre-answer timer, cat z=id-200 | $122F | 2 | 2 | `EE` | 28 | 1–9999 |
| 210–219 | 10 | first-period length, cat z=id-210 | $1243 | 2 | 2 | `EE` | 28 | 1–9999 |
| 220–229 | 10 | repeat-period length, cat z=id-220 | $1257 | 2 | 2 | `EE` | 28 | 1–9999 |
| 231 | 1 | metering-mode selector | $126B | 1 | 1 | `EE` | 3 | 0–3 |
| 232 | 1 | time-window adjustment categories | $126C | 2 | 5 | `EE` | 23 | — |
| 233 | 1 | time-window adjustment percent | $126E | 1 | 2 | `EE` | 14 | 1–100 |
| 235 | 1 | timing-branch category mask | $126F | 2 | 5 | `EE` | 23 | — |
| 240 | 1 | daily window start | $1271 | 2 | 2 | `EE` | 18 | — |
| 241 | 1 | daily window end | $1273 | 2 | 2 | `EE` | 18 | — |
| 246 | 1 | date window start | $1275 | 5 | 5 | `EE` | 24 | — |
| 247 | 1 | date window end | $127A | 5 | 5 | `EE` | 24 | — |
| 250 | 1 | maintenance time A | $127F | 2 | 2 | `FE` | 18 | — |
| 251 | 1 | — | $1281 | 2 | 2 | `FE` | 18 | — |
| 252 | 1 | — | $1283 | 1 | 1 | `FE` | 13 | 0–99 |
| 253 | 1 | — | $1284 | 1 | 1 | `FE` | 17 | 5–99 |
| 254 | 1 | — | $1285 | 1 | 1 | `FE` | 15 | 1–99 |
| 255 | 1 | — | $1286 | 1 | 1 | `FE` | 5 | 0–19 |
| 256 | 1 | maintenance time B | $1287 | 2 | 2 | `FE` | 18 | — |
| 257 | 1 | — | $1289 | 1 | 1 | `FE` | 5 | 0–19 |
| 258 | 1 | — | $128A | 2 | 2 | `FE` | 2 | 0–9999 |
| 260 | 1 | maintenance dial prefix | $128C | 3 | 3 | `FE` | 0 | — |
| 261 | 1 | maintenance destination A | $128F | 5 | 5 | `FE` | 0 | — |
| 262 | 1 | — | $1294 | 3 | 3 | `FE` | 0 | — |
| 263 | 1 | — | $1297 | 5 | 5 | `FE` | 0 | — |
| 264 | 1 | prefix-to-destination pause | $129C | 1 | 1 | `FE` | 5 | 0–19 |
| 266 | 1 | — | $129D | 3 | 3 | `FE` | 0 | — |
| 267 | 1 | maintenance destination B | $12A0 | 5 | 5 | `FE` | 0 | — |
| 275 | 1 | — | $12A5 | 1 | 1 | `FE` | 5 | 0–19 |
| 276 | 1 | — | $12A6 | 1 | 1 | `FE` | 21 | 1–60 |
| 277 | 1 | — | $12A7 | 2 | 5 | `FE` | 23 | — |
| 278 | 1 | — | $12A9 | 1 | 1 | `FE` | 9 | 0–2 |
| 279–281 | 3 | — | $12AA | 1 | 1 | `FE` | 6 | 0–1 |
| 282 | 1 | — | $12AD | 1 | 1 | `FE` | 9 | 0–2 |
| 283 | 1 | mode-4 confirmation key | $12AE | 1 | 1 | `FE` | 4 | 0–4 |
| 284–285 | 2 | — | $12AF | 1 | 1 | `FE` | 6 | 0–1 |
| 286–293 | 8 | — | $12B1 | 1 | 2 | `FE` | 26 | 1–200 |
| 294 | 1 | — | $12B9 | 1 | 1 | `87` | 6 | 0–1 |
| 295 | 1 | accounting-upload enable | $12BA | 1 | 1 | `07` | 6 | 0–1 |
| 296 | 1 | change-journal-upload enable | $12BB | 1 | 1 | `07` | 6 | 0–1 |
| 297 | 1 | authentication plaintext | $12BC | 8 | 8 | `06` | 0 | — |
| 298 | 1 | authentication key source | $12C4 | 8 | 8 | `07` | 0 | — |
| 299 | 1 | — | $12CC | 2 | 1 | `A3` | 0 | — |
| 300 | 1 | — | $1400 | 2 | 2 | `AB` | 2 | 0–9999 |
| 305 | 1 | — | $140A | 4 | 3 | `AB` | 1 | 0–999999 |
| 306 | 1 | — | $141E | 2 | 2 | `AB` | 2 | 0–9999 |
| 307 | 1 | — | $1428 | 4 | 3 | `AB` | 1 | 0–999999 |
| 310–319 | 10 | — | $143C | 2 | 2 | `AB` | 2 | 0–9999 |
| 331–337 | 7 | — | $14A0 | 2 | 2 | `AB` | 2 | 0–9999 |
| 340–349 | 10 | — | $14E6 | 4 | 3 | `AB` | 1 | 0–999999 |
| 351–353 | 3 | — | $15AE | 2 | 2 | `AB` | 2 | 0–9999 |
| 355–357 | 3 | — | $15CC | 2 | 2 | `AB` | 2 | 0–9999 |
| 360–369 | 10 | — | $15EA | 2 | 2 | `AB` | 2 | 0–9999 |
| 371–373 | 3 | — | $164E | 2 | 2 | `AB` | 2 | 0–9999 |
| 375 | 1 | — | $166C | 2 | 2 | `AB` | 2 | 0–9999 |
| 377–389 | 13 | — | $1676 | 2 | 2 | `AB` | 2 | 0–9999 |
| 390–409 | 20 | — | $16F8 | 4 | 3 | `AB` | 1 | 0–999999 |
| 420 | 1 | — | $1888 | 4 | 4 | `AB` | 25 | 0–99999999 |
| 422 | 1 | — | $189C | 2 | 2 | `AB` | 2 | 0–9999 |
| 423 | 1 | — | $18A6 | 4 | 4 | `AB` | 25 | 0–99999999 |
| 430–432 | 3 | — | $18BA | 2 | 2 | `AB` | 2 | 0–9999 |
| 435–436 | 2 | — | $18D8 | 2 | 2 | `AB` | 2 | 0–9999 |
| 440–441 | 2 | — | $18EC | 2 | 2 | `AB` | 2 | 0–9999 |
| 445–446 | 2 | — | $1900 | 2 | 2 | `AB` | 2 | 0–9999 |
| 500–508 | 9 | — | $1914 | 2 | 2 | `AB` | 2 | 0–9999 |
| 520–522 | 3 | — | $1926 | 2 | 2 | `AB` | 2 | 0–9999 |
| 530 | 1 | — | $192C | 2 | 2 | `AB` | 2 | 0–9999 |
| 532 | 1 | — | $192E | 2 | 2 | `AB` | 2 | 0–9999 |
| 543–544 | 2 | — | $1930 | 2 | 2 | `AB` | 2 | 0–9999 |
| 550 | 1 | — | $1934 | 2 | 2 | `AB` | 2 | 0–9999 |
| 555–556 | 2 | — | $1936 | 2 | 2 | `AB` | 2 | 0–9999 |
| 560–562 | 3 | — | $193A | 2 | 2 | `AB` | 2 | 0–9999 |
| 570–572 | 3 | — | $1940 | 2 | 2 | `AB` | 2 | 0–9999 |
| 574–582 | 9 | — | $1946 | 2 | 2 | `AB` | 2 | 0–9999 |
| 650–659 | 10 | — | $1958 | 2 | 2 | `AB` | 2 | 0–9999 |
| 660–679 | 20 | — | $19BC | 4 | 3 | `AB` | 1 | 0–999999 |
| 690–699 | 10 | — | $1B60 | 2 | 2 | `A3` | 2 | 0–9999 |
