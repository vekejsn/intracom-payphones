# Firmware Update

How the phone receives and activates new firmware from the server, as far as
the ROM and the emulator show.

Everything here comes from the unscrambled image run in an emulator with a
simulated modem, clock, controller and **flash chip**. The flash model is ours:
it accepts the `AA/55/A0` programming sequence, completes instantly and
supports a write-protect fault we added. No real flash has been programmed
and nothing here is a procedure to follow on hardware. Protocol framing is in
[SERVER.md](SERVER.md); general phone behaviour in [PHONE.md](PHONE.md).

---

## 1. Model: two images, one selector

The 256 KiB flash holds two 128 KiB images (half 0 and half 1). The original
dump has the same image in both. At reset the code at `$4100–$41B6` picks one:

| Stored byte `$0DFB` | Output PA5 | Half run |
|---|---|---|
| nonzero | low | **0** |
| zero | high | **1** |

Only `$0DFB` decides the half. The update-state byte `$0DFA` feeds a
different branch, so clearing the state alone doesn't switch images (tested
over 18 cold-reset cases: states 0–5 × `$0DFB` 0/1/`FF`).

A download goes into the **inactive** half. The first `$0800` bytes of an image
are excluded from the checksum and copied separately by the replication step;
the name "bootloader" for this region is *not* established and shouldn't be
used.

The dial-plan table at `$8400–$87FF` is not part of this scheme: it sits
outside the checksummed region and is programmed into **both** halves.

---

## 2. Messages

All frames use the normal format of [SERVER.md](SERVER.md) §2. Payloads start
with `01` (count/item) and end in marker `03` (more) or `04` (final).

| Server → phone | Phone reply | What it does |
|---|---|---|
| `1F` / `21` / `25` | `20` / `22` / `26` | Stage a block: `01 len off_hi off_lo data marker` into a staging region (EEPROM `$1C00` for `1F`) |
| `29` | `2A` | Program one 256-byte page into the inactive half after checking its additive 16-bit checksum. Reply `01 00 04` = ok. `01 01 04` was seen when no writable flash existed; a wrong checksum returns status 4. |
| `2B` | `2C` | Erase-page path (traced, not exercised) |
| `2D` | `2E` | Verify image: payload `01 csum_hi csum_lo 04`. `01 00 04` = accepted, `01 01 04` = rejected |
| `31` | control | Activate: payload `01 03` for the CPU image |
| `2F` | control | Clear the update state: payload `01 03` |

The leading `01` on `1F` matters: leaving it off produced a zero-length no-op
that still returned status 0.

### Checksum

- A page checksum (`29`) is the 16-bit additive sum of the page's 256 bytes.
- The image checksum (`2D`) is the additive sum of the whole image
  **excluding its first `$0800` bytes**. It's stored at logical `$0DFE`.
  Lab images came out at `E638`, `E639`, `E63A`. These depend on the image.
- Neither is the frame CRC.

### Typical successful sequence

1. Normal authenticated session ([SERVER.md](SERVER.md) §3.2).
2. For each page: `29` with its data, expect `2A 01 00 04`.
3. `2D` with the image checksum; on acceptance the ROM stores the checksum and
   sets update state **2** (`$0DFA`).
4. `31 01 03`: state becomes **3**, the source-half indication is stored in
   `$0DFB`, and scheduler code `11` (argument 2) is registered.
5. `0B` and `02`: session ends; phone shows `OK`.
6. The next reset runs the new half.

A rejected `2D` leaves state at 1, the peer doesn't send `31`, and the phone
reboots into the old image: the changed bytes in the other half had no effect.

---

## 3. After the reset: replication and state 4/5

When a new image boots, the ROM compares an **identifier** with the stored one.
In the lab the identifier is four bytes in a data block copied from ROM
`$4346` into RAM `$0100` (descriptor at `$4340`, length `$94`). They read
`EA 77 9D 00` in the source ROM. Setting the fourth byte (`$4349`) to 1 is the
"revision" in our test images; no code changes were needed.

If the identifier differs, the original task (`$AD15` → `$A899` → `$AC1C`)
copies the running image into the other half and checks it, ending in:

| State | Meaning | Observed |
|---:|---|---|
| 0 | Clear | After `2F` |
| 1 | — | Seen when the image checksum was rejected |
| 2 | Checksum accepted | During the download |
| 3 | Activated, awaiting first boot | After `31`; remains 3 if the identifier is unchanged |
| **4** | Copy/check succeeded | Both halves equal the new image |
| **5** | Copy/check failed | Halves differ. In the lab, writes to half 0 were refused |

The copy programs **520 pages = 133,120 bytes**: eight pages first, then all 512.
The ROM does its own read-back and checksums.

**State 5 is not a rollback.** On the next reset the phone stays on the image
it was running (half 1 in the test), retains state 5, programs nothing, and
displays the new image's text. The old image sits untouched in the other half,
but nothing switches back to it.

**State 4 second reset:** half 0 selected, state 4 kept, zero bytes programmed.

### `907#`

From the service menu (`907#`) the phone shows four hex fields:

```text
E639 E639 01 04
 │    │    │   └ update state ($0DFA)
 │    │    └ selection indicator: 1 if $0DFB ≠ 0, else 2
 │    └ half-1 checksum
 └ half-0 checksum
```

after a failed copy: `E663 E639 02 05`. The indicator is derived from the
EEPROM byte, not a measurement of PA5.

---

## 4. Recovery

- **New download.** From state 5 a second session sent a data-only revision 2
  into the other half: checksum accepted, state 3, then on reboot a fresh
  copy/check reached state 4 with both halves equal. No `2F` was needed.
- **`2F`** sets `$0DFA` from 5 to 0. It doesn't touch either image, doesn't
  change `$0DFB`, and the next reset still selects the same half. It is
  **not** a rollback.

---

## 5. Full transfer

The whole image is 512 × 256 bytes = 131,072. A complete transfer into an
initially erased (all `FF`) inactive half worked end to end in the emulator: 512
successful `2A` replies, checksum accepted, activation, normal reset,
replication to state 4, second reset on the new half.

At 1200 bit/s with 10 bits per byte, 131,072 bytes need about **18 minutes** on
the wire for the data alone; the lab run took about 24 minutes of virtual time
with framing and ACKs. That's an estimate of line time, not a measurement of a
real modem link.

The test images differed from the original in only two data bytes (a display
label and the identifier), so the executable code was never changed by any of
these tests.

---

## 6. What is not established

- Real flash behaviour: erase timing, programming delay, write protection,
  endurance, and the `2B` erase path.
- Power loss at any point (mid-page, mid-copy, before `$0DFB` changes).
- Automatic retry or rollback after state 5.
- What the real server sends and in what order; our peer script is ours.
- Whether PA5 truly switches the flash halves on the board; this is the
  emulated wiring.
- Behaviour when the changed image has different code, not just data.
