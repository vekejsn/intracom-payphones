We tend to attach two files here, for each firmware version:

- One is the raw binary file, that is what the device actually runs. The file is named `SOURCE.BIN`.
- The other is the "unscrambled" version, which has the D4 and D5 bits in each byte reversed. This file is named `UNSCRAMBLED.BIN`.

To convert between the formats, use the `scramble.py` script in the `tools` directory.

To convert from the raw binary to the unscrambled version, run:

`python3 tools/scramble.py --unscramble SOURCE.BIN UNSCRAMBLED.BIN`

To convert from the unscrambled version back to the raw binary, run:

`python3 tools/scramble.py --scramble UNSCRAMBLED.BIN SOURCE.BIN`

Additionally, you may attach an optional text file named `README.txt` that contains any relevant information about the firmware version - where it came from, what phone it was extracted from, etc. This is not required, but it is helpful for future reference.