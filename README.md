# TomCat 🐾🔇

A DIY, CATWatch-style **PIR-triggered ultrasonic cat deterrent** built around a
Raspberry Pi 4 and parts sourced from [elimex.bg](https://elimex.bg). When the
PIR sees motion, the Pi's hardware PWM (GPIO18 / PWM0) generates a 20–24 kHz
square wave; an **IRLZ44N** logic-level MOSFET switches a piezo horn against a
12 V rail. Inaudible to humans, deeply unwelcome to cats.

> **Dogs first.** This device is built to be dog-safe. Aim the horn *away* from
> the dogs, keep them ≥ 8 m off-axis / ≥ 15 m on-axis, run the default quiet
> hours, and start at reduced volume. See [docs/BUILD.md §6](docs/BUILD.md) before
> you power it on in anger.

## What's in here

| Path | What it is |
|---|---|
| `src/pir_test.py` | Standalone PIR sanity check |
| `src/tone_sweep.py` | Hardware-PWM 20→24 kHz sweep, for spectrum-analyser verification |
| `src/catdeter.py` | The main program: PIR → burst, quiet hours, cooldown, SQLite logging |
| `systemd/catdeter.service` | systemd unit to run it on boot |
| `docs/BUILD.md` | The complete beginner build guide: electronics, wiring, BOM, weatherproofing, dog safety |

## Hardware in one breath

Raspberry Pi 4 · DFRobot SEN0018 PIR · IRLZ44N MOSFET · F28 piezo horn ·
12 V DC adapter · 220 Ω / 10 kΩ / 33 Ω resistors · 1N4148 diode · ABS IP66
enclosure. Full bill of materials with elimex.bg product links in
[docs/BUILD.md §7](docs/BUILD.md).

**Pins used (4 of them):**

| Physical pin | BCM | Use |
|---|---|---|
| 2  | 5 V     | PIR VCC |
| 6  | GND     | Common ground (**must** be shared with the 12 V supply ground) |
| 11 | GPIO17  | PIR OUT |
| 12 | GPIO18 (PWM0) | Hardware PWM to MOSFET gate |

## Quick start

On a fresh Raspberry Pi OS Lite (64-bit):

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y python3-pip python3-gpiozero pigpio python3-pigpio sqlite3
sudo systemctl enable --now pigpiod

git clone https://github.com/cargopete/tomcat.git ~/tomcat

# 1. Test the PIR (wave your hand)
python3 ~/tomcat/src/pir_test.py

# 2. Test the ultrasonic output (verify with a phone spectrum analyser)
python3 ~/tomcat/src/tone_sweep.py

# 3. Run the full thing as a service
sudo cp ~/tomcat/systemd/catdeter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now catdeter.service
journalctl -u catdeter -f
```

## Tuning

Knobs live at the top of `src/catdeter.py`:

- `DUTY` — `500_000` is 50 % (full). Start at `250_000` (25 %, ~6 dB quieter) for week one.
- `QUIET_START_H` / `QUIET_END_H` — default 22:00–07:00, no firing at night.
- `BURST_SECONDS`, `COOLDOWN_S` — burst length and minimum gap between bursts.

## Safety notes (the short version)

- **Keep both mains adapters indoors.** Only DC (12 V and the Pi's 5 V) goes outside.
- The 12 V supply ground **must** be tied to the Pi's GND — non-negotiable.
- Use the **IRLZ44N**, not the IRFZ44N — the latter won't switch fully from 3.3 V.
- Watch the dogs closely for the first week and back off if they show distress.

## Roadmap

- 10-second camera clip per detection
- Flask/FastAPI dashboard over the SQLite `events` table
- v2 board: anti-phase H-bridge (+6 dB) and LC resonance boost
- Eventual Rust port using `rppal`

## Licence

MIT — see [LICENSE](LICENSE).
