# Calling Home

How the phone starts a call to the central system, what has to be true on the
board for that to work, how a scheduled call comes about, and what happens when
the call goes wrong. The message formats are in [SERVER.md](SERVER.md); this doc
is about the **session as a whole**: start-up, wake-up, timeouts and retries.

Everything here was observed in an emulator running the original ROM against a
simulated board: a serial modem and server, a clock chip, a card/controller
peripheral and external contacts. The peers are lab models, not captures from a
real phone, line or server. Times are "modelled seconds" (the 1 MHz E-clock and
the 8 ms tick are assumptions, see [PHONE.md](PHONE.md) §1). Confidence labels
are the same as in [ALARMS.md](ALARMS.md): **Static**, **Emulated**,
**Hypothesis**.

Related docs: the update transfer is in [FIRMWARE-UPDATE.md](FIRMWARE-UPDATE.md),
what gets uploaded in [ACCOUNTING.md](ACCOUNTING.md) and [ALARMS.md](ALARMS.md),
how a technician starts a call in [CONFIGURATION.md](CONFIGURATION.md) §4.

---

## 1. Ways a call starts

| Trigger | Route | Notes |
|---|---|---|
| Technician keys `935#` etc. | mode 14, 20, 22, 30, 88 | [CONFIGURATION.md](CONFIGURATION.md) §4. Emulated end to end for `935#` (mode 14) |
| Scheduled time reached | code `10` (destination A, 261) or `14` (destination B, 267) | Settings 250 / 256 |
| Retry after a failed call | code 15 (after 14), 23 (after 22) | §6 |
| Fault latched | mode 20 | [ALARMS.md](ALARMS.md) §3 |
| Fault recovery | code 22, then 23 | [ALARMS.md](ALARMS.md) §3 |
| Blank EEPROM | mode 60, flag `$0C75 = 1` | First-contact session; `930#` is the same route. No authentication stage. |

Whichever way it starts, the phone dials **prefix (260) + destination (261 or
267)** with a pause between them (264), waits for carrier, and runs the session.

---

## 2. One session, start to finish (Emulated)

1. **Dial.** The ROM's own dialer sends prefix then destination (for example `9`,
   then the number).
2. **Carrier qualification.** Routine `$8E2F` waits for a low interval on the
   receive line, then `$909D` for a stable high interval, before enabling the
   serial receiver. The simulated modem gave 1.1 s low, then high.
3. **Start token.** With the receiver enabled, the peer sends the control `06 30`.
   The ROM takes it as an internal "start" message and enters the opening stage.
4. **Opening** (`0A`, then `50`), **authentication response** (`0C`, DES; see
   [SERVER.md](SERVER.md) §3.1), and the **upload stages** of the route (`10`,
   `12`, `32`, `24`).
5. **Server commands.** After the peer accepts `0C` with `0D`, it sends
   application commands. The tested session wrote and read back one setting
   (`17`→`18`, `15`→`16`) and registered a scheduler code with `0B`.
6. **Termination.** The peer sends `02 00 04`; the phone answers with the same.
   Cleanup runs with reason 5 / phase 5, and the technician display shows `OK`.
   Automatic sessions need not show `OK`.

Order matters:

- Terminating without the preceding completion command (`0B`) gives
  `EROARE 788`; sending `0D` as the final completion gives phase 4 and
  `EROARE 790`.
- A duplicate frame must be answered with the same acknowledgement as before,
  without advancing the sequence.
- Continuation acknowledgements begin with `32 A0`, then `32 80`.
- A `C0` control is not a positive acknowledgement for any step.

Group 1 (mode 60, initialisation) has no authentication stage. The other groups
all do.

---

## 3. What the board needs to look right

The ROM refuses to proceed unless several peripherals answer. Each was a blocker
in the emulator until modelled:

| Need | What the ROM does without it |
|---|---|
| **Clock chip** answering on PD3/PD4 (address `A0/A1`) with a plausible time | Reads all-zero time and date, and the main task can go to `STOP` while a call is pending |
| **Controller bus** on PA3/PA4 (address `64/65`) answering initialisation `81 80 01`, `88` record queries and `90` status | Controller-driven paths fail; nothing dials |
| **Control bus** on PD0/PD1 (address `48`), shared with the serial pins | Must acknowledge control writes, even when the modem's receive line idles high |
| **Reply-pending line** (`$4080` bit `40`, active low) | The receive routine waits on this input. In the emulator it is low while a controller reply is pending |
| **Previously commissioned EEPROM** (`$0C75 = 0`) | A fresh image requests a mode-60 initialisation that collides with other tasks |

`$4080` is both the bank latch and an input port. Writing it as a plain register
corrupts ROM and EEPROM bank selection. The modelled board merges the input bits
`E0` with the latched output bits `1F`.

The physical identity of each device is unknown. "Controller" and "control bus"
name interfaces, not identified chips. The clock matches a PCF8583-style register
layout.

---

## 4. Scheduled calls

### 4.1 Provisioning the schedule

Two times are stored in settings, `hh mm`:

| Setting | Scheduler code | Destination |
|---|---|---|
| 250 | `10` | 261 |
| 256 | `14` | 267 |

An empty entry (`250##` or `256##`) stores `FF FF` and disables that slot. The
calendar must be set (setting 62, `YYMMDDhhmm`) before a future time means
anything. Example from the lab, typed as one service sequence:

```text
555657# 062# 2611141000# 256# 1002# 
```

Sets the date to 2026-11-14 10:00 and the time-B schedule to 10:02.

Things that bite:

- **Same-time registration.** Registering 00:02 while the clock already reads
  00:02 produced an internal scheduler word of 1439 instead of 2. The scheduler
  words are relative, not plain `hh mm`.
- **A remote write can overwrite the schedule.** Setting 256 written remotely and
  read back correctly was later replaced by the standard peer's final `0B`
  instruction (`01 14 00 3C 03`: register code 14 with argument 60), which put a
  relative 60-minute entry in its place. A matching read-back doesn't prove the
  final scheduler table.

### 4.2 Waking up (Emulated, wiring is Hypothesis)

On a normal boot with the schedule set, the ROM shows the time, programs the
clock chip's next alarm (control write `00 04`; alarm write `08 90 00 00 03 00`
then read-back) and executes `STOP`.

Two ways the alarm could bring the phone back were tried:

| Hypothesis | Result |
|---|---|
| Clock interrupt output wired to the CPU's **XIRQ** | **Rejected.** The CPU wakes and vectors through `FFF4`, then lands in the ROM's *unhandled interrupt* path, because the XIRQ handler slot is unregistered. No dialing, no session. |
| Alarm causes a **power cycle** (cold reset), and alarm status is also readable as **scanner input 8** (active low, second SPI byte bit 0) | **Works.** Each alarm starts the original reset code; the ROM-written EEPROM and the clock survive. |

The second arrangement is an explicit hypothesis. It is not known how a real board
wakes. What the runs show is that rebooting at alarm times is not enough on its
own: with input 8 high, a correctly provisioned schedule never calls. The ROM
checks its own due table when input 8 reports the alarm.

Software gate (Static, confirmed in Emulated runs): the scanner's `6800` message
reaches `$B0A2`, which sets a "check schedule" flag; `$B181` then calls the
scheduler `$ECCA`; a non-zero result goes to `$B1D5` and on to the maintenance
dispatcher `$B728`.

### 4.3 The scheduled-call chain

From a 10:00 boot with 256 = 10:02:

| Clock | What the ROM does |
|---|---|
| 10:00 | Normal idle, programs a 10:01 alarm, `STOP` |
| 10:01 (alarm, input 8 low) | Scheduler returns 0, no call, programs 10:02, `STOP` |
| 10:02 (alarm, input 8 low) | Scheduler returns `14` hex. Dialer sends prefix and the 267 number |
| Same boot | Opening, DES, uploads, settings write/read, termination, cleanup reason 5 / phase 5 |
| about 10:02:40 | Returns to `STOP` |

No keys are used. Disabling 256 still lets the check run but it returns nothing
due, and no call happens.

Limits: this is a cold-reset model and not an uninterrupted `STOP` resume; the
alarm physically waking the CPU has not been shown; a real phone's behaviour
across power-down isn't known.

---

## 5. When the call fails

Cleanup reason and phase identify how a session ended. All Emulated.

| Reason / phase | Cause | Example |
|---|---|---|
| 5 / 5 | Success | Normal termination |
| 7 / 4 | Server answered `C0` three times | Accounting upload rejected |
| 0B / 3 | Receive timeout, sixth attempt | Server never completes authentication |
| 2 / 2 | Carrier qualification failed (`$8E2F` returns 0) | Receive line held high |
| 8 | Startup returned `FFFF` | Fatal startup result |

### 5.1 Server answers `C0`

On a rejected accounting upload (control `C0`, repeated during control
synchronisation three times in all): one data batch goes out, then cleanup 7/4.
The pending record stays pending, and the phone schedules a **retry as code 15**
with a delay of two minutes (setting 258; see [ALARMS.md](ALARMS.md) §3.2 for the
equivalent retry settings in other modes). At 10:03 the scheduler returns 0, so
no premature redial. At 10:04 it returns `15`, the phone redials and
authenticates, and the same 26-byte record uploads and commits.

The record's bytes and the batch marker (03 in automatic sessions) come from the
ROM, not from the peer. One failed attempt isn't three calls.

### 5.2 Authentication reply never arrives

The receive routine `$9119` arms a timer (output compare 1) for `TCNT + $7A12`
(about 0.5 s at the assumed clock) and waits. On timeout the handler marks an
error and the routine re-arms, up to **220 times** per inner loop (`DC` hex).
After the inner loop it returns `FFFD`, and `$9F04` counts an outer attempt. Five
are allowed; on the **sixth** the ROM runs cleanup with reason `0B`.

Expected silence budget: 5 × 220 × 0.5 s, about **550 s**. Observed: 1100
timeouts, failure 553 s after the withheld reply (578 s into the boot). The
pending record is untouched (the accounting stage is never reached), and the
retry is the usual code 15 two minutes later, at 10:13 in the run, after an
unmodified 10:12 check that returned 0. These are modelled seconds. The real
timeout depends on the real clock rate.

A slow server is tolerated: a valid completion reply after a nominal 30 s delay
(59 timeouts in between) finishes the **same** call with no redial.

### 5.3 Start-up failures

| Fault | Behaviour |
|---|---|
| Receive line held high (no carrier qualification) | `$8E2F` returns 0 after about 31.7 s; cleanup 2/2; nothing transmitted; retry as code 15 succeeds |
| Qualification fine, `06 30` start token never sent | The ROM keeps waiting: 100 timeouts in 72 s, no cleanup, no transmit. A bounded wait, not shown to end. |

The stored byte `$2066` keeps the last failure reason (7, 0B) after a later
success. It's a history, not the current session's state.

None of this identifies a real carrier-detect wire or reproduces a real
disconnection. Only what the lab peripheral supplied was tried.

---

## 6. Retry and timing summary

| Item | Value | Source |
|---|---|---|
| Retry code after a failed code-14 call | 15 | scheduler table |
| Retry delay, group 3 (modes 14/15) | setting 258 (2 min in the lab) | [SETTINGS.md](SETTINGS.md) |
| Retry delay, other modes | setting 254 (5 min in the lab) | [ALARMS.md](ALARMS.md) §3.2 |
| Receive inner loop | 220 timeouts × about 0.5 s | `$91F2` |
| Receive outer attempts | 5, cleanup on the 6th | `$9F65` |
| Carrier wait before cleanup 2/2 | about 31.7 s in the run | `$8E2F` |

Not tested: other failure combinations, how many retries are made before giving
up, behaviour on a real line.

---

## 7. What isn't established

- Everything about the real line: modem audio (V.23), real carrier timing, whether
  `06 30` appears the way the simulated modem produced it.
- How the alarm wakes the board: XIRQ failed in the model; reset plus input 8 is a
  working hypothesis only.
- Whether the real scheduler and clock survive a power loss in the way the model
  assumed.
- The identity and wiring of the controller, control bus, reply-pending line and
  clock interrupt.
- Server-side behaviour: all peers were lab scripts.
