#!/usr/bin/env python3
"""Scramble / unscramble Intracom payphone firmware images.

The firmware that the phone actually runs (``SOURCE.BIN``) has the D4 and D5
bits of every byte swapped with respect to the readable image
(``UNSCRAMBLED.BIN``).  Swapping two bits is its own inverse, so ``--scramble``
and ``--unscramble`` apply the very same transformation; the two flags only
express the direction you think about the file in.

Bit numbering follows Motorola convention: D0 is the least significant bit, so

    D4 = 0x10
    D5 = 0x20

Usage::

    python3 tools/scramble.py --unscramble SOURCE.BIN UNSCRAMBLED.BIN
    python3 tools/scramble.py --scramble UNSCRAMBLED.BIN SOURCE.BIN
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Motorola-style bit numbering: D0 is the LSB.
D4 = 0x10
D5 = 0x20
MASK = D4 | D5


def build_table() -> bytes:
    """Build the 256-byte translation table that exchanges D4 and D5.

    A byte is decomposed into its two bit positions::

        value = (rest & ~MASK) | (d4 << 4) | (d5 << 5)

    and reassembled with the two bit fields exchanged::

        result = (rest & ~MASK) | (d4 << 5) | (d5 << 4)
    """
    table = bytearray(256)
    for value in range(256):
        rest = value & ~MASK
        d4 = value & D4
        d5 = value & D5
        table[value] = rest | (d4 << 1) | (d5 >> 1)
    return bytes(table)


TABLE = build_table()


def transform(data: bytes) -> bytes:
    """Return *data* with the D4 and D5 bits of every byte swapped."""
    return data.translate(TABLE)


def convert(source: Path, destination: Path) -> tuple[int, int]:
    """Transform *source* into *destination*; return (total, changed) counts."""
    original = source.read_bytes()
    converted = transform(original)

    destination.write_bytes(converted)

    changed = sum(1 for a, b in zip(original, converted) if a != b)
    return len(original), changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scramble.py",
        description=(
            "Convert between the raw firmware and the unscrambled image by "
            "swapping the D4 and D5 bits of every byte."
        ),
        epilog="The transformation is its own inverse: --scramble and "
        "--unscramble do the same thing.",
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--unscramble",
        action="store_true",
        help="convert a raw firmware image into the readable (unscrambled) one",
    )
    mode.add_argument(
        "--scramble",
        action="store_true",
        help="convert an unscrambled image back into the raw firmware",
    )

    parser.add_argument("source", type=Path, help="file to read")
    parser.add_argument("destination", type=Path, help="file to write")

    args = parser.parse_args(argv)

    try:
        total, changed = convert(args.source, args.destination)
    except FileNotFoundError:
        print(f"error: no such file: {args.source}", file=sys.stderr)
        return 1
    except IsADirectoryError:
        print(f"error: not a file: {args.source}", file=sys.stderr)
        return 1
    except PermissionError:
        print(f"error: permission denied: {args.destination}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    direction = "unscrambled" if args.unscramble else "scrambled"
    print(
        f"{args.source} -> {args.destination}: wrote {total} bytes "
        f"({changed} bytes modified) as {direction} image"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
