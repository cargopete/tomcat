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
| `src/pwm.py` | Thin wrapper over the kernel's `/sys/class/pwm` hardware PWM |
| `src/tone_sweep.py` | Hardware-PWM 20→24 kHz sweep, for spectrum-analyser verification |
| `src/catdeter.py` | The main program: PIR → burst, quiet hours, cooldown, SQLite logging |
| `dashboard/app.py` | Read-only Flask web view: fires/day, hour-of-day histogram, recent events |
| `systemd/*.service` | systemd units for the deterrent and (optionally) the dashboard |
| `docs/BUILD.md` | The complete beginner build guide: electronics, wiring, BOM, weatherproofing, dog safety |

## Hardware in one breath

Raspberry Pi 4 · DFRobot SEN0018 PIR · IRLZ44N MOSFET · F28 piezo horn ·
12 V DC adapter · 220 Ω / 10 kΩ ×2 / 22 kΩ / 33 Ω resistors · 1N4148 diode ·
ABS IP66 enclosure. Full bill of materials with elimex.bg product links in
[docs/BUILD.md §7](docs/BUILD.md).

**Pins used (4 of them):**

| Physical pin | BCM | Use |
|---|---|---|
| 2  | 5 V     | PIR VCC |
| 6  | GND     | Common ground (**must** be shared with the 12 V supply ground) |
| 11 | GPIO17  | PIR OUT (**via voltage divider — see below**) |
| 12 | GPIO18 (PWM0) | Hardware PWM to MOSFET gate |

> ### ⚠️ Protect GPIO17 from the PIR's 4 V output
> The SEN0018's OUT pin drives **4 V** HIGH, but the Pi's GPIO absolute maximum
> input is **3.3 V**. The Pi reads it as a logic HIGH either way, and many
> builders wire it direct without immediate damage — but the formally-correct,
> Pi-protecting wiring is a two-resistor divider that drops 4 V to ~2.7 V:
>
> ```
>   PIR OUT ──[ 10 kΩ ]──┬── GPIO17 (pin 11)
>                        │
>                     [ 22 kΩ ]
>                        │
>                       GND
> ```
> This is the wiring documented in [docs/BUILD.md §2.3 / §2.4](docs/BUILD.md); see
> [the Caveats section](docs/BUILD.md) for the full reasoning.

## Quick start

On a fresh Raspberry Pi OS Lite (64-bit):

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y python3-pip python3-gpiozero python3-lgpio sqlite3

# Enable hardware PWM0 on GPIO18, and free the PWM peripheral from the
# onboard audio driver, which otherwise claims it. Both need a reboot.
sudo sh -c 'printf "\ndtoverlay=pwm-2chan\n" >> /boot/firmware/config.txt'
sudo sed -i 's/^dtparam=audio=on/dtparam=audio=off/' /boot/firmware/config.txt
sudo reboot

# After the reboot, /sys/class/pwm/pwmchip0 should exist:
ls /sys/class/pwm/

git clone https://github.com/cargopete/tomcat.git ~/tomcat

# 1. Test the PIR (wave your hand)
python3 ~/tomcat/src/pir_test.py

# 2. Test the ultrasonic output (verify with a phone spectrum analyser)
sudo python3 ~/tomcat/src/tone_sweep.py

# 3. Run the full thing as a service
sudo cp ~/tomcat/systemd/catdeter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now catdeter.service
journalctl -u catdeter -f
```

> ### Why no `pigpio`?
> Earlier versions of this project drove GPIO18 through `pigpio`. That package
> was **dropped from Debian trixie**, the base of current Raspberry Pi OS. The
> client pieces (`python3-pigpio`, `pigpio-tools`) are still in the archive but
> the `pigpiod` daemon they talk to is not, so `pigpio.pi()` connects to
> nothing and the program silently never makes a sound. We now drive the same
> SoC peripheral through the kernel's `/sys/class/pwm` interface instead: no
> daemon, no third-party library, no root-mapped `/dev/mem`. This is why the
> `dtoverlay=pwm-2chan` line above is not optional.

## Status

Verified on hardware, 22 August 2026, Raspberry Pi 4 Model B, Raspberry Pi OS
Lite 64-bit (trixie, image 2026-06-18):

- Kernel hardware PWM on GPIO18 produces a frequency-accurate square wave,
  read back from `period` in sysfs and confirmed with `pinctrl`.
- The complete drive chain works: GPIO18 → 220 Ω → IRLZ44N gate, drain → 33 Ω →
  piezo horn → 12 V rail, with a shared ground. Confirmed **by ear**, by
  dropping the sweep to 3 kHz where a human can hear it.
- `SIGTERM`, which is what `systemctl stop` sends, now silences the output.
  Tested rather than assumed, because the first version did not and happily
  left the horn running after the process had died.

**Not** verified, and worth stating plainly:

- **Acoustic output at 20–24 kHz.** Phone spectrum analysers roll off above
  roughly 16 kHz and A-weight what is left, so they cannot measure it. No
  calibrated ultrasonic microphone has been near this build.
- **Any deterrent effect on any cat.** No cat has been observed. The SPL
  figures quoted in [docs/BUILD.md](docs/BUILD.md) come from the Nelson et al.
  study of the commercial CATWatch, not from this device.
- An audible frequency probe suggested the horn is loudest around 5–8 kHz and
  falls away above that, which would be poor news for a 20–24 kHz deterrent.
  That reading was taken from *behind* a directional horn, using ears that roll
  off across the same band, so it is inconclusive in both directions. It wants
  following up with a real instrument.

## Tuning

Every knob has a sane default in `src/catdeter.py` and can be overridden with a
`TOMCAT_*` environment variable — so you tune without editing source. Copy
[`.env.example`](.env.example) to `.env`, edit, and the systemd unit picks it up
(`EnvironmentFile=-/home/pi/tomcat/.env`):

```bash
cp .env.example .env
# e.g. half volume for week one:
echo 'TOMCAT_DUTY=250000' >> .env
sudo systemctl restart catdeter
```

Key settings:

- `TOMCAT_DUTY` — `500000` is 50 % (full). Start at `250000` (25 %, ~6 dB quieter) for week one.
- `TOMCAT_QUIET_START_H` / `TOMCAT_QUIET_END_H` — default 22:00–07:00, no firing at night.
- `TOMCAT_BURST_SECONDS`, `TOMCAT_COOLDOWN_S` — burst length and minimum gap between bursts.

Full list with comments in [`.env.example`](.env.example).

## Safety notes (the short version)

- **Keep both mains adapters indoors.** Only DC (12 V and the Pi's 5 V) goes outside.
- The 12 V supply ground **must** be tied to the Pi's GND — non-negotiable.
- Use the **IRLZ44N**, not the IRFZ44N — the latter won't switch fully from 3.3 V.
- Watch the dogs closely for the first week and back off if they show distress.

## Dashboard

A small read-only web view of the event log — total fires, fires in the last
24 h, suppressed (quiet-hours/cooldown) counts, a fires-by-hour histogram, a
per-day table, and the most recent detections. No JavaScript, no build step.

```bash
pip install -r dashboard/requirements.txt
python dashboard/app.py            # serves on http://<pi-ip>:8080/
```

Or run it on boot alongside the deterrent:

```bash
sudo cp ~/tomcat/systemd/catdeter-dashboard.service /etc/systemd/system/
sudo systemctl enable --now catdeter-dashboard.service
```

It reads the same `TOMCAT_DB_PATH` as the deterrent and opens the DB read-only,
so it can never disturb the log.

## Development

The hardware-free logic (quiet-hours windowing, etc.) is unit-tested and runs
on any machine — `pigpio` is stubbed in tests, so you don't need a Pi to hack
on it:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check .      # lint
pytest -q         # tests
```

CI runs the same lint + compile + tests on every push and PR.

## Roadmap

- [x] Flask dashboard over the SQLite `events` table
- [ ] 10-second camera clip per detection
- [ ] v2 board: anti-phase H-bridge (+6 dB) and LC resonance boost
- [ ] Eventual Rust port using `rppal`

## Licence

MIT — see [LICENSE](LICENSE).
