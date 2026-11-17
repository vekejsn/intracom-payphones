# Configuration Guide

How the phone is configured: the local technician menu, the maintenance
call-home, and what the server sends to provision a phone. For what each
setting means see [SETTINGS.md](SETTINGS.md); for the protocol see
[SERVER.md](SERVER.md); for how the phone works generally see
[PHONE.md](PHONE.md).

> **This is reverse-engineering notes, not a service manual.** Every procedure
> below was run against the firmware in an emulator with simulated hardware.
> Several service commands clear configuration or start firmware updates. Do
> not try unknown commands on real equipment. Entries marked **Verified** were
> reproduced in the emulator; none has been confirmed on a physical phone.

---

## 1. Getting into the service menu

1. **Hold the service input during reset.** The ROM reads a candidate service
   switch on the keypad scan line (input byte 1, bit 2, active low) at boot.
   The firmware doesn't say what physical switch this is. **Working
   assumption (unconfirmed):** it is the switch labelled **SW700** on the
   main board, a small slide/toggle switch next to the `CUN701` connector,
   below the `R4R1C` ROM. This comes from looking at a board photo, not from
   tracing SW700's wiring to the keypad scan line; it could equally be the
   self-test input (§1, last paragraph). Check with a meter before relying on
   it. Switching it after boot didn't reproduce the prompt in testing, so
   set it before reset.
2. The display shows the PIN prompt:

   | Language | Prompt |
   |---|---|
   | Romanian | `TIPARESTE CODUL` |
   | English | `ENTER PIN NUMBER` |
   | French | `ENTREZ NUM. DE CODE` |
   | German | `CODENUMMER EINGEBEN` |

   Press `A` (matrix fourth column, top row) to cycle the language. It resets
   to Romanian at the next boot.
3. Enter a PIN followed by `#`. Each digit shows as `*`.

| PIN | Access argument | Notes |
|---|---:|---|
| `555657#` | 1 | Technician class 1 |
| `336633#` | 2 | Technician class 2 |

Both are constants in the firmware (the comparison code is at selector 0
`$DB65–$DBC4`), and both lead to the same `TESTARE` ("TEST") menu. The ROM also
has some configuration-based PIN comparisons that aren't mapped.

The two classes differ in what they can do, not in a simple order:

- Class 2 can write settings that class 1 can't (mask `EE`, e.g. 60 and 231).
- Class 2 can enter nine service commands class 1 is refused:
  `903 910 911 950 956 957 996 997 999`.
- Neither is read-only or safe.

**A second entry point:** holding input byte 1 bit 0 low at reset skips the PIN
and goes straight to the self-test sequence (`TESTARE`, then `EROARE 572 /
802 / 803` on a failing test). Physical identity unknown.

---

## 2. The TESTARE menu

At `TESTARE`, every command is **exactly three digits followed by `#`**,
leading zeros included. Single-digit entries are rejected.

| Entry | Path |
|---|---|
| `000#`–`299#` | Base-parameter editor. Per-setting access still applies. |
| `300#`–`699#` | Extended numeric **view**. Not an editor; typing a new value does nothing. |
| `700#`–`849#` | Rejected. |
| `850#`–`899#` | Base editor path. Only aliases 850–889 are established. |
| `900#`–`999#` | Special service commands (§5). |

Keys while viewing a setting: digits enter a replacement value, `#` confirms,
`*` cancels back to `TESTARE` without changing anything. For the maintenance
time fields, an empty `#` is **not** a cancel (§4).

### Reading and writing a setting

| Keys | Effect | Evidence |
|---|---|---|
| `004#` | Show parameter 4 (pulse timing). Fixture showed `0100`. | Verified |
| `0064#` | Store decimal 64 and return to `TESTARE` | Verified |
| `004#` | Reads back `0064`; survives rebooting from the saved EEPROM | Verified |
| `*` | Cancel the current view | Verified |
| `000#` | Dialing mode. `0`/`1` tone, `2`/`3` pulse | Verified |
| `060#0123456789#` | Terminal identifier (5 bytes). **Class 2 only** | Verified |
| `062#2611120002#` | Set date/time, `YY MM DD hh mm` = 2026-11-12 00:02 | Verified |

The value typed is in the setting's *wire* format: decimal digits for
numeric fields (`0064`, not `40`). A setting the PIN class can't write simply
doesn't change (for example `555657#` then `231#02#` leaves 231 at `01`).

**Clock.** Writing 062 also sets the external clock chip. The ROM combines the
clock's two-bit year cycle with a stored base, so an uncommissioned phone can
show a wrong year on its own. This verifies the emulated setter, not RTC
battery behaviour.

**Settings with an unknown purpose.** The editor will happily show and (if the
mask allows) write about 245 base settings. Writing a value of unknown
purpose is a good way to break a phone. See [SETTINGS.md](SETTINGS.md) §4.

---

## 3. Maintenance numbers

The phone dials the server itself. Three settings give the number:

| Keys (example) | Effect |
|---|---|
| `260#9#` | Common prefix `9` (up to 6 digits) |
| `261#0212345679#` | Destination A (up to 10 digits) |
| `267#0312345678#` | Destination B (up to 10 digits) |
| `261#` then `*` | View without changing |

The numbers here are laboratory examples, not recovered server numbers.

- Leading zeros are kept. Short input is padded with `F`; the dialler stops at
  the first `F`. Prefix `9` is stored `9F FF FF` and shows as `9FFFFF`.
- The dialler sends the prefix, waits per setting 264, then sends the
  destination. An empty 261 stops the call before dialling.
- Destination **A (261)** is used by scheduled code `10` and by modes 20, 22,
  30, 88. Destination **B (267)** is used by scheduled code `14` and by
  `935#`.
- 262 and 263 haven't been shown to be used.

The consumer routine (selector 2 `$BA36`) hands prefix and destination
separately to the dial-request routine. The tests intercepted the dial
request; a completed telephone call wasn't made. **Verified** keypad entry,
read-back and reboot.

### Scheduled maintenance

| Keys | Effect |
|---|---|
| `250#1234#` | Time A = 12:34, registers scheduler code `10` |
| `256#1235#` | Time B = 12:35, registers scheduler code `14` |
| `250##` | Empty confirm: stores `FF FF`, deactivates codes `10/11` |
| `256##` | Same for time B, codes `14/15` |
| `250#` then `*` | View without changing |

Don't edit the scheduler's internal table (eight 4-byte entries at `$07D0`) by
hand: its minute word depends on clock and flags. When a code falls due, the
ROM starts a maintenance session with that code. In the emulator a due schedule
runs through to a complete call, but only with a modelled wake-up (cold reset
plus an alarm-status input); how a real board wakes isn't known. See
[CALL-HOME.md](CALL-HOME.md) §4.

---

## 4. Starting a maintenance call from the keypad

From `TESTARE`:

| Keys | Mode | Destination | Uploads before the server takes over |
|---|---|---|---|
| `932#` | 22 | 261 | status lists 2 and 1 |
| `934#` | 20 | 261 | status list 2 |
| `935#` | 14 | 267 | status list 2, then accounting |
| `936#` | 88 | 261 | status list 2, then accounting; wire group 82 |
| `939#` | 30 | 261 | accounting |
| `930#` | 60 | 261 | **Initialisation route. Clears things before calling.** |

The accounting stage only runs if setting 295 = 1. The change-journal stage
(296) is skipped on these local routes. Each route sends the opening frame
(type `0A`), the authentication response (`0C`) where the group has one, and
then enters the common server-command loop where the server issues reads,
writes and updates. These are *dispatch* results: the lab has run `935#`
through a complete call, not each mode.

There is no "download only" command. Everything the server wants to do —
settings, tables, firmware — happens in the shared command loop after the
opening.

### Factory blank → provisioned

What the lab did from an all-`FF` configuration EEPROM (**Verified**, group-1
bootstrap, then authenticated group-3 call):

1. Boot with the service input held. The ROM initialises the EEPROM (about 66 s
   on the lab clock) and reaches the PIN prompt.
2. Enter, in order:

   | Entry | Purpose |
   |---|---|
   | `336633#` | Class 2 (class 1 can't write 060) |
   | `060#0123456789#` | Terminal ID |
   | `062#2611131002#` | Date/time |
   | `260#9#` | Maintenance prefix |
   | `261#0212345679#` | Destination A |
   | `267#0312345678#` | Destination B |
   | `930#` | Start the initialisation call |

3. The phone sends the opening frame (group 1) and waits. The server
   writes and reads back, one `17`/`18` and `15`/`16` pair each, setting 4
   and then **295** (=1), **296** (=1), **297** and **298** (the 8-byte
   authentication inputs), then finishes with `0B` and `02`. The phone
   clears its pending-initialisation flag and shows `OK`.
4. Group 1 has no authentication stage, so the first call is not authenticated.
   That matches what the ROM does; it hasn't been invented.
5. From then on `336633#935#` makes a group-3 call, which authenticates with
   DES from the stored 297 and 298.

Those numbers and keys are lab choices. **Do not use `930#` on a configured
phone.**

---

## 5. Service commands 900–999

Of the 100 slots, **34 are real commands** (29 distinct handlers). The other 66
go to the generic error routine and show `EROARE`. This counts dispatch
entries, not understood features. Each slot was tried separately under both
PINs on copies of a synthetic EEPROM.

**Risk:** `!` = clears or resets state.

### Diagnostics

| Entry | Function | Min. class | Notes |
|---|---|---:|---|
| `900#` | Keypad echo test | 1 | Typing `123#*` shows `123BA` |
| `901#` | LCD pattern test | 1 | `#` cycles patterns, `*` exits |
| `903#` | Peripheral diagnostic | 2 | Shows `CU 0` on the fixture |
| `904#` | Input/output diagnostic | 1 | Physical functions unknown |
| `907#` | Update status | 1 | Two image checksums, selection indicator, update state |
| `908#` | Event/status diagnostic | 1 | Hex fields |
| `910#` | Multi-output diagnostic | 2 | Drives outputs |
| `911#` | Output-control diagnostic | 2 | Digits and C/D; drives outputs |
| `920#` | DTMF/pulse test prompt | 1 | Shows `1/2-DTMF/Pulse`; tone generation unverified |
| `950#` | Diagnostic summary | 2 | e.g. `1 23:59 98` on the fixture |
| `988#` | Five-channel input diagnostic | 1 | |
| `989#` | Controller mode/flag | 1 | |

### Stored-data browsers

| Entry | Shows | Keys |
|---|---|---|
| `951#` | Status/counter slots | `#` next, `*` exit. **Key `9` can clear** under class 2. `!` |
| `952#` | `Tr` records | `*` exit; statically `#`/`5`/`0` step 1/5/10, `1`–`4` pages. Only an empty `Tr 0` was seen. |
| `956#` | `Sr` entries (class 2) | Count first; `#` open/next, `B` previous, `1`/`2`/`3` field pages, `*` exit |
| `957#` | `Bl` entries (class 2) | Count first; `#` open/next, `B` previous, `*` exit |

Contents of `Tr`, `Sr` and `Bl` haven't been interpreted; seeded test data
displayed correctly.

### Maintenance sessions

`930#`, `932#`, `934#`, `935#`, `936#`, `939#`: see §4. `930#` is `!`.

### Clearing and reset commands — `!`

| Entry | Effect (static trace) |
|---|---|
| `970#` | Clear extended IDs 300–499 (skips 440 and 445) |
| `971#` | Clear extended IDs 500–559 |
| `972#` | Clear extended IDs 560–599 |
| `979#` | Clear extended 300–699 and the RAM index array |
| `990#` | Initialisation/clear A (zero-fills 20 bytes at `$0C60`); shows `EROARE 803` |
| `991#` | Initialisation/clear B (zero-fills `$0DF0`) |
| `992#` | Table/index reset, includes IDs 440 and 445 |
| `994#` | Clears logical state byte `$2076`, which de-selects a downloaded dial plan |
| `996#` | Reset state, sets `$2070` to `FF` (class 2) |
| `997#` | Reset operation, sets `$2072` to `FF` (class 2) |
| `998#` | Maintenance operation, effect unresolved |
| `999#` | Clears four bytes at `$0DF4` (class 2) |

All were exercised only on synthetic EEPROM copies, and mostly statically
traced for effect. Some changed several bytes. None of these should be run on a
phone that needs to keep working.

---

## 6. Configuring tariffs and the dial plan (remote)

Tariffs and dial plan are set from the server, not the keypad: the tariff
settings are mostly mask `EE` (class 2 can edit them locally, in principle,
but only the remote path was tested), and the dial plan and card ranges are
tables, not parameters. All of the following were done in one authenticated
maintenance session in the emulator.

### Prerequisites

- Terminal ID (060), maintenance prefix and destination, and the
  authentication inputs (297/298) already set, as in §4.
- Settings that gate a category: card acceptance, paid-category permissions,
  supervision mode (114/115), and prices/intervals for the category. Setting
  131 alone doesn't enable a barred category or define "answered".

### A. Tariff and supervision settings

Use type `17` to write, `15` to read back. The phone answers with `18` and
`16`. IDs are binary, values BCD. For parameter 131 = 2:

```text
Server → phone   17:  01 00 83 02 00 02 04       write 131 = 0002
Phone  → server  18:  01 00 83 00 04             status 0
Server → phone   15:  01 00 83 04                read 131
Phone  → server  16:  01 00 83 00 02 00 02 04    131 = 0002
```

With the framing and CRC (frames from the lab transcript):

```text
Server → phone  32 17 00 06 01 00 83 02 00 02 04 D8 90
Phone  → server 32 18 00 04 01 00 83 00 04 A4 81
Server → phone  32 15 00 03 01 00 83 04 03 E3
Phone  → server 32 16 00 07 01 00 83 00 02 00 02 04 DB 0A
```

The lab's standard tariff provisioning wrote 114, 131, 141, 211, 221, 231 and
235, each followed by a read-back:

| ID | Value | Meaning |
|---:|---|---|
| 114 | `01` | Supervision mode 1 |
| 131 | `0002` | Category 1 initial charge 2 |
| 141 | `0003` | Category 1 repeat charge 3 |
| 211 | `0002` | First period 2 |
| 221 | `0003` | Repeat period 3 |
| 231 | `01` | Metering mode 1 |
| 235 | `1111111111` | Timing branch enabled for categories 0–9 |

Values are lab examples, not any operator's tariff. Always check each write's
status and read back; a link ACK alone doesn't prove a value was stored.

Other provisioned examples: `232:0100000000 233:0050 246:2611010000
247:2611302359` (stretch category 1's charging periods to twice their length
during November 2026; the amounts don't change), `114:04 283:02` (mode 4, key B confirms the
answer), `861:0007 871:0011` (alternate bank prices).

### B. Card-range row

A type `3D` download of a 32-byte row sets which cards are accepted: range
identity, serial interval, scale and the alternate-bank flag (byte 2, bit
`08`). On boot the ROM rebuilds its card index. It does not define free
numbers. Beyond those fields the row layout hasn't been written up.

### C. Dial plan (number classification)

Sent as type `1F` blocks (`01 length offset_hi offset_lo data marker`; marker
`03` for continuation blocks, `04` for the last). The phone answers `20` with
payload `01 00 04` **before** it validates anything.

1. Blocks stage the table at EEPROM `$1C00`.
2. After the final block the ROM validates geometry and prefix lengths, then
   programs 4×256 bytes into each flash half at `$8400–$87FF`.
3. It sets `$2076 = 1`. The next boot uses `$8400` instead of the built-in
   fallback.

A table with bad geometry still gets the positive `20` reply and a session
`OK` but changes nothing. So the reply and the `OK` aren't proof of
installation; the lab checked flash contents and then classified digits on a
fresh boot. There's no known read-back command for the table.

Table layout:

```text
+0       G   bytes in a candidate mask
+1       L   maximum prefix length
+2..3    N   entry count (big endian)
+4       N   raw category bytes
+4+N     N   prefix-length bytes
+4+2N    L × 10 × G digit masks
Total = 4 + 2N + 10·G·L bytes
```

For each entry and each position, the digit masks say which digits are
permitted. The built-in fallback is G=1, L=3, N=8 (50 bytes). The lab's
replacement used L=4, N=3 (also 50 bytes): `0800` free (`20`), `07` paid
category 1 (`02`), `911` free (`20`). A builder/decoder for this format exists in the research
folder (`dial_plan.py`); it isn't in this repository's `tools/` yet.

> **The lab plan is a test fixture.** It covers three prefixes and leaves
> everything else unclassified. A real plan must cover the complete numbering
> scheme with non-overlapping prefixes (the classifier is not longest-match).
> Never load a three-entry plan on a phone that takes real calls.

A free-call prefix like `0800` is therefore not built into the firmware: in
the fallback plan `08…` is paid category 1. Whether a real operator's phones
treated it as free depended on the plan they had been sent.

### D. Whole session, in order

1. Technician starts the call (`336633#935#`); modem carrier comes up.
2. Phone sends opening, capabilities and DES response; server checks DES and
   sends `0D`.
3. Phone uploads status lists and any records.
4. Server writes and reads back the tariff settings (§A).
5. Server downloads the card-range row (`3D`), then the dial plan (`1F`).
6. Server sends the scheduling instruction and completion (`0B`, `02`).
7. Phone shows `OK`. Verify by reading settings back and test-dialling; `OK`
   alone doesn't prove everything landed.

---

## 7. Quick reference

| Task | Keys / message |
|---|---|
| Enter service menu | Hold service input at reset; `555657#` or `336633#` |
| Read setting _nnn_ | `nnn#` (`*` to leave) |
| Write setting _nnn_ | `nnn#` then value then `#` |
| Set clock | `062#YYMMDDhhmm#` |
| Set maintenance numbers | `260#`, `261#`, `267#` |
| Set maintenance times | `250#hhmm#`, `256#hhmm#` (`250##` disables) |
| Call the server | `935#` (A: `932#`, `934#`, `936#`, `939#`) |
| Self-test | `900#`, `901#`, `920#` |
| Remote read / write | type `15` / `17` |
| Dial plan / card range | type `1F` / `3D` |
