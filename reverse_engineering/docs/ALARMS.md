# Faults and Alarm Reporting

How the firmware counts faults, latches them, reports them to the server, and
clears them. This covers **software fault reporting**. It is not about the RTC
wake alarm that starts scheduled calls (see [CONFIGURATION.md](CONFIGURATION.md)
§3 for the schedule).

Confidence labels used below:

- **Static**: read from the disassembly, not executed as a live alarm.
- **Emulated**: reproduced by the original ROM in the emulator, with the
  peripherals (card reader, controller, server, external contacts) supplied by
  the lab model.
- **Hypothesis**: a reading that fits the evidence but isn't established.

No physical fault has been observed on a real phone. Where the emulator needed an
input contact or a controller status bit, the physical meaning of that signal is
unknown, and the doc says so rather than naming it ("door open", "line cut" and
similar names are **not** supported by anything in the ROM).

---

## 1. The fault table

Thirteen entries live in the common ROM at `$4442`–`$4475`, four bytes each:
a big-endian fault number, a priority byte, and an optional threshold parameter
ID. The fault numbers are the same numbers the UI shows as `EROARE nnn`
([PHONE.md](PHONE.md) §8), and also ordinary extended parameter IDs that hold a
two-byte **total occurrence counter** for that fault.

| Index | Fault | Priority | Threshold parameter | Total counter (logical) |
|---:|---:|---:|---:|---|
| 0 | 522 | 1 | 81 | `$192A` |
| 1 | 543 | 1 | 82 | `$1930` |
| 2 | 544 | 1 | 83 | `$1932` |
| 3 | 550 | 0 | 95 | `$1934` |
| 4 | 555 | 0 | none | `$1936` |
| 5 | 556 | 0 | none | `$1938` |
| 6 | 575 | 0 | none | `$1948` |
| 7 | 576 | 2 | none | `$194A` |
| 8 | 578 | 0 | none | `$194E` |
| 9 | 579 | 0 | none | `$1950` |
| 10 | 580 | 2 | none | `$1952` |
| 11 | 581 | 0 | 96 | `$1954` |
| 12 | 582 | 0 | none | `$1956` |

Priority 0 is a real table value and not a sign that a condition is harmless.
Not every displayed `EROARE 5xx` is in this table (577 isn't, for instance), and
those errors still increment their total if they have a counter parameter.

Other persistent state:

| What | Address | Size |
|---|---|---|
| Per-fault occurrence counters (towards the threshold) | `$0C40`–`$0C4C` | 13 × 1 |
| Per-fault reporting state | `$0C50`–`$0C5C` | 13 × 1 |
| Highest active priority | `$0DF0` | 1 |
| "Alarm pending" indicator | `$2065` | 1 |

---

## 2. Life of a fault

### 2.1 Reporting states

Each fault has one state byte:

| State | Meaning |
|---:|---|
| 0 | Idle |
| 1 | Cleared locally, **clear report owed** to the server |
| 2 | Latched, **report owed** |
| 3 | Reported (the report was built and sent; see §4 on what this does not prove) |

### 2.2 Producer (Static, confirmed in Emulated runs)

Common routine `$54A3` raises a displayed error 500–599:

1. It increments the fault's **total counter** (`$52FC`). This always happens,
   even with threshold 0.
2. If the fault has a state entry, selector-3 routine `$A7D4` runs:
   - **Threshold parameter is zero:** nothing further. The total counts, no
     alarm is latched.
   - **Threshold parameter is `n` > 0:** the occurrence counter at `$0C40+i`
     increments. When it reaches `n` it is reset to 0 and the fault may latch.
   - **No threshold parameter:** the fault latches immediately.
3. Latching sets state 0/1 → **2**, sets the pending indicator, and raises the
   maximum priority at `$0DF0` if this fault's priority is higher.

### 2.3 Clear (Static, confirmed in Emulated runs)

Selector-3 routine `$A9D0`, gated by a runtime flag at `$0795`:

- Resets the occurrence counter.
- Leaves states 0 and 1 alone.
- State **2 → 0** (it was never reported, so nothing to tell the server), or
- State **3 → 1** and, for a nonzero caller argument, schedules **call code 22**
  with delay argument 2.

Routine `$A8EC` then rescans the states: with no state-2 fault left it cancels
scheduler codes 20/21 and clears the pending indicator, and it recomputes the
maximum priority from states above 1.

Because the pending indicator also falls back to 0 on its own while a fault is
still latched, **the pending indicator alone says nothing about whether a fault is
active or delivered.**

### 2.4 Overall lifecycle (Emulated, fault 580)

```text
0 ─ fault raised ─▶ 2 ─ type 10 report built ─▶ 3 ─ condition clears ─▶ 1 ─ type 12 built ─▶ 0
        (latched)        (marked before sending)    (cold boot, healthy       (marked before sending)
                                                     input)
```

Technician reset from the `951#` browser jumps **3 → 0** directly and tells the
server nothing (§5).

Both state changes on the way out (`2→3` in `$A475`, `1→0` in `$A521`) are made
**before** the frame is transmitted and are not rolled back on failure (§4).

---

## 3. Reporting to the server

A latched fault is reported inside a maintenance call
([SERVER.md](SERVER.md), [ACCOUNTING.md](ACCOUNTING.md) §4). Two message types
carry the lists:

| Type | Built by | Selects | Marks |
|---:|---|---|---|
| `10` | `$A475` | faults in state 2 | 2 → 3 |
| `12` | `$A521` | faults in state 1 | 1 → 0 |

Payload: `count`, then `count` big-endian fault numbers, then a marker byte. IDs
only, no counter values. Examples from the emulator:

| Payload | Meaning |
|---|---|
| `00 03` | Empty type 10 list (marker 03) |
| `01 02 42 03` | One fault: 0x0242 = 578 |
| `01 02 44 04` | One fault: 0x0244 = 580 (marker 04 in type 10 from a mode-20 call, and in type 12) |
| `01 02 0A 04` | 522 |
| `01 02 1F 04` | 543 |
| `01 02 20 04` | 544 |

The marker varies with the call (03 in scheduled mode 14, 04 in the alarm and
recovery modes); its exact meaning isn't established. A final-marker-04 frame is
answered by server **application commands**, not by a separate `80/A0` report
acknowledgement, so the phone has no explicit "report accepted" signal here.

### 3.1 Which calls carry reports

| Call | Mode / group | Reports | Accounting upload |
|---|---|---|---|
| Scheduled call, destination A or B | 14/15 (group 3), 10/11 (group 2) | type 10 | yes (type 32), if 295 = 1 |
| Alarm-triggered call | **20** (group 7) | type 10 | **no** |
| Recovery call (code 22) | **22** (group 8) | type 10 then type 12 | **no** |
| Retry call (code 23) | 23 | type 10 then type 12 | **no** |
| `934#` / `932#` | 20 / 22 | as above | no |

Consequences, all Emulated:

- An alarm call does not upload the customer records pending behind it; they
  stay queued for the next accounting call, byte for byte.
- A scheduled call that *discovers* a fault reports it in the same session. That
  is not an alarm-initiated call.
- Alarm calls dial prefix `9` and destination **261** (`0212345679` in the lab
  configuration), not the scheduled destination 267. See
  [SETTINGS.md](SETTINGS.md) for 260/261/267.

### 3.2 Retry timing

If the call fails (§4), the firmware schedules a retry. The delay is read from
settings:

| Setting | Used for | Lab value |
|---|---|---:|
| 254 | Retry delay for non-group-3 modes (odd retry code: 23 after 22) | 5 |
| 255 | Held next to 254 in RAM (`$076D`); role not traced | 3 |
| 258 | Delay for group 3 (modes 14/15), two-byte | 2 |

So the five-minute retry seen for code 23 is a configuration value, not a
constant. The complete back-off and the give-up point were not exercised.

---

## 4. Failure behaviour (Emulated)

What happens when the server rejects a report (`C0` control) three times:

| Case | Outcome |
|---|---|
| Type 10 rejected | The call ends with cleanup reason 7. State stays **3** and the frame is **not** resent on the next automatic call; that call sends an empty list `00 03`, while customer accounting uploads normally. |
| Type 12 rejected | State already 0. The retry call sends empty lists `00 03` and `00 04`; the rejected clear is **not** resent. |

This follows from the state byte being changed before transmission. The server
did receive the first frame's bytes before rejecting it, so "never seen" is not
the right reading, but nothing in the phone distinguishes a delivered report from
a rejected one. **State 3, state 0 and a later successful empty list prove neither
acceptance nor durable storage on the server side.** Only one fault at a time
(and one failure mode, `C0`) was tested; lost replies and other combinations
weren't.

---

## 5. Technician access: the `951#` browser

Class-1 (`555657#`) and class-2 (`336633#`) PINs both open the status browser at
`951#`. `#` steps through the 13 entries (starting at 522), `9` resets the shown
entry, `*` leaves. The display shows `fault state-bytes`, for example `578 1 3`.

Emulated paired test, starting from a latched fault 578 (state 3):

| PIN | Browser | Reset (`9`) |
|---|---|---|
| Class 1 `555657` | shows the entry | **no effect**; state 3 and pending stay |
| Class 2 `336633` | shows the entry | state **3 → 0**, pending indicator → 0 |

The reset leaves every total counter, the accounting records and headers alone.
It does not produce state 1, does not dial and sends no type 12. A technician
reset therefore removes the alarm **without telling the server**. The PIN values
are the ones from the test EEPROM and aren't claimed as universal.

---

## 6. What produces each fault

Only six of the thirteen are reproduced. Everything here is ROM-derived plus
emulator inputs; none of it identifies a physical condition.

### 6.1 Threshold behaviour: fault 522 (Emulated)

522 was reproduced with the card peripheral returning an error (type `85`, code
`04`) to the **credit-write request** at the end of a paid call. The ROM then
raises 522 through the normal error path.

| Threshold (81) | Attempt | Total | Occurrence counter | State | Priority |
|---:|---:|---:|---:|---:|---:|
| 0 | 1 | 1 | 0 | 0 | 0 |
| 0 | 2 | 2 | 0 | 0 | 0 |
| 2 | 1 | 1 | **1** | 0 | 0 |
| 2 | 2 | 2 | **0** | **2** | **1** |

- A zero threshold still counts the total but never latches.
- With threshold 2, the second occurrence latches, and the phone then dials
  `9` + destination 261, authenticates, and sends type 10 `01 02 0A 04`.
- The write never took effect: the card credit stays where it was. No customer
  record is created in this path.
- **The threshold is not "consecutive failures".** Bad write → good call → bad
  write still latches on the second bad write; the healthy call in between did
  not clear the first occurrence.

The threshold is set with the ordinary local editor, for example
`336633#` `081#` `02#` `081#` `*` for threshold 2. It's an ordinary base
parameter.

Reader errors during the *credit read* (type `85`, codes `05` and `0B`) show up
as customer errors **200/201**, **not** as fault 522 or 555, whatever the
threshold. Do not infer "reader error code X creates fault Y".

### 6.2 Controller status word: 578 and 579 (Emulated)

During scheduled maintenance the phone sends controller command `12 81 01 94` and
reads a 16-byte status response (`90 90 <b0> …` plus checksum). The first status
byte is tested in routine `$9347`:

| Bit | Raises |
|---|---|
| `40` | **578** |
| else `20` | **579** |
| else `04` | 577 (not in the pending list) |

Zero-status control: no fault, an empty type 10, accounting uploads as usual. With
bit 40 or bit 20 set once, the fault latches (0 → 2 → 3), the session reports it
(`01 02 42 03` / `01 02 43 03`), and uploads the pending customer record in the
same call. Two later healthy status reads did not clear either fault. The
physical meaning of the bits is unknown; the priority order is ROM behaviour only.

### 6.3 Contact input: 580 (Emulated)

Message class `7700` (an external contact going low) reaches handler `$C880`. If
the contact stays low through a short wait it posts UI message `3C12`, which the UI
maps to fault **580**; the matching `9700` (contact high) reaches `$C7DD` and the
clear routine, the candidate for the 3 → 1 path.

- The contact is scanner input 23, reached in the lab model from the first SPI
  byte's bit 7. Its physical wire is unidentified.
- A contact post alone isn't a fault. In the lab, 580 only latched when a second
  input (input 11, the handset candidate) was in its low state; with it high, the
  message was posted but no fault was raised.
- Once latched, raising the contact did not clear it during the same run: the
  input stays masked after the low event. A fresh boot with a healthy contact does
  the clearing (see below). Whether real hardware clears without a restart isn't
  known.

**Fault-triggered call** (Emulated): with 580 latched, the main path requests
mode 20, dials `9` + 261, and sends type 10 `01 02 44 04`; the server answers
with normal commands. The customer record is untouched.

**Recovery** (Emulated, after an explicit cold reset with the contact healthy): on
boot the scanner registration posts `9700`, `$A9D0` clears 580 (state 3 → 1) and
schedules code 22. At the next call time the phone sends an empty type 10, then
type 12 `01 02 44 04`, marking 1 → 0. Final: all states 0, total 580 stays at 1.
The cold reset is a lab intervention; uninterrupted recovery without a restart was
not shown.

### 6.4 Missing supervision: 543 (Emulated)

The pre-answer timer armed for a paid call (setting 200 + category) fires and, if
supervision hasn't been seen and the mode doesn't start charging on the timer
(modes 2 and 3 do), the ROM posts `3C18`, which the UI shows as **543**.

With threshold 82 = 1, one run (mode 1, category 1) latched 543, dialled the alarm
call, and sent `01 02 1F 04`; the same configuration with the answer transition
present produced a normal debited call and no alarm. A second route to 543 exists
in the ROM (incoming message `A500`), but nothing was found that produces it.
See [TARIFFS.md](TARIFFS.md) for the supervision modes.

### 6.5 Adaptive metering: 544 (Emulated)

Setting 235 (category mask) and 231 (metering mode) select a mode in which the ROM
measures the interval between metering pulses and compares it with a window
derived from 117 (tolerance). Two independent routes to **544** were reproduced
with threshold 83 = 1:

- **Short interval:** a pulse arriving much earlier than the learned interval
  (75 ticks measured against a 200–300 window) posts `3C15` → 544.
- **Pulses stop:** after the pulse stream ends, the timer branch posts `3C03` and
  raises 544 as well.

So an out-of-window interval alone does not always raise 544 (it depends on
further gates), and a "regular" pulse stream isn't alarm-free once it stops.
Both alarmed calls end with a saved customer record (here debit 4, balance 96)
that stays pending. This is not a universal meaning of 544 or a physical
meter-fault diagnosis.

### 6.6 Fault 582: static only

Routine `$D45E`–`$D59F` contains both a producer and a clear path for 582. It
requires a hardware register bit and a nonzero input-12 test, then adds ten RAM
words (at `$068F`) to a ten-word profile block (located via extended parameter 690),
and checks them against settings **97** (per-bucket floor) and **98** (total):

- Total **> 98** and some bucket **< 97**: raise 582.
- Total **> 98** and none below 97: clear 582.
- Total ≤ 98: nothing.

The meaning of the buckets isn't known (the sample EEPROM holds 97 = 10, 98 = 400),
so 582 is not reproduced and shouldn't be given a name.

### 6.7 Remaining entries

522, 543, 544, 578, 579 and 580 are reproduced. **550, 555, 556, 575, 576 and 581**
have table entries (550 and 581 with thresholds 95 and 96) but no producer was
traced and no trigger reproduced. A single-contact sweep of 12 external input
changes (SPI bits, `$4080` bits 5 and 7) with every threshold at 0 raised nothing.
That doesn't rule out thresholded, combined or timed conditions.

---

## 7. Practical notes

- **Read-only inspection.** The `951#` browser shows state bytes safely for both
  PINs. Pressing `9` is class-2 only and clears the shown entry; treat it as
  destructive ([CONFIGURATION.md](CONFIGURATION.md) §5).
- **EEPROM dump.** Fault state bytes are at `$0C50`–`$0C5C`, totals at the
  addresses in §1. A phone that was used in the field may hold real nonzero
  totals, which would show which of the 13 faults actually occur. This is cheap
  and valuable ([HARDWARE-CHECKLIST.md](HARDWARE-CHECKLIST.md) §4).
- **Thresholds.** 81, 82, 83, 95, 96 are base parameters set from the service menu
  (class 1 or 2 per their access masks); zero disables latching for that fault but
  not its total.
- **Alarm routes.** `934#` and `932#` run the alarm-call stage sequences without
  an actual fault ([CONFIGURATION.md](CONFIGURATION.md) §4).

---

## 8. Not established

- The physical meaning of every fault, status bit and contact. The names in other
  documents ("handset", "service switch") are labelled candidates.
- Whether the server ever stores or acts on type 10/12 lists, and any retransmit
  or reconciliation on the server side.
- Fault delivery under lost replies and other failures (only repeated `C0` was
  tried); how the complete retry back-off ends.
- Recovery without a restart, and recovery of any fault other than 580.
- Triggers for 550, 555, 556, 575, 576, 581, 582, and the second route to 543.
- The marker byte in type 10/12 payloads.
- How faults are raised on real hardware during a customer call (the lab used
  scripted peripherals throughout).
