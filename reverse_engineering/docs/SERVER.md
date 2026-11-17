# Server Protocol Overview

An overview of the remote-maintenance protocol implemented by the firmware, together with what we have actually established about it.

Everything below comes from firmware inspection (the unscrambled image of
`firmwares/R4R1C/UNSCRAMBLED.BIN`) and from exercising individual routines in
an emulator. It is *not* the result of capturing a conversation with a real
central server — no such capture exists yet.

Confidence labels used throughout:

| Label | Meaning |
|---|---|
| **Verified** | Reproduced by running the original ROM code and observing the result. |
| **Traced** | Found in the disassembly by following the code path; not executed end-to-end. |
| **Hypothesis** | Consistent with the ROM, but not confirmed. |

---

## 1. The stack at a glance

The phone is not a passive terminal: it contains a client for an operator-side
maintenance system (the **CSMS** on the Intracom/Intrarom side). The protocol
has three layers, and only the upper two have been pinned down.

| Layer | What it does | State of knowledge |
|---|---|---|
| Application | Message types, payload layouts, CRC, session logic | **Verified / traced** in detail |
| Framing | Start marker, type, length, payload, checksum | **Verified** |
| Transport | UART to some line/modem device | **Hypothesis** (V.23, ~1200 bit/s) |

One distinction matters throughout: the ROM proves how the CPU *formats*
bytes. It does not prove those exact bytes reach the remote server unchanged.
A modem or line interface can sit between the CPU and the network.

The phone also contains a **V.23 asynchronous modem** (per the marketing
material), so a serial line is the plausible physical path — but the peer
device attached to that serial port has not been identified.

---

## 2. Framing

### Normal frames

```text
32 | TYPE | LEN HIGH | LEN LOW | CONTENT ... | CRC HIGH | CRC LOW
```

| Field | Meaning |
|---|---|
| `32` | Start of a normal frame (hex `0x32`, not decimal 32) |
| `TYPE` | What the frame does (settings read, write, upload, update…) |
| `LEN HIGH`, `LEN LOW` | Big-endian length of the **content**, **minus one** |
| `CONTENT` | Command-specific payload |
| `CRC HIGH`, `CRC LOW` | CRC-16 over everything from `32` to the last content byte, high byte first |

The "minus one" is the single most common source of off-by-one errors when
writing a decoder: a length field of `00 01` means **two** content bytes.

The last content byte is a marker:

- `03` — continuation block, more traffic for this message follows.
- `04` — final block, a response may be expected.

The command type lives in the outer header, not at the end of the payload.

### Worked example (verified)

```text
32 02 00 01 00 04 D1 2D
│  │  └───┘ └───┘ └───┘
│  │  length   data    CRC
│  type 02
start
```

`00 01` → content is `00 04` (two bytes). `D1 2D` is the CRC the original ROM
produces for this frame, transmitted high byte first. Type `02` is a
framing-test vector, not a characterised server command.

### CRC

**CRC-16/ARC** — polynomial `0x8005` (reflected implementation `0xA001`),
init `0x0000`, no final XOR, no reflection of the input. Computed over all
frame bytes from the `32` start marker through the last content byte; the two
CRC bytes themselves are excluded and are sent **high byte then low byte**.
The check value for `123456789` is `BB3D`.

```python
def crc16_arc(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF
```

No byte escaping exists: a `32` inside a payload is just data, once the
length is known. The link also retries on CRC failure.

### Short control frames

These break the normal format — **no length, no CRC**:

| Sequence | Role |
|---|---|
| `32 80` | Acknowledgement / control form (which one applies depends on transaction state and parity — not "success" in every context) |
| `32 A0` | The alternate of the above |
| `32 C0` | Retry / retransmission control |
| `06 30` | Another recognised control sequence |

A frame can be perfectly valid and still fail at the application level (see
status codes in §4).

---

## 3. Command catalogue

Types marked with `→` are request/reply pairs: the central system sends the
first, the phone answers with the second.

| Type | Direction | Purpose | State |
|---|---|---|---|
| `0A` | phone → server | Session opening: 5 bytes of setting 60, state bytes, group code | Traced |
| `02` | both | Terminate (`00 04`), echoed by the phone; final step of a session | Verified |
| `0B` | server → phone | Register a scheduler code and argument (e.g. `01 14 00 3C 03`) — the "completion instruction" before `02` | Verified |
| `0C` | phone → server | Authentication response: `01`, 8-byte DES ciphertext, marker (see §3.1) | Verified |
| `0D` | server → phone | Authentication accepted | Verified |
| `50` | phone → server | Bootstrap/continuation request after the opening frame (`00 04` group 1, `00 03` group 3) | Verified |
| `10` | phone → server | Upload of status-2 identifiers (advances their state to 3) | Traced |
| `12` | phone → server | Upload of status-1 identifiers (resets their state to 0) | Traced |
| `15 → 16` | server → phone | Read one or more settings | Verified |
| `17 → 18` | server → phone | Write one or more settings | Verified |
| `1F → 20` | server → phone | Transfer a block to image staging region A | Verified (isolated 16-byte write) |
| `21 → 22` | server → phone | Alternate staging region/path for image data | Traced |
| `24` | phone → server | Upload of the configuration-change journal | Traced |
| `25 → 26` | server → phone | Transfer a block into another staging region | Traced |
| `29 → 2A` | server → phone | Check a 256-byte page's additive checksum, invoke programming helper | Verified (both outcomes) |
| `2B → 2C` | server → phone | Erase-page path | Traced |
| `2D → 2E` | server → phone | Verify / checksum path | Traced |
| `2F`, `31` | — | Completion or activation-related state handling | Traced, not exercised as a complete update |
| `32` | phone → server | Upload of accounting (call) records | Traced |
| `3D` | server → phone | Download a 32-byte card-range row (card acceptance, scale, alternate price bank) | Verified (lab) |
| `3E`–`6C` | server → phone | Tables, keyed records, auxiliary devices | Names not established — do not guess |

`1F` is also how the number-classification (dial-plan) table is installed; see
[CONFIGURATION.md](CONFIGURATION.md) §6.

### 3.1 Authentication (types `0C`/`0D`)

The phone proves it holds the shared secret with a single-DES encryption:

1. Read setting **298** (8 bytes) and reorder it to `[2,0,1,3,7,6,5,4]`.
2. XOR with `3C AF E2 12 46 B3 59 7D` to get the DES key.
3. Read setting **297** (8 bytes) as the plaintext.
4. Send type `0C`: `01`, the 8 ciphertext bytes, marker `04`.

The ROM's DES routine matches the standard known-answer test (key
`133457799BBCDFF1`, plaintext `0123456789ABCDEF` → `85E813540F0AB405`). With
both inputs zero the response is `8C 45 E7 05 E5 8E 1A 11`. **Verified** in the
emulator, with an independent implementation checking the ciphertext.

What this does *not* show: as described, the response is computed only from
stored values and no server-supplied challenge enters it, which would make it
the same on every call and replayable by anyone who captured one exchange. The
ROM-level evidence is consistent with that, but it hasn't been tested against
a real server that might do something else. Also, the first initialisation call
(group 1) has no authentication stage at all; the server writes 297/298 during
that call.

### 3.2 Session shape

A normal local session (`935#`, group 3) in the order seen on the wire:

```text
phone  0A   opening: terminal ID (setting 60), group
server A0   positive control
phone  50   continuation
server 80   positive control
phone  0C   DES response              (not sent in group 1)
server 0D   accepted
phone  10/12   status lists           (if the route includes them)
phone  32   accounting records        (if 295 = 1)
server 17/15 ...                      settings writes/reads, tables, updates
server 0B   scheduler instruction
phone  80   control
server 02   terminate
phone  02   acknowledge → phone shows OK
```

Short controls alternate `32 A0` / `32 80`; a duplicate frame must keep its
earlier ACK, not advance the sequence. Sending `02` without the preceding `0B`
makes the phone display error 788; ending with `0D` shows 790.

---

## 4. Reading and writing settings

### Read: `15` → `16`

Request payload: `COUNT | (two-byte parameter ID) × COUNT | 03|04`.

```text
Request  15:  01 00 00 04
                  └───┘ │
                  ID 0  final block
                one setting requested
```

Reply payload: `COUNT | ID | STATUS | VALUE LENGTH | VALUE | … | MARKER`.

```text
Response 16:  01 00 00 00 01 02 04
               │  └───┘ │  │  │  │
               │  ID 0  │  │  │  final block
               │        │  │  └── value 2
               │        │  └─── value length 1
               │        └── status 0 = accepted
               one item
```

### Write: `17` → `18`

Request payload: `COUNT | ID | VALUE LENGTH | VALUE | … | MARKER`; the reply
is `COUNT | ID | STATUS | MARKER`.

```text
Request  17:  01 00 00 01 02 04      Response 18:  01 00 00 00 04
                  └───┘ │  │  │                         └ status 00
                  ID 0  │  │  └── final block
                        │  └──── value 2
                        └─────── length 1
```

Writing an out-of-range dialing mode (4) returns `01 00 00 03 04` — status
`03` — and the stored value is left untouched.

Up to **16 settings** may be carried in one ordinary request. Parameter IDs
are **big-endian binary**, not the decimal-digit encoding used by many
values (§5).

### Status codes

| Status | Meaning |
|---|---|
| `00` | Accepted |
| `01` | Invalid, unavailable, or a directly rejected parameter ID (e.g. 160) |
| `02` | Not permitted by the setting's access mask |
| `03` | Invalid or out-of-range value / rejected length |
| `04` | Used in some extended-read situations (e.g. empty data for a given format) — *not* a universal "authentication failed" |

Do not assume every command uses these bytes identically.

### Access masks

Each base setting carries a permission mask with separate bits for remote
reading/writing and the two local technician classes:

| Operation | Mask bit |
|---|---|
| Remote read (`15`) | `02` |
| Remote write (`17`) | `04` |
| Technician class 1 — read | `20` |
| Technician class 1 — write | `10` |
| Technician class 2 — read | `80` |
| Technician class 2 — write | `40` |

`FE` grants all six. `EE` omits bit `10`, so setting 231 can be read but not
written from the class-1 menu. `07` grants remote read/write only — the case
for settings 295 and 296.

These are *descriptor* checks inside the handlers. They do not prove that an
unauthenticated network caller can reach the handlers; the session/login gate
is still unknown.

---

## 5. The BCD trap

Some values travel as **BCD** (two decimal digits per byte) while being held
as plain binary inside the phone.

```text
Wire bytes:       00 64
Visible digits:   0 0 6 4
Decimal value:    64
Stored binary:    40      (0x40 = 64 decimal)
```

Confirmed for **setting 4** (pulse dialing timing, range 50–200): the phone
converts BCD to binary before storing and back again when reading. The same
value in the other direction: stored `C8` (200 decimal) appears on the wire as
`02 00` — the digits `0200`. So setting 4 occupies **one internal byte but two
wire bytes**.

There is no single universal rule for all values; the parameter table tells
the firmware which converter/validator each setting uses. The IDs themselves
are always plain big-endian binary.

---

## 6. Maintenance sessions

The firmware selects a maintenance **route** (mode + group) before it accepts
remote commands. Some routes are technician-triggered, some are scheduled.

### Route menu (traced)

| Keys | Mode / group | Destination | Upload stages |
|---|---|---|---|
| `932#` | `22` / group 8 | setting 261 | `10` and `12` |
| `934#` | `20` / group 7 | setting 261 | `10` |
| `935#` | `14` / group 3 | setting 267 | `10`, `32` if enabled |
| `936#` | `88` / group 9 | setting 261 | `10`, `32` if enabled |
| `939#` | `30` / group 4 | setting 261 | `32` if enabled |

Every traced route also runs the session opening (`0A`), the
authentication-response construction (`0C`) and the shared remote-command
handler. These are **stage selections in ROM**, not verified successful calls.
`930#` in particular is dangerous: it invokes initialisation/clearing
operations before its session route.

### Dialing out

| Setting | Role |
|---|---|
| `260` | Maintenance dialing prefix (up to three BCD bytes, `F` terminates) |
| `261` | Maintenance destination **A** (up to five BCD bytes) |
| `267` | Maintenance destination **B** (up to five BCD bytes), used by the `14`/`15` route |
| `264` | Pause between prefix and destination (0–19; time unit unresolved) |
| `262`, `263` | Purpose **unknown** — do not call them backup numbers |

Scheduled code `10` selects destination 261, scheduled code `14` selects 267.
The dial-request code path is traced; a completed line call has not been
performed.

### Automatic maintenance

| Setting | Meaning |
|---|---|
| `250` | Maintenance time A, `hh mm`, scheduled under code `10` |
| `256` | Maintenance time B, `hh mm`, scheduled under code `14` |

Both are editable from the original service menu. An empty entry is stored as
`FF FF` and clears the scheduler slot. The code path links these events to
session startup. In the emulator a due code `14` completes a full authenticated
session, with retries on failure; the wake-up mechanism is a modelled
hypothesis. See [CALL-HOME.md](CALL-HOME.md).

---

## 7. What the phone uploads

### Call records — type `32`

Up to **eight 26-byte records** per batch. Layout taken from the serializer:

| Offsets | Contents |
|---|---|
| `0–1` | Four-digit field. Earlier called a sequence number; in lab calls it held the card-range ID, so don't treat it as a unique call ID |
| `2–9` | Eight bytes of packed dialled digits (unused nibbles may be `F`) |
| `10–13` | Month, day, hour, minute, each as two decimal digits |
| `14–15` | Four-digit quantity — **not proven** to be duration |
| `16–18` | Six-digit accounting value A |
| `19–21` | Six-digit accounting value B |
| `22–24` | Six-digit accounting value C (from a different caller context) |
| `25` | Two-digit final status/class candidate |

The accounting fields may turn out to be time, charge, balance or totals.
Which is which is **not** established — the byte boundaries are. Lab calls
suggest call length, scaled debit, scaled balance and card serial; see
[ACCOUNTING.md](ACCOUNTING.md) for the field sources, storage, batching and
fault behaviour, and the per-mode upload stages.

### Status identifier lists — types `10` and `12`

Count plus two-byte identifiers, not the values behind them. The firmware
scans 13 tracked status entries and picks the ones in a given internal state:
type `10` takes status-2 entries and advances them to 3; type `12` takes
status-1 entries and resets them to 0.

### Change journal — type `24`

Raw journal bytes from a dedicated nonvolatile region. A seeded experiment
reproduced a packet using bytes appended by the settings-change system.
Acknowledgement and clearing behaviour is not fully verified.

---

## 8. Firmware updates

Full detail (image halves, checksums, states 0–5, recovery) is in
[FIRMWARE-UPDATE.md](FIRMWARE-UPDATE.md). Summary:

The update path is a family of commands, not a single "flash" command:

| Request → reply | Effect |
|---|---|
| `1F → 20` | Block to staging region A |
| `21 → 22` | Block to the alternate staging path |
| `25 → 26` | Block to another staging region |
| `29 → 2A` | Verify a 256-byte page's **additive 16-bit checksum**, then invoke the programming helper |
| `2B → 2C` | Erase page |
| `2D → 2E` | Verify / checksum page |
| `2F`, `31` | Completion / activation state handling |

The **page checksum is not the frame CRC**. The CRC protects a packet in
transit; the additive checksum covers a 256-byte image page. A successful
handler response does not mean a complete physical flash update — or a
reboot — would work. This sequence is not a tested end-to-end flashing recipe.

---

## 9. Settings with an identified purpose

The firmware describes **700 slots** (IDs 0–699: 300 base + 400 extended).
Only 245 base and 170 extended descriptors have non-zero storage size, and
most real-world meanings remain unknown. The ones we can name:

| ID | Meaning | Notes | Confidence |
|---:|---|---|---|
| 0 | Dialing method | `0`/`1` = tone (DTMF), `2`/`3` = pulse | Verified |
| 1 | Tone timing A | 8–99, unit unproven | Traced |
| 2 | Tone timing B | 8–99, unit unproven | Traced |
| 3 | Pulse timing | 11–99, split into quotient/remainder after ÷10 | Traced |
| 4 | Pulse dialing timing | 50–200, BCD on the wire | Verified |
| 60 | Session/terminal identifier | Five bytes copied into `0A` | Traced |
| 62 | Date and time | `YY MM DD hh mm`, five BCD bytes, no century | Verified |
| 114 / 115 | Answer-supervision mode (categories 1–9 / category 0), 0–4 | One-byte value; see `SETTINGS.md` §4.3 | Verified |
| 130–159 | Per-category initial charge, repeat charge, pulse allowance | `SETTINGS.md` §4.3 | Verified |
| 200–229 | Per-category pre-answer timer, first and repeat period length | `SETTINGS.md` §4.3 | Verified |
| 231 | Global metering-mode selector, 0–3 | Class-2 writable, class-1 not. Not the display language. | Traced |
| 232, 233, 235, 240, 241, 246, 247 | Time-window price adjustment and timing-branch masks | `SETTINGS.md` §4.3 | Verified |
| 283 | Mode-4 confirmation key (1 `#`, 2 B, 3 C) | | Verified |
| 250 | Maintenance time A | `hh mm`, schedule code `10` | Verified |
| 256 | Maintenance time B | `hh mm`, schedule code `14` | Verified |
| 260 | Dialing prefix | ≤ 3 BCD bytes | Traced |
| 261 | Destination A | ≤ 5 BCD bytes | Traced |
| 264 | Pause after prefix | 0–19, unit unresolved | Traced |
| 267 | Destination B | ≤ 5 BCD bytes, route `14`/`15` | Traced |
| 295 | Allow accounting upload stage | `0` skip / `1` allow; does not prove charging stops | Verified |
| 296 | Allow change-journal upload | `0` skip / `1` allow; local route suppresses it | Verified |
| 297 | Authentication plaintext | Eight opaque bytes | Verified |
| 298 | Authentication key source | Eight opaque bytes, reordered/XORed into the DES key | Verified |

Two structural quirks:

- **IDs 160–199 are rejected directly** by the ordinary read/write handler,
  while **850–889 are aliases** into that protected block, mirroring the
  layout of IDs 120–159 (ten six-digit fields, twenty four-digit fields, ten
  two-digit fields). A tariff-counter role is plausible but speculative.
- **Extended IDs (300–699)** are profile-dependent: 400 slots, 170 with
  stored data, all readable when seeded non-zero across five profiles (850
  reads) — and **all 170 rejected ordinary remote writes**. Do not treat
  them like editable settings.

The full catalog, and the tariff parameter families (IDs 114–283), are in
[SETTINGS.md](SETTINGS.md).

---

## 10. Technician keypad access

On the emulated hardware, holding a candidate service key during reset leads
to a PIN screen (the ROM also carries the Romanian prompt
`TIPARESTE CODUL` / "print the code"). The physical switch identity is not
established.

| Input | Effect |
|---|---|
| `555657#` | Enter technician class 1 |
| `336633#` | Enter technician class 2 |
| `000#` | Open setting 0 (dialing mode) |
| `004#` in `TESTARE` | Read setting 4 |
| `0064#` | Store decimal 64 in the selected setting |
| `004#` | Read it back |
| `*` | Cancel viewing |
| `062#` | Open the clock setting |
| `250#`, `256#` | Edit the maintenance times |
| `900#` | Keypad diagnostics |
| `901#` | LCD diagnostics |
| `920#` | Show the DTMF/pulse selection prompt |

The keypad matrix's `A` contact cycles Romanian → English → French → German
in the PIN-screen path. That is **not** proven to be setting 231.

> **Do not try `900#`–`999#` on real equipment.** Some codes point at
> initialisation, erasing, clearing and update operations. The tests used
> synthetic EEPROM copies.

---

## 11. How this was established

- **Isolated handler calls.** The original ROM's serial receive/transmit
  routines are invoked directly, with select application requests and mocked
  dependencies. This is where the settings read/write results, the status
  codes and the CRC behaviour come from.
- **Boot-mode emulation.** The decoded ROM runs from reset on a provisional
  Python HC11 model: startup, keypad, PIN menu and local settings editing are
  reachable; a fully authenticated network session is not.
- **Lab server.** A local dashboard (default port `8765`) and a raw TCP peer
  (default port `2323`) stand in for the modem. TCP is a *test replacement*
  for the line transport — the phone itself knows nothing about IP addresses
  or ports.

Corroborating evidence in the ROM image itself includes the `TESTARE` menu
name, the `1/2-DTMF/Pulse` prompt, the date/time format string
`%02d/%02d/%02d %02d:%02d`, the five-byte hex format `%02X%02X%02X%02X%02X`,
and the four-language message set (Romanian, English, French, German).

The lab configuration is **synthetic** — produced by running the ROM in the
emulator — and must not be treated as a dump of a real phone.

---

## 12. Open questions

- Physical capture of phone-to-central-computer traffic; identification of the
  real serial peer and modem path.
- Confirmed line modulation, baud and framing directions, dialling handshake,
  and the actual server endpoint.
- The complete authentication exchange, login rules and failure handling.
- A completed session from boot, with successful record transfer and remote
  commands.
- The meaning of most of the 700 parameter slots — especially tariff, rating
  and credit fields.
- Physical units for the accounting quantities and the timing controls.
- A verified page programming / activation / reboot cycle on real hardware.
- Physical input and switch mapping, and normal card and call behaviour.

---

## 13. Source map

This overview consolidates the research notes behind it: `SERVER-COMMS.md`,
`PROTOCOL-MEANINGS.md`, `COMMUNICATIONS.md`, `MAINTENANCE-WORKFLOWS.md`,
`PARAMETER-CATALOG.md`, `PARAMETER-STRUCTURE.md`, `ACCESS-CONTROL.md`,
`WRITE-GUIDE.md`, `CALL-RECORD.md`, `USER-GUIDE.md`, `FEATURE-MAP.md`,
`BOOT-INPUTS.md`, `V23.md`, `EMULATOR.md` and `LIVE-LAB.md`. Where later
tracing corrected an earlier hypothesis, this document follows the correction.

Those notes are still working documents outside this repository; the parts
worth keeping are being distilled into this file, [SETTINGS.md](SETTINGS.md),
[PHONE.md](PHONE.md) and [CONFIGURATION.md](CONFIGURATION.md).
