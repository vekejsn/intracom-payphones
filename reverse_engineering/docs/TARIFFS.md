# R4R1C Payphone — Tariffs and Charging

How the phone decides what a call costs, step by step, and where each number
is stored. This pulls together material that is also in
[SETTINGS.md](SETTINGS.md) §4.3, [PHONE.md](PHONE.md) §6 and
[CONFIGURATION.md](CONFIGURATION.md) §6, with a worked example and a table to
fill in from a real EEPROM dump.

**No real rates are known.** The firmware image holds the machinery; the prices
are stored in the configuration EEPROM and set by the central system. Every
number in the examples below is a laboratory value chosen for testing. What one
charge unit is worth, in money or in time, is unknown. All behaviour here was
observed in the emulator with a simulated card, clock and line (labels: see
[SERVER.md](SERVER.md)).

---

## 1. The pipeline

The phone charges locally. It doesn't ask the server what each call costs.

```text
Digits → dial-plan category → permission / card checks
       → free path   OR   paid path
                          → wait for answer (supervision mode)
                          → initial charge at answer
                          → repeat charge every period
                          → card balance written after each charge
       → hang-up → accounting record
```

1. **Dial plan** puts the number in a category: free, barred, or paid 0–9
   ([PHONE.md](PHONE.md) §6). The built-in fallback plan treats `01`–`09` as
   paid category 1 and `00` as paid category 2. A downloaded plan replaces it.
2. **Permissions.** Whether a given card may use a given paid category is
   controlled separately. The parameter that does this hasn't been identified.
3. **Free calls** skip answer supervision, card writes and (under the default
   logging mask) the accounting record.
4. **Paid calls** wait for the answer condition set by 114/115, then charge.

Let `z` be the paid category, 0–9 (the classifier's raw code minus one).

---

## 2. What sets the price

| Parameters | Meaning | Notes |
|---|---|---|
| 130 + z | Initial charge, quantity debited at answer | 4 digits |
| 140 + z | Repeat charge, debited each further period | 4 digits |
| 210 + z | Length of the first period | 4 digits |
| 220 + z | Length of each later period | 4 digits, capped at 524 |
| 200 + z | Pre-answer timer, used by supervision mode 2 | 4 digits |
| 150 + z | Pulse allowance, used by supervision mode 0 | 2 digits |
| 114 / 115 | Supervision mode: categories 1–9 / category 0 | 0–4 |
| 231 | Global metering-mode selector | 0–3, only 1 tested |
| 235 | Which categories use the local timing branch | ten-bit category mask |
| 232, 233 | Time-window adjustment: categories, percentage | |
| 240, 241 | Daily window start and end | `hh mm` |
| 246, 247 | Date window start and end | `YY MM DD hh mm` |
| 860 + z, 870 + z | Alternate initial / repeat charge bank | selected by the card |
| (card-range row) | Card scale and the alternate-bank flag | type `3D` download |

**Units.** Charges are plain quantities ("units"). Periods are counted in the
ROM's nominal second: 125 scheduler ticks of 8 ms. If the 1 MHz clock
assumption holds, that is one real second; it hasn't been measured.

---

## 3. Worked example

Lab settings for category 1: initial charge (131) = 2, repeat charge (141) = 3,
first period (211) = 2, later period (221) = 3. Card credit 100. Supervision
mode 1 (charging starts on the answer transition).

Idealised timeline from answer, ignoring scheduler latency:

| Time after answer | Event | Debit | Card |
|---:|---|---:|---:|
| 0 s | answer | 2 | 98 |
| 2 s | first period ends | 3 | 95 |
| 5 s | | 3 | 92 |
| 8 s | | 3 | 89 |
| 11 s | | 3 | 86 |
| 14 s | | 3 | 83 |
| 17 s | | 3 | 80 |

This matches the lab run (about 20 s: one initial charge and six repeats, final
balance 80, total debit 20). In the emulator the first expiry has some phase
and latency, so exact times vary slightly.

In general, for a call of `t` seconds after answer, with `p1` and `p2` the first
and later periods, `a` the initial charge and `b` the repeat charge:

```text
repeats = 0                              if t < p1
repeats = 1 + floor((t − p1) / p2)       if t ≥ p1
debit   = a + repeats × b
```

A three-minute call on those settings (t = 180): repeats = 1 + floor(178/3) =
60, debit = 2 + 60 × 3 = **182 units**. This formula is my reading of the
observed behaviour, not something tested at that length.

---

## 4. Modifiers

### Answer supervision (114/115)

| Mode | Charging starts on | Lab debits (credit 100) |
|---:|---|---|
| 0 | First filtered pulse on PORTA bit 2 | 2, 3, 3 for three pulses |
| 1 | Transition on controller input 13, then local timer | 2, then 3 per period |
| 2 | The pre-answer timer (200 + z) expiring | 2, 3, 3, 3, 3 |
| 3 | Pulse/timer routes exist | Not exercised |
| 4 | Matrix key B or C (283 = 2 or 3) after dialling | 2, 3, 3, 3 |

In mode 0 a pulse shorter than the software filter (4 ms tried) is rejected
and a 100 ms pulse accepted. With 151 = 2 (pulse allowance) the same three
pulses debited 2, 3 instead of 2, 3, 3.

### Time-of-day and date windows (232, 233, 240, 241, 246, 247)

When the clock is inside an enabled window and the category is selected by 232,
the ROM stretches the periods:

```text
adjusted period = floor(period × 100 / 233)
```

With 233 = 50 the periods double (2 → 4, 3 → 6) and the **amounts stay the
same**, so the call costs less per second. The repeat period is still capped at
524. Verified results:

- Date window `2611010000`–`2611302359`, clock 2026-11-14: 2, 3, 3, 3 (balance
  89 rather than 80 for the same call length). Clock 2026-12-14 (outside): the
  normal total of 20.
- Daily window 10:00–11:00 is **start-inclusive, end-exclusive**: off at 09:59,
  on at 10:00, off at 11:00. A 22:00–06:00 window wraps midnight (on at 22:00,
  23:00 and 05:59; off at 06:00 and 21:59).
- The window is rechecked during the call: a call starting at 10:59:45 switched
  back to the normal period when the window closed.

### Card scale and alternate bank

- The accepted card-range row carries a **scale** (BCD, 1–99). Charges are
  rounded up to whole card units by ceiling division, with a residual carried so
  that rounding doesn't compound. Scale 3 with quantities 2 and 2: seven charges
  totalling 14 became five one-unit card writes and a scaled debit of 15.
- A flag in the row (byte 2, bit `08`) makes the phone read charges from
  **860 + z** and **870 + z** instead of 130 + z and 140 + z. With 861 = 7 and
  871 = 11 the card went 100 → 93 → 82 → 71 → 60, while 131/141 stayed 2/3.

### Low credit and failures

| Situation | Behaviour |
|---|---|
| Credit 0 | Message `3C0C`, no dial |
| Credit smaller than the charge | The debit is capped to what is left and the period shortened in proportion (minimum 1). Credit 1: one unit debited. Credit 4 with charges 2, 3: debited 2 then 2. Call closes at exhaustion (`3C17`). |
| Card write gets no reply | Same request sent three times in total, then `3C1C` and the call closes. The record shows the **last acknowledged** balance. |
| One reply lost | The retry succeeds; charges that built up in the meantime go out together (2, 3, **6**, 3, 3, 3) |
| Card removed (contact) | Call closes; record holds what was actually debited |

### Free calls

Free is a property of the dial plan, not of the tariff. `0800…` is paid
category 1 in the fallback plan. A downloaded plan can make `0800` free: no
card needed, no debit, no paid record. See
[CONFIGURATION.md](CONFIGURATION.md) §6.

---

## 5. Where to find real values

If a phone's EEPROM is still the original, a dump may hold the real tariff.
Logical addresses (the EEPROM is paged into an 8 KiB window; see
[SETTINGS.md](SETTINGS.md)). Amounts and periods are stored as 16-bit binary
words (probably big-endian; unconfirmed) while the wire uses four BCD digits.
Category masks are 16-bit with category `z` at bit `15 − z`: `4000` is category
1, `FFC0` is categories 0–9.

| Parameter | Address | Bytes | Value (z = 0 … 9) |
|---|---|---:|---|
| 114 | `$1175` | 1 | |
| 115 | `$1176` | 1 | |
| 130 + z | `$11A3 + 2z` | 2 each | |
| 140 + z | `$11B7 + 2z` | 2 each | |
| 150 + z | `$11CB + z` | 1 each | |
| 170 + z (alias 860) | `$11FD + 2z` | 2 each | |
| 180 + z (alias 870) | `$1211 + 2z` | 2 each | |
| 200 + z | `$122F + 2z` | 2 each | |
| 210 + z | `$1243 + 2z` | 2 each | |
| 220 + z | `$1257 + 2z` | 2 each | |
| 231 | `$126B` | 1 | |
| 232 | `$126C` | 2 | |
| 233 | `$126E` | 1 | |
| 235 | `$126F` | 2 | |
| 240 / 241 | `$1271` / `$1273` | 2 each | |
| 246 / 247 | `$1275` / `$127A` | 5 each | |
| 283 | `$12AE` | 1 | |

Also record, from any phone that has been used: the prefix classes in the
dial-plan table at flash `$8400` (outside the EEPROM), the card-range rows, and
any pending call records ([ACCOUNTING.md](ACCOUNTING.md)), which show real
dialled numbers with the charge actually applied.

With actual values, the unit question can be tested: compare a
pending record's length field with its debit and see which tariff entry fits.
Currency still needs outside evidence, such as the operator's published card
prices.

---

## 6. Not established

- The money or time value of a unit; the operator's real tariffs and dial plan.
- The parameter that grants each card access to each paid category.
- Mode 3, the mode-4 secondary detector, adaptive-pulse behaviour, and most
  combinations of 114/115 with 231 and 235.
- Real pulse polarity, frequency and answer wiring.
- Calibrated seconds for the nominal periods.
- Real smart-card write semantics: the lab card is a plain memory model with
  idempotent writes.
