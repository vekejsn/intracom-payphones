# Intracom Payphones (and Reverse Engineering)

Intracom is a Greek company, that produces a lot of telecommunication equipment, including payphones.

The purpose of this repository is to collect information about Intracom payphones, and to (attempt to) reverse engineer them, in order to understand how they work, and how to interface with them.

## Repository Structure

- `documents/` - marketing materials, product brochures, and other documents related to Intracom payphones.
- `documents/clippings/` - newspaper, website and magazine clippings about Intracom payphones.
- `documents/marketing/` - marketing materials and product brochures for Intracom payphones.
- `firmwares/` - firmware dumps from Intracom payphones, organized by version.
- `tools/` - tools and scripts for analyzing Intracom payphone firmware and data.

## Payphone Models

Intracom's payphone range is built around the **INT** series of card-operated
public terminals, extended by the **MUST** series for ISDN. Every terminal is
supervised by the **CSMS** (Cardphone Supervision & Maintenance System) and is
usually paired with an exchange-side **Line Unit** that handles debiting and
anti-fraud detection.

### Cardphones

| Model | Type | Network | Dimensions (H x W x D) | Weight |
|---|---|---|---|---|
| **INT 100** | Indoor; table top or wall mounted | Analog (PSTN) | 75 x 189 x 220 mm | 1 kg (3 kg with inclined base) |
| **INT 200** | Outdoor, wall mounted, all weather | Analog (PSTN) | 275 x 275 x 172 mm | 6.5 kg |
| **INT 200 GSM** | Outdoor, wall mounted | GSM 900 / DCS 1800 | - | - |
| **MUST 400** | ISDN terminal | ISDN U-interface | 290 x 285 x 155 mm | 6 kg |

Common to the INT series: a chip card reader (Eurochip I & II, T2G, 104-bit
EEPROM / 256-bit EPROM), five SAM sockets for security modules, a 12-key
keypad (DTMF or pulse) plus four software-programmable function keys, an STN
display (2 x 20 alphanumeric, or graphics, optionally backlit), line-powered
operation (18-100 mA, no battery), a built-in V.23 asynchronous modem,
multilingual support and full firmware downloading from the CSMS. The INT 100
and the INT 200 share the same main board and card reader.

- **INT 100** - compact indoor terminal for supervised premises (hotels,
  restaurants, offices) where a heavy-duty outdoor unit is not suitable.
  Optional inclined base, fax/modem terminal adapter, satellite connection.
- **INT 200** - outdoor, all-weather, wall-mounted terminal for unattended
  public sites, in a vandal-resistant metal housing. Optional GSM interface.
- **INT 200 GSM** - the INT 200 with an integrated GSM module (2 W or 8 W
  transceiver) for areas without fixed network infrastructure, on-board public
  transport such as trains and ships, or temporary use at exhibitions, fairs
  and sporting events. Optional solar panel power supply, various antennas.
- **MUST 400** - *Multiple Services Terminal*. The ISDN member of the range,
  with a large 1/4 VGA LCD and eight programmable buttons beside the screen.
  Content is served by the CFDS (Content Formatting and Distribution System):
  directory, weather forecast, SMS sending, e-mail reception, neighborhood
  map, on-duty emergency places, stock exchange and exchange rate information.
  Communication with the CFDS is authenticated by an AAA server.

### Romanian deployment (Intrarom / ROMTELECOM)

INTRAROM, the Romanian subsidiary, manufactured, supplied and maintained the
ROMTELECOM public cardphone network - over 35,000 Intracom-designed
cardphones - and developed the national cardphone management system. From 2000
onwards the phones in that network use EUROCHIP 2 technology.

### Sources

- [Integrated Cardphone System](documents/marketing/inter_cardphone.pdf) - INT 100, INT 200, Line Unit, CSMS
- [MUST 400 Cardphone](documents/marketing/must_400_cardphone.pdf) - MUST 400
- [Phone Booth Series 100/200](documents/marketing/phone_booths.pdf) - booth models
- [Intrarom product listing (archived)](documents/clippings/payphone-models.txt) - adds the INT 200 GSM and LU 300 model names
- [Intrarom / ROMTELECOM public telephony](documents/clippings/romtelecom.txt) - Romanian deployment

