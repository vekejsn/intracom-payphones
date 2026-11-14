# Call Records and Uploads

How the phone stores call records, what is in each 26-byte record, how records
and status lists are uploaded to the server, and which maintenance routes do
what. For the protocol itself see [SERVER.md](SERVER.md); for how charging
works see [PHONE.md](PHONE.md) §6.

All of this is from the firmware image run in an emulator with simulated
card reader, clock, modem and server. "Verified" means the original ROM code
did it there; no real call or server has been observed. The real-world units of
the record's numeric fields are **not** known.

---

## 1. The 26-byte record

A record is built field by field by the serializer at selector 2 `$E0F1`. Most
fields are a number written as N **decimal digits** (two per byte), keeping
only the least-significant N digits. A value that doesn't fit is silently
truncated: 65535 becomes `5535` in a four-digit field. So a record is not a
lossless dump of what the phone holds internally.

| Bytes | Digits | Contents | What we know |
|---|---|---|---|
| 0–1 | 4 | First field | Not a sequence number (see below) |
| 2–9 | 16 | Dialled digits | Packed BCD, unused nibbles `F` |
| 10 | 2 | Month | 4-bit source |
| 11 | 2 | Day | 5-bit source |
| 12 | 2 | Hour | 5-bit source |
| 13 | 2 | Minute | 6-bit source |
| 14–15 | 4 | Call length | `max(0, end − start) + extra`, low 16 bits, in the ROM's "nominal second" |
| 16–18 | 6 | Numeric A | In lab calls: amount debited, scaled by the card scale |
| 19–21 | 6 | Numeric B | In lab calls: remaining credit, scaled |
| 22–24 | 6 | Outer context value | In lab calls: the normalised card serial |
| 25 | 2 | Status byte | 0–99; observed 2; meaning unknown (producer asserts ≤ 2) |

**Decoded example** (from the two-record provisioning test; the record was
fabricated for the test, not produced by a call):

```text
12 34 | 07 12 34 56 78 FF FF FF | 11 13 10 05 | 00 60 | 00 00 01 | 00 00 99 | 34 56 78 | 02
 1234    dialled 0712345678       Nov 13 10:05    60      1          99        345678     2
```

### What the numbers are, as far as we can tell

- **Bytes 0–1** came from the downloaded card-range row's ID in the lab
  calls. Earlier notes called this a sequence number; that is withdrawn. Don't
  use it as a unique call ID.
- **Call length (14–15).** The ROM adds the elapsed difference of a 32-bit
  counter incremented once per 125 scheduler updates (a "nominal second") to a
  small extra byte. That is the ROM's own timebase. Its relation to real
  seconds depends on the real oscillator and is unmeasured.
- **A and B** are products of a quantity and the card's scale factor (`$06F7`,
  a BCD value 1–99; invalid BCD becomes 99, zero becomes 1). In a lab call
  with scale 3 the record carried scaled debit 21 and scaled balance 279 for a
  raw debit of 7 off a raw 100. That supports "A = debit, B = balance" for
  lab calls. It doesn't say what one unit is worth.
- **Outer value** took the card serial in lab calls, not a lifetime total.
- **Status byte** is a one-byte value copied from RAM; the producer expects it
  to be at most 2. Whether it encodes a disconnect reason, call class or
  something else isn't established.

---

## 2. Where records live

Pending records sit in EEPROM in **28-byte slots** starting at logical
`$4000` (index × `$1C`): 2 bytes (first field), 4 bytes (outer value), then a
22-byte inner structure (8 dialled bytes, timestamp, quantities, status). The
uploader reads these and reassembles the 26-byte wire record.

A six-byte header at logical `$0C7A` tracks pending/committed counts. A fresh
header after one append reads `01 00 01 01 00 01`; after the server acknowledges
the record it reads `01 00 01 01 01 00`: pending 1 → 0. **The stored record
bytes stay in place** — acknowledgement advances an iteration state, it
doesn't erase. The exact meaning of each header byte isn't documented; the
pattern above is what was observed.

Appending takes two locks (record storage, configuration access) and is done by
`$DEF1`. In the emulator the append was run in isolation with a declared
task/lock context, and also as part of a complete modelled card call.
Persistence is to the emulated EEPROM; real power-loss behaviour is untested.

### How the producer fills a record

Static trace of the producer at selector 1 `$CC04`:

1. ASCII digits from `$0518`, length 1–16, packed into 8 bytes, padded with `F`.
2. Timestamp from clock-derived bytes `$04B3–$04B6`.
3. Length from the two counter snapshots (start `$04BE`, end `$04C2`) plus
   extra `$0716`.
4. A and B from word differences multiplied by the card scale.
5. Status from `$0713`.
6. Context values from `$04D3` (4 digits) and `$04D0` (6 digits) passed to
   `$DEF1`, which writes the pending slot.

---

## 3. Uploading records (type `32`)

A batch frame carries up to **eight** records:

```text
32 TYPE=32 LEN ...  payload = COUNT | record(26) × COUNT | 03/04
```

Marker `03` = more batches follow, `04` = final batch. The pending count is
committed one batch at a time, after the server acknowledges it.

| Pending | Batches sent | Pending after each |
|---:|---|---|
| 1 | 1 | 0 |
| 9 | 8 then 1 | 1, 0 |
| 8 | 8 then an empty final batch (`00 04`) | 0 |
| 0 | `32: 00 04` (empty) | 0 |

A second session from the saved EEPROM sends an empty batch; it doesn't resend
an acknowledged record. If a session is cut after the first batch commits,
a fresh session uploads only the remaining record(s). **Verified** at the
checkpoint (not arbitrary power loss).

### Acknowledgement faults (single scripted faults)

| Peer behaviour | Phone response |
|---|---|
| Wrong-sequence ACK (`80` when `A0` expected) | Retransmits the whole batch byte-for-byte. Pending stays until a correct ACK, then commits once. |
| `C0` instead of an ACK | A separate control exchange, no data retransmission. Not a generic "resend". |
| `C0` repeated (three times) | Session ends in a bounded failure, **`EROARE:773`**. Nothing committed; all records stay pending. |
| Fresh manual session afterwards | Uploads everything normally. |

The stored diagnostic byte `$2066` stays 7 after a recovered failure, so don't
read it as "the last session failed". Tested against single faults only — this
isn't a proof of exactly-once delivery or of behaviour on a bad line.

### Controlling the upload: setting 295

| 295 | Effect |
|---:|---|
| 1 | The accounting stage runs where the route includes it |
| 0 | Stage skipped. The session still completes. Records stay pending and nothing is deleted. |

295 doesn't switch off charging or recording. It is `07` access: the remote
server can write it, the keypad can't. Writing 0 remotely and then 1 again
leaves the record pending until the next session, which uploads it.

---

## 4. Maintenance modes: what each route sends

Each mode picks a sequence of stages from a table at selector 2 `$EA47`: ten
groups of seven pointers. Every sequence starts with opening (`$A06D`, type
`0A`) and authentication (`$A361`, type `0C`), and ends in the common
server-command loop (`$A919`). In between come optional upload stages.

| Stage | Routine | Type | Gated by |
|---|---|---|---|
| Opening / negotiation | `$A06D` | `0A` | — |
| Authentication | `$A361` | `0C` | Not present in group 1 |
| Status-2 identifier list | `$A475` | `10` | route |
| Status-1 identifier list | `$A521` | `12` | route |
| Accounting records | `$A5CC` | `32` | 295 = 1 |
| Change journal | `$A6AE` | `24` | 296 = 1 **and** not a local route |
| Server commands | `$A919` | — | — |

| Keys | Mode / group | Dest. | Uploads |
|---|---|---|---|
| `932#` | `22` / 8 | 261 | status-2, status-1 |
| `934#` | `20` / 7 | 261 | status-2 |
| `935#` | `14` / 3 | 267 | status-2, accounting |
| `936#` | `88` / 9 | 261 | status-2, accounting |
| `939#` | `30` / 4 | 261 | accounting |
| `930#` | `60` / 1 | 261 | initialisation; no authentication |
| scheduled A | `10`/`11` | 261 | status-2, accounting, journal |
| scheduled B | `14`/`15` | 267 | status-2, accounting, journal |

Mode numbers are hexadecimal. The group code in the opening frame is **not**
the trigger mode: group 9 goes out as `82`. These tables are from tracing with
the stage bodies stubbed, apart from `935#`, which was run all the way
through. There's no download-only route: every route ends in the same
server-command loop that accepts settings and update commands.

### Opening frame (`0A`)

```text
01 | 5 bytes of setting 60 | counter/state | update state | group | 00 | marker
```

Example for group 9: `01 01 23 45 67 89 03 07 82 00 03`. Counter and state
fields are only partly understood.

### Status identifier lists (`10`, `12`)

The firmware tracks **13 status entries** (state bytes at `$0C50`). Each entry
maps to a fixed ID, all inside the extended range:

`522, 543, 544, 550, 555, 556, 575, 576, 578, 579, 580, 581, 582`

- Type `10` takes entries in state 2, sends their IDs, and sets them to state 3.
- Type `12` takes entries in state 1, sends their IDs, and sets them to 0.
- Payload: `COUNT | ID_hi ID_lo × COUNT | 04`; with none, `00 04`.
  Example `02 02 0A 02 26 04` = IDs 522 and 550.

Only IDs go out, not values. What each ID signals (alarms? counters?) isn't
known, and the same IDs are what `951#` shows as status slots.

### Change journal (`24`)

Raw journal bytes from a nonvolatile region (pointer at `$0C98`, data from
`$0C9A`): `01 06 00 04 02 01 00 64 04` in the seeded test. It's appended to
when settings are changed. How the server acknowledges and clears it hasn't
been exercised.

---

## 5. Unknowns

- Units of the call length, A and B; what one card unit costs.
- Meaning of the status byte and of the header bytes at `$0C7A`.
- Whether the 4-digit first field is anything other than the card-range ID.
- Behaviour on a real line: retry, redial, partial uploads.
- Real power-loss safety of append and commit.
