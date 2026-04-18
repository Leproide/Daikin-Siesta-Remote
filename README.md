# Daikin Siesta Local LAN Control via Panamalar Tuya IR Hub

Control your **Daikin Siesta** air conditioner **locally** over your LAN (no cloud, no internet required) through a cheap Tuya-compatible IR hub. Includes a fully reverse-engineered Daikin Siesta IR protocol implementation in pure Python, a desktop remote-control GUI, and a CLI for automation.

<img width="371" height="1003" alt="Daikin_Remote" src="https://github.com/user-attachments/assets/89d23499-330c-489c-97a8-684d785a92a5" />

## Why?

Daikin Siesta splits don't come with Wi-Fi natively. Official smart-control options require cloud-connected IR blasters (SmartLife / Tuya app) that depend on Chinese servers, online accounts, and an internet connection. This project cuts all of that out: commands travel directly from your PC to the IR hub over your local network.

- **No cloud** — the IR hub communicates over your LAN via the Tuya local protocol
- **No SmartLife app needed** at runtime (only for initial pairing)
- **No manual learning** — IR codes are generated on the fly from a reverse-engineered protocol
- **Every feature** of the original remote: mode, temperature, fan speed, swing, LED, X-FAN

## Hardware

This project was built and tested specifically with this IR controller:

**Panamalar IR001 Universal IR Remote Control Hub** — [Amazon IT: B07K8M7HR6](https://www.amazon.it/dp/B07K8M7HR6)

It should also work with any other Tuya-based IR blaster that uses `control_type=1` (DPS 201/202). Other Tuya IR hubs with the newer DPS 1–13 protocol may need minor changes in `tinytuya` configuration.

## Features

- **Pure-Python Daikin Siesta encoder** — no C++ dependencies, no external IR libraries
- **4 operating modes**: Cool, Heat, Dry, Fan
- **Full state control**: temperature (16–30°C), fan speed (auto / turbo), swing, unit LED, X-FAN
- **Desktop GUI** styled like the physical remote
- **Preset system** — save any configuration and invoke it with one command
- **CLI mode** — send commands or presets directly without opening the UI (ideal for Task Scheduler, cron, Home Assistant, shell automation)

## Requirements

- Python 3.9+
- Tkinter (included in standard Python on Windows / macOS; on Linux install `python3-tk`)
- [tinytuya](https://github.com/jasonacox/tinytuya)

```bash
pip install tinytuya
```

## Setup

### 1. Pair the IR hub with SmartLife

Use the Tuya / SmartLife mobile app to pair your IR hub the usual way. This only needs to be done once.

### 2. Get local credentials

Follow the tinytuya wizard to recover the device's local key:

```bash
python -m tinytuya wizard
```

The wizard walks you through creating a free Tuya IoT Platform account, registering an API project, and linking your SmartLife app via QR code. At the end you'll have a `devices.json` with the **Device ID**, **IP address**, and **local key** of every Tuya device in your account.

For detailed instructions see the [tinytuya setup guide](https://github.com/jasonacox/tinytuya#tinytuya-setup-wizard).

### 3. Install dependencies and configure

```bash
git clone https://github.com/<you>/daikin-siesta-local.git
cd daikin-siesta-local
pip install -r requirements.txt
```

Copy the config template and fill in your credentials (from the wizard's `devices.json`):

```bash
cp config.example.py config.py
```

Edit `config.py`:

```python
DEVICE_ID  = "bfxxxxxxxxxxxxxxxxxxxx"   # from devices.json
DEVICE_IP  = "192.168.1.xxx"            # from devices.json
DEVICE_KEY = "xxxxxxxxxxxxxxxx"         # from devices.json
```

`config.py` is listed in `.gitignore` so your credentials will never be committed. That's it — you can now control the AC.

## Usage

### Desktop GUI

```bash
python daikin_remote_gui.py
```

![remote-screenshot](docs/remote.png)

Each click sends the full AC state to the unit instantly — same behavior as a real Daikin remote (which transmits its entire state on every button press, not delta commands).

### Save presets from the GUI

1. Set the GUI to the state you want (e.g. `Heat 21°C Auto, LED off, X-FAN on`)
2. Click **💾 SAVE CURRENT COMMAND**
3. Enter a name (the app suggests one based on the state, e.g. `heat_21_auto`)

Presets are stored in `daikin_presets.json` next to the script.

### Send presets from the CLI (automation)

```bash
# List saved presets
python daikin_remote_gui.py --list

# Send a preset (no GUI opens)
python daikin_remote_gui.py --send evening_winter

# Delete a preset
python daikin_remote_gui.py --delete old_preset
```

**Exit codes**:

| Code | Meaning                              |
| ---- | ------------------------------------ |
| 0    | Success                              |
| 1    | Preset not found / invalid arguments |
| 2    | Connection to IR hub failed          |

### Windows Task Scheduler example

Create a daily task to turn the AC on at 7:00 PM in winter:

- **Program/script**: `C:\Python313\python.exe`
- **Arguments**: `C:\Scripts\daikin_remote_gui.py --send evening_winter`

Or a simple `.bat` on the desktop:

```bat
@echo off
python "C:\Scripts\daikin_remote_gui.py" --send evening_winter
```

### Use the encoder as a library

Generate an IR code for any arbitrary state:

```python
from daikin_siesta_encoder import generate

code = generate(
    power=True, mode="cool", temp=23,
    turbo=False, swing=True, led=True, xfan=True,
)
# `code` is a base64 string ready to send through the Tuya IR hub
```

## Daikin Siesta IR Protocol (reverse-engineered)

The protocol documented here was reverse-engineered by capturing IR codes from the physical Siesta remote using the Panamalar hub's learning mode, decoding them into pulse timings, then bit-diffing related captures (e.g. 20 °C vs 22 °C vs 24 °C) to isolate every meaningful bit.

### Pulse timings

All values in microseconds.

| Segment    | Mark (µs) | Space (µs) |
| ---------- | --------- | ---------- |
| Header     | 9000      | 4430       |
| Bit (zero) | 680       | 530        |
| Bit (one)  | 680       | 1625       |
| Frame gap  | 680       | 20 000     |
| End gap    | 680       | 30 000     |

The signal consists of **2 frames** separated by a 20 ms gap. The second frame has no header — it's just the trailing mark of frame 1's last bit + gap, then data bits of frame 2 start immediately.

- **Frame 1**: 35 data bits (4 full bytes + 3 bits of the 5th byte)
- **Frame 2**: 32 data bits (4 bytes)

Byte encoding is **LSB first**.

### Frame 1 — 5 bytes

| Byte | Meaning                                                                             |
| ---- | ----------------------------------------------------------------------------------- |
| 0    | Mode + swing: low nibble = mode code, bit 6 (`0x40`) = swing on                     |
| 1    | Temperature − 16 (i.e. `22°C` → `0x06`, `24°C` → `0x08`)                            |
| 2    | Feature flags: bit 4 (`0x10`) = turbo, bit 5 (`0x20`) = LED, bit 7 (`0x80`) = X-FAN |
| 3    | Constant `0x50`                                                                     |
| 4    | Constant `0x02` (only the low 3 bits are transmitted — total frame = 35 bits)       |

### Frame 2 — 4 bytes

| Byte | Meaning                                                                     |
| ---- | --------------------------------------------------------------------------- |
| 0    | Bit 0 (`0x01`) = swing state echo (mirrors the swing bit in frame 1 byte 0) |
| 1    | Constant `0x20`                                                             |
| 2    | Constant `0x00`                                                             |
| 3    | Checksum — see formula below                                                |

### Mode codes (Frame 1, Byte 0)

| Mode | Hex value | Binary      | Notes                                   |
| ---- | --------- | ----------- | --------------------------------------- |
| OFF  | `0x01`    | `0000 0001` | Unit is off. Temperature is ignored.    |
| Cool | `0x09`    | `0000 1001` |                                         |
| Heat | `0x0C`    | `0000 1100` |                                         |
| Dry  | `0x1A`    | `0001 1010` | Note: sets bit 4 of the high nibble too |
| Fan  | `0x0B`    | `0000 1011` | Temperature ignored by the AC           |

If swing is on, bit 6 (`0x40`) is OR-ed into this byte.

### Feature flags (Frame 1, Byte 2)

All flags combine by OR. These are independent; any combination is valid.

| Flag  | Bit | Mask   | Effect                                               |
| ----- | --- | ------ | ---------------------------------------------------- |
| Turbo | 4   | `0x10` | Maximum fan speed (the "Powerful" button)            |
| LED   | 5   | `0x20` | Turns the display LED on the indoor unit on / off    |
| X-FAN | 7   | `0x80` | Keeps the fan running after shutdown to dry the coil |

When all flags are off, byte 2 is `0x00`. Originally-learned codes had X-FAN (and often LED) on by default, because those were the states active on the physical remote when the codes were captured.

### Checksum formula (Frame 2, Byte 3)

One single formula covers every combination of mode, temperature, and power state:

```
checksum = ((mode_low_nibble + (temperature − 20)) mod 16) × 16
```

Where `mode_low_nibble` is the low nibble of frame 1 byte 0 (see the mode table above).

**Verification table** (all captured and confirmed):

| State           | Low nibble | Temp | Formula                | Checksum byte |
| --------------- | ---------- | ---- | ---------------------- | ------------- |
| Cool 20 °C      | `0x9`      | 20   | `(9 + 0) × 16`         | `0x90`        |
| Cool 22 °C      | `0x9`      | 22   | `(9 + 2) × 16`         | `0xB0`        |
| Cool 24 °C      | `0x9`      | 24   | `(9 + 4) × 16`         | `0xD0`        |
| Heat 22 °C      | `0xC`      | 22   | `(12 + 2) × 16`        | `0xE0`        |
| Dry 22 °C       | `0xA`      | 22   | `(10 + 2) × 16`        | `0xC0`        |
| Fan 25 °C       | `0xB`      | 25   | `(11 + 5) mod 16 × 16` | `0x00`        |
| OFF (temp 22°C) | `0x1`      | 22   | `(1 + 2) × 16`         | `0x30`        |

### Complete byte examples

Real IR codes for common states (`F1` = frame 1, `F2` = frame 2, hex bytes LSB-first):

| State                            | F1               | F2            |
| -------------------------------- | ---------------- | ------------- |
| OFF                              | `01 06 80 50 02` | `00 20 00 30` |
| Cool, 22 °C, auto, no swing      | `09 06 80 50 02` | `00 20 00 B0` |
| Cool, 22 °C, auto, **swing on**  | `49 06 A0 50 02` | `01 20 00 B0` |
| Cool, 22 °C, **turbo**, no swing | `09 06 B0 50 02` | `00 20 00 B0` |
| Heat, 22 °C, auto                | `0C 06 00 50 02` | `00 20 00 E0` |
| Dry, 22 °C, auto                 | `1A 06 00 50 02` | `00 20 00 C0` |
| Fan, auto                        | `0B 09 00 50 02` | `00 20 00 00` |

## Files

| File                       | Purpose                                                        |
| -------------------------- | -------------------------------------------------------------- |
| `daikin_siesta_encoder.py` | Pure-Python encoder. Generates IR codes in Tuya base64 format. |
| `daikin_remote_gui.py`     | Tkinter remote-control GUI + preset manager + CLI.             |
| `daikin_presets.json`      | Saved presets (auto-generated).                                |
| `README.md`                | This file.                                                     |

## Troubleshooting

### The IR hub isn't found / "connection refused"

- Confirm the hub's IP is correct (it may have changed after a router reboot; reserve it via DHCP)
- Make sure your PC and the hub are on the same VLAN / subnet
- Allow outbound TCP traffic on port 6668 from your PC

### `control_type has not been detected` error

Your hub firmware uses the newer DPS layout. Try changing `control_type=1` to `control_type=2` in `daikin_siesta_encoder.py` and the GUI:

```python
d = Contrib.IRRemoteControlDevice(
    DEVICE_ID, DEVICE_IP, DEVICE_KEY,
    version=3.3, control_type=2, persist=True,
)
```

### The AC doesn't react

- Check line of sight between the IR hub and the AC unit
- Some Siesta sub-models may use slightly different mode codes or timings. Capture a working code from the physical remote and bit-diff it against the tables above. The swing bit, turbo bit, and LED bit are the most likely to vary. Open an issue with your captured bytes and I'll extend the encoder.

### Temperature changes don't take effect in Fan mode

Normal — in Fan mode the Daikin ignores the temperature field. The GUI shows `--` in that case.

## Credits

Protocol reverse-engineered by pulse-level capture and differential analysis of IR codes learned through the Panamalar IR001 hub's learning mode. No prior Daikin Siesta documentation was consulted.

## License

GPL v2
