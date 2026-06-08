# DIY Ultrasonic Cat Deterrent — Complete Beginner Build Guide (Elimex.bg + Raspberry Pi 4)

## TL;DR
- You will build a CATWatch-style PIR-triggered 20–24 kHz ultrasonic emitter using parts sourced entirely from elimex.bg plus your existing Raspberry Pi 4. The Pi's hardware PWM (GPIO18 / physical pin 12, channel PWM0) generates the ultrasonic square wave; an **IRLZ44N** logic-level MOSFET switches a piezo horn against a 12 V rail.
- Headline parts (all confirmed on elimex.bg): DFRobot SEN0018 PIR (product 87576), IRLZ44N MOSFET (product 36316), piezo horn F28 (product 78799 — rated 93 dB sensitivity, 3 – 20 kHz, 285 × 110 × 167 mm), 12 V / 1 A or 12 V / 1.5 A adapter (products 64509 / 72724), GOODRAM 32 GB microSDHC + adapter Class 10 (product 60052), ABS IP66 enclosure 200 × 120 × 75 mm (product 68216). Elimex.bg renders prices client-side in JavaScript, so live лв prices were not present in the static page HTML at the time of writing — open each URL in your browser to confirm the current price.
- Critical dog-safety constraint already established: aim the directional horn AWAY from where the dogs are, keep dogs ≥ 8 m off-axis or ≥ 15 m on-axis, schedule quiet hours, and start with reduced volume (lower rail voltage or lower duty cycle).

---

## Key Findings

1. **Elimex.bg has every electronic part you need.** The IRLZ44N MOSFET (product 36316, "MOS-N-FET, 55V, 47A, 110W, TO-220" per elimex's own metadata), the DFRobot SEN0018 PIR module (product 87576, "PIR, 7 µm – 14 µm" per the elimex page), and the F28 piezo horn (product 78799, "Високочестотен, пиезо говорител, хорна 93dB, 3kHz-20kHz, 285×110mm, височина 167mm" per the elimex page) all resolve to live product pages with valid metadata.
2. **The architecture is sound for the Pi 4.** Per pigpio's author on the Raspberry Pi Forums: "pigpio uses the 500 MHz PLLD as the clock source for the PWM peripheral … For a frequency of 25 kHz the resolution in steps is 250 million divided by 25 thousand, or 10000." 24 kHz is therefore in pigpio's safe zone (the documented hard upper limit is ~30 MHz on the Pi 4). GPIO18 / physical pin 12 is the canonical hardware PWM0 pin.
3. **The IRLZ44N is genuinely a 3.3-V-drivable switch.** Per the Infineon datasheet, V<sub>GS(th)</sub> is 1.0 V (min) to 2.0 V (max), V<sub>DSS</sub> = 55 V, I<sub>D</sub> = 47 A — so 3.3 V from a Pi GPIO drives it solidly into its low-R<sub>DS(on)</sub> region. Do **not** substitute the elimex IRFZ44N (product 9002): that part needs ~4–10 V on the gate and will not switch fully from 3.3 V.
4. **The target SPL is reproducible.** The peer-reviewed study "The efficacy of an ultrasonic cat deterrent" in *Applied Animal Behaviour Science* (Nelson et al., doi:10.1016/j.applanim.2005.04.014) measured the original Catwatch© at "21–23 kHz and a volume of 96 dB at 1 m, declining to 56 dB at 7 m and 44 dB at 13 m." With the F28's 93 dB / 1 W / 1 m sensitivity, a 12 V square wave drive sits in the same ballpark; the optional 24 V upgrade gives an extra ~6 dB of margin.
5. **The "modulating" character is just frequency sweeping in software.** Concept Research (the British manufacturer of CATWatch) states on conceptresearch.co.uk/products/catwatch: "The CATWatch operates at a frequency of 20 – 24 kHz." Software-stepping the pigpio hardware-PWM frequency between 20 kHz and 24 kHz across each burst reproduces that behaviour and helps prevent habituation.

---

## Details

### 1. Electronics Fundamentals (Beginner Primer)

**1.1 What a GPIO pin is.** GPIO ("General Purpose Input / Output") is a simple pin on the Raspberry Pi that your software can switch ON (≈ 3.3 V) or OFF (0 V), or read as an input. The Pi 4 has 40 pins on the header along its top edge; most of them are GPIO. Think of each GPIO as a tiny digital tap your Python code can open and close.

**1.2 What PWM (Pulse-Width Modulation) is.** PWM means switching a pin between HIGH and LOW very fast and very regularly. Two numbers describe it:
- **Frequency** — full ON-OFF cycles per second, in hertz. For our project this is 20 000 – 24 000 Hz (20–24 kHz, above human hearing).
- **Duty cycle** — what percentage of each cycle is HIGH. 50 % is a true square wave.

The Pi 4's *hardware* PWM (built into the SoC, not done by software loops) is rock-solid; software PWM jitters too much for clean ultrasound.

**1.3 What a MOSFET is and why a *logic-level* one.** A MOSFET is a three-leg electronic switch:
- **Gate (G)** — the control input. Apply voltage between Gate and Source and the switch turns on.
- **Drain (D)** — one side of the switch.
- **Source (S)** — the other side (in our circuit, ground).

For a 3.3 V Pi GPIO to fully switch the MOSFET, the gate threshold must be ≤ ~2 V. The IRLZ44N's V<sub>GS(th)</sub> is **1.0 V (min) to 2.0 V (max)** (Infineon datasheet), so 3.3 V on the gate drives it deep into the ON region with R<sub>DS(on)</sub> around 22 mΩ. Why we need it here: a Pi GPIO pin can only source ~16 mA at 3.3 V, but a piezo on a 12 V rail at 20 kHz briefly demands hundreds of mA of switching current. The MOSFET is the "muscle" the small 3.3 V signal pushes around.

**1.4 Piezo tweeter — a capacitive load.** A piezo tweeter is a piezoelectric ceramic that flexes when voltage is applied. Electrically it behaves mostly like a capacitor (~15–80 nF). That makes it ideal for square-wave drive — you charge it, the ceramic flexes; discharge, it flexes back; the motion radiates sound. The piezo-horn type is very efficient and, although the F28's sticker says "3–20 kHz", piezo-horn elements radiate usefully up to ~25–30 kHz because the underlying ceramic resonance is above the rated audio passband.
- **Series resistor (~33 Ω):** limits in-rush current into the capacitance at the switching edges; 10–47 Ω is the textbook range.
- **Protection diode (1N4148):** clamps any negative spike on the drain back to the +12 V rail (cathode = banded end up to +12 V, anode down to drain). Belt-and-braces with a capacitive load but harmless to include.

**1.5 Resistors and how to read them.** 4-band code: bands 1, 2 = digits; band 3 = multiplier; band 4 = tolerance.
- 33 Ω: orange-orange-black-gold
- 220 Ω: red-red-brown-gold
- 1 kΩ: brown-black-red-gold
- 10 kΩ: brown-black-orange-gold

The **10 kΩ gate-to-source pull-down** matters: when the Pi is rebooting or the GPIO is in input mode, the gate floats and even ESD on your finger can switch the MOSFET on. The pull-down forces OFF whenever the Pi isn't actively driving HIGH. The **220 Ω gate-drive resistor** between GPIO18 and the MOSFET gate slows the in-rush into the gate capacitance so the Pi GPIO doesn't have to source a hard pulse.

**1.6 Safety basics.**
- 12 V DC is low-risk. Don't short the 12 V rail to ground; don't open the sealed adapter.
- **230 V mains is dangerous**: never open mains adapters; keep both wall adapters indoors; only DC (12 V and the Pi's 5 V) goes outside.
- ESD: touch a grounded metal object before handling the MOSFET and Pi.
- Never short the Pi's 5 V rail to GND.
- Build, then double-check, then power on.

### 2. The Complete Circuit

**2.1 The 40-pin header (physical numbering).** Pin 1 (3.3 V) is the one closest to the microSD slot. You will use exactly four pins:

| Physical pin | BCM name | Use |
|---|---|---|
| 2 | 5 V | PIR V<sub>CC</sub> |
| 6 | GND | Common ground |
| 11 | GPIO17 (BCM17) | PIR OUT input |
| 12 | GPIO18 (BCM18) — **PWM0** | Hardware PWM to MOSFET gate |

GPIO18 is the canonical PWM0 pin: the official `dtoverlay=pwm-2chan` overlay defaults to GPIO18 (PWM0) and GPIO19 (PWM1).

**2.2 pigpio hardware PWM range.** Per pigpio's documentation and Joan's confirmation on the Pi Forums: "pigpio uses the 500 MHz PLLD as the clock source for the PWM peripheral … For a frequency of 25 kHz the resolution in steps is 250 million divided by 25 thousand, or 10000." The documented hard upper limit ("Frequencies above 30 MHz are unlikely to work") sits five orders of magnitude above what we need. Duty cycle is expressed as 0–1 000 000 (so 500 000 = 50 %).

**2.3 Schematic (redraw-able).**

```
                            +12 V (adapter centre pin)
                                  │
                                  ├────────────────┐
                                  │                │
                                  │              [D1] 1N4148
                                  │               (stripe/cathode = up
                                  │                anode = down)
                                  │                │
                              [R_s 33Ω]            │
                                  │                │
                                  ├────────────────┤
                                  │                │
                              [PIEZO  HORN F28]    │
                                  │                │
                                  ├────────────────┘
                                  │
                                  D (drain)
                                  │
                              [ IRLZ44N ]
                          G ─[R_g 220Ω]── GPIO18 (pin 12)
                          │
                       [R_pd 10kΩ]
                          │
                          S (source)
                          │
                  ────────┴─────── COMMON GROUND ───────────
                          │                       │
                  Pi GND (pin 6)         12 V adapter ground (barrel sleeve)
                          │
                  PIR sensor GND
                  PIR sensor VCC ───── Pi 5V  (pin 2)
                  PIR sensor OUT ───── Pi GPIO17 (pin 11)
```

**The critical beginner rule:** the 12 V supply ground **must** be joined to the Pi's GND. The MOSFET source goes to that same common ground. Without a common ground the MOSFET has no reference for "what is 3.3 V at the gate", and the circuit will behave erratically or not at all.

**2.4 Wiring connection table.**

| From | To | Note |
|---|---|---|
| Pi pin 2 (5 V) | PIR `VCC` | Red lead of the supplied DFRobot Gravity cable |
| Pi pin 6 (GND) | PIR `GND` | Black lead |
| Pi pin 11 (GPIO17) | PIR `OUT` | Goes HIGH (4 V per DFRobot) on motion |
| Pi pin 12 (GPIO18) | One end of R_g (220 Ω) | Gate-drive resistor |
| Other end of R_g | MOSFET Gate (leg 1, leftmost with label facing you) | |
| MOSFET Gate | One end of R_pd (10 kΩ) | Pull-down |
| Other end of R_pd | MOSFET Source (leg 3, rightmost) | |
| MOSFET Source | Common ground rail | Same node as Pi pin 6 + 12 V negative |
| MOSFET Drain (leg 2 / metal tab) | One end of R_s (33 Ω) | Series limiter |
| Other end of R_s | Piezo terminal (either) | |
| Other piezo terminal | +12 V rail | Centre pin of barrel jack |
| 1N4148 anode | MOSFET Drain | |
| 1N4148 cathode (stripe) | +12 V rail | Protection / flyback diode across the piezo |
| Pi pin 6 (GND) | 12 V adapter negative | **Common ground — mandatory** |

> **IRLZ44N pinout (label facing you, legs down):** 1 = Gate, 2 = Drain, 3 = Source. The metal tab is electrically the Drain — don't let it touch grounded metal.

**2.5 Breadboard first.** Before any soldering, build on a solderless breadboard — elimex's МАКЕТНА ПЛАТКА 400 ГНЕЗДА (product 76380) is a perfect fit; the larger GL-36 (product 51358) gives more elbow room. Power-up order: wire everything dead, double-check IRLZ44N orientation and diode stripe, plug in the Pi USB-C first, *only then* plug in the 12 V adapter, run test scripts.

### 3. Step-by-Step Assembly

**Step 1 — Flash Raspberry Pi OS Lite (64-bit).**
1. Install Raspberry Pi Imager on your laptop from raspberrypi.com.
2. Insert the GOODRAM 32 GB microSD using its included SD adapter.
3. In Imager, choose *Raspberry Pi OS Lite (64-bit)*.
4. Click the ⚙ gear: hostname (`catdeter`), enable SSH with a strong password, set Wi-Fi SSID + password, set locale + keyboard. Save.
5. Write and eject.

**Step 2 — First boot, SSH in, update.**
```bash
ssh pi@catdeter.local
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y python3-pip python3-gpiozero pigpio python3-pigpio sqlite3
sudo systemctl enable --now pigpiod
```

**Step 3 — Wire on breadboard** per the table in §2.4 (Pi powered off).

**Step 4 — Test the PIR alone** (`src/pir_test.py`). Wave your hand — `MOTION` prints. Per the DFRobot wiki: "Output level(HIGH): 4V", and "Detect angle: 110 Degree, Detect distance: 7 meters" — note 110° (not 120°) and 7 m max range. The output stays HIGH for the time set by the on-board TIME potentiometer (2.3 s minimum hold).

**Step 5 — Test the PWM + MOSFET + piezo** (`src/tone_sweep.py`). You will not hear anything (ultrasonic). Verify with **Spectroid** (Android) or **SpectrumView** (iOS) within 50 cm of the horn — a clear peak between 20 and 24 kHz. To "see" PWM working before connecting the piezo, swap in an LED + 1 kΩ from drain to +5 V and run a 2 Hz PWM.

**Step 6 — Combine into the full program** (`src/catdeter.py`) and test end-to-end.

**Step 7 — Move to soldered perfboard.** Use elimex's universal board from category 948 / product 24400 ("ПЛАТКА ELIMEX"). Layout: screw terminal for 12 V in, screw terminal for piezo, header pins for the Pi GPIO cable, then the IRLZ44N, the three resistors, the diode. Solder one component at a time; multimeter beep-test continuity after each. Add a small heatsink + thermal pad to the Pi 4's main SoC.

**Step 8 — Mount in the enclosure** (elimex product 68216, ABS 200×120×75 mm IP66):
1. Cut a hole for the F28 horn through the front face; bed in clear neutral-cure silicone, cure 24 h.
2. Cut a hole for the PIR dome (the fresnel lens must see out). Seal with a silicone bead under its bezel.
3. Drill a single 3 mm drain hole on the bottom face.
4. PG7 cable gland for the 12 V lead (3–6 mm cable); PG9 for the Pi USB-C cable (4–8 mm).
5. Pi and driver board both on standoffs.

**Step 9 — Mount in the garden** per §6.

### 4. The Software (Python — full, copy-paste)

The runnable copies live in [`../src/`](../src/). They are reproduced here for reference.

**4.1 `src/pir_test.py`**
```python
#!/usr/bin/env python3
from gpiozero import MotionSensor
from time import sleep

pir = MotionSensor(17)   # BCM17 = physical pin 11

print("Warming up PIR for 30 s...")
sleep(30)
print("Ready. Wave your hand.")

while True:
    pir.wait_for_motion()
    print("MOTION")
    pir.wait_for_no_motion()
    print("...clear")
```

**4.2 `src/tone_sweep.py` — pigpio hardware PWM frequency sweep**
```python
#!/usr/bin/env python3
"""Sweep 20 kHz -> 24 kHz on GPIO18 (PWM0) using pigpio hardware PWM."""
import pigpio, time

PWM_GPIO   = 18           # BCM18 = pin 12 = hardware PWM0
F_LOW_HZ   = 20_000
F_HIGH_HZ  = 24_000
SWEEP_STEP = 250          # Hz per tick
TICK_S     = 0.020        # 20 ms per step
DUTY       = 500_000      # 50 %  (range 0..1_000_000)

pi = pigpio.pi()
if not pi.connected:
    raise SystemExit("pigpio daemon not running. sudo systemctl start pigpiod")

try:
    print("Sweeping. Use Spectroid on your phone to verify 20–24 kHz peaks.")
    while True:
        f = F_LOW_HZ
        direction = +SWEEP_STEP
        while True:
            pi.hardware_PWM(PWM_GPIO, f, DUTY)
            time.sleep(TICK_S)
            f += direction
            if f >= F_HIGH_HZ:
                direction = -SWEEP_STEP
            elif f <= F_LOW_HZ:
                direction = +SWEEP_STEP
                break
except KeyboardInterrupt:
    pass
finally:
    pi.hardware_PWM(PWM_GPIO, 0, 0)
    pi.stop()
```

**4.3 `src/catdeter.py` — main program**

See [`../src/catdeter.py`](../src/catdeter.py) for the full, current source. It:
- detects motion on BCM17,
- bursts a 20 kHz ↔ 24 kHz sweep on BCM18 (hardware PWM0) via an IRLZ44N switching a piezo horn against 12 V,
- honours quiet hours (no firing at night while dogs are out),
- enforces a cool-down between bursts to avoid habituation and excess,
- logs every detection to a local SQLite DB.

**4.4 `systemd/catdeter.service`**
```ini
[Unit]
Description=TomCat ultrasonic cat deterrent
After=network.target pigpiod.service
Requires=pigpiod.service

[Service]
Type=simple
User=pi
ExecStart=/usr/bin/python3 /home/pi/tomcat/src/catdeter.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```
Enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now catdeter.service
journalctl -u catdeter -f
```

**4.5 Forward-looking.** The `events` SQLite table can later feed a tiny Flask/FastAPI dashboard so you see when and how often the device fires; a USB or Pi Camera can record a 10-s clip per detection. A Rust port using `rppal` + the `pigpio` Rust bindings is straightforward later — for now stay on Python.

### 5. The Piezo Drive — Loudness & Correctness

**5.1 Will 12 V be loud enough?** The original Catwatch© was measured at "a frequency of 21–23 kHz and a volume of 96 dB at 1 m, declining to 56 dB at 7 m and 44 dB at 13 m" (Nelson et al., *Applied Animal Behaviour Science*, doi:10.1016/j.applanim.2005.04.014). The F28 horn's 93 dB / 1 W / 1 m sensitivity combined with the few-watt reactive drive available from a 12 V square wave into a ~30–80 nF piezo at 20 kHz puts our build in essentially the same SPL bracket. Because the F28 is a horn it concentrates SPL forward, so 10–12 m on-axis range is realistic.

**5.2 If you want more SPL.**
- **Raise the rail voltage to 18 V or 24 V** from elimex's мрежови адаптери (category 956). The IRLZ44N's 55 V breakdown gives ample headroom. Each doubling of voltage ≈ +6 dB SPL.
- **Anti-phase / H-bridge drive (v2 upgrade).** Two MOSFETs driven from BCM18 (PWM0) and BCM19 (PWM1) 180° out of phase give the piezo ±V<sub>rail</sub> swings instead of 0…V<sub>rail</sub> — about +6 dB.
- **LC resonance boost (advanced).** A 1–2 mH series inductor with the piezo's ~30–80 nF resonates near 20 kHz and steps up the voltage across the piezo significantly. Needs an oscilloscope to tune.

**5.3 Duty cycle and harmonics.** A 50 % duty-cycle square wave at 20 kHz has odd harmonics at 60 kHz, 100 kHz … All inaudible to humans, all in the cat-audible range, and the F28 rolls them off naturally above ~30 kHz so we don't waste energy. To **reduce loudness** (for dog-friendliness or testing), set `DUTY = 250_000` (25 %): less RMS energy in the fundamental, ~6 dB quieter.

**5.4 Sweeping the frequency.** Concept Research (manufacturer of CATWatch) states on conceptresearch.co.uk/products/catwatch: "The CATWatch operates at a frequency of 20 – 24 kHz." Our `burst()` ramps the pigpio hardware-PWM frequency back and forth across 20–24 kHz in 250 Hz steps every 20 ms, reproducing the "modulating" character. Modulation also helps prevent habituation — a static tone is easier for an animal to learn to tolerate than a moving one.

### 6. Weatherproofing, Mounting & Dog-Safe Placement

**6.1 Sealing the enclosure.** Front face: F28 horn and PIR dome both bedded in clear neutral-cure silicone (24 h cure before deploying). Bottom face: one 3 mm drain hole (yes — outdoor electronics need a way for condensation to escape; mount the box drain-down and out of direct rain spray). Cable entries: PG7 gland for the 12 V cable (3–6 mm), PG9 for the Pi's USB-C cable (4–8 mm). Always include a **drip loop** — let the cable sag outside the gland so water runs off rather than tracking along the cable into the box.

**6.2 Where the 230 V mains lives. KEEP BOTH ADAPTERS (12 V and USB-C 5 V) INDOORS** and run only DC out through the wall to the box. This is the single strongest safety recommendation: it eliminates all 230 V exposure outside. Outdoor mains is possible (separate sealed IP65 enclosure with its own glands) but is *not* a beginner project — don't do it.

**6.3 Mounting in the garden.** Height 30–50 cm off the ground, aimed roughly horizontally (cat-head level on the path you want to deny). Aim the horn down the cat's entry corridor (along a fence, gap in a hedge). Aim AWAY from where the dogs are; behind the box the effective distances roughly halve.

**6.4 Dog-safety rules.**
- Beam aimed away from dog areas.
- Dogs **≥ 8 m off-axis** or **≥ 15 m on-axis** when armed.
- Quiet hours 22:00–07:00 (default in `catdeter.py`) so it never fires at night when dogs are out.
- Start at reduced volume: `DUTY = 250_000` (25 %) and 12 V rail, not 24 V.
- If the dog shows distress (ears flattening, refusing to enter that area), reduce duty cycle further or reposition.

### 7. Bill of Materials

| # | Part | Elimex product | Qty | Notes |
|---|---|---|---|---|
| 1 | Raspberry Pi 4 (any RAM) | — already owned | 1 | Heart of the project |
| 2 | USB-C 5.1 V / 3 A PSU for Pi | already owned (or buy locally) | 1 | Searching elimex's adapter category did not surface an official Raspberry Pi USB-C PSU — closest BG sources are erelement.com or ardboard.com if needed |
| 3 | microSD 32 GB GOODRAM + adapter, Class 10 | elimex.bg/product/60052 | 1 | Boot media |
| 4 | DFRobot SEN0018 digital PIR module | elimex.bg/product/87576 | 1 | 5 V supply; **OUT 4 V HIGH on motion**; detect angle **110°**, range **7 m** (DFRobot wiki) |
| 5 | IRLZ44N N-channel logic-level MOSFET TO-220 | elimex.bg/product/36316 | 1 | V<sub>DSS</sub> 55 V, I<sub>D</sub> 47 A, V<sub>GS(th)</sub> 1.0–2.0 V (Infineon) |
| 6 | Piezo horn tweeter F28 | elimex.bg/product/78799 | 1 | 93 dB, 3–20 kHz rated, 285 × 110 × 167 mm; radiates usefully into 25–30 kHz |
| 7 | 12 V / 1 A DC adapter (5.5 × 2.1 mm jack) | elimex.bg/product/64509 | 1 | Or 12 V / 1.5 A 5.5 × 2.5 mm — elimex.bg/product/72724 |
| 8 | DC barrel jack panel socket (matching) | elimex category 1086 ("СЪЕДИНИТЕЛИ") | 1 | Mates with the adapter |
| 9 | ABS IP66 enclosure 200 × 120 × 75 mm | elimex.bg/product/68216 | 1 | "Кутия пластмасова ABS 200×120×75 mm IP66" |
| 10 | PG7 cable gland | elimex category 1086 (or local hardware) | 1 | For 12 V cable |
| 11 | PG9 cable gland | as above | 1 | For USB-C cable |
| 12 | Universal perfboard | elimex.bg/category/948 ("ПЕЧАТНИ ПЛАТКИ И ТЕКСТОЛИТ") — e.g. product 24400 "ПЛАТКА ELIMEX" | 1 | Cut to fit |
| 13 | Solderless breadboard 400-tie | elimex.bg/product/76380 (МАКЕТНА ПЛАТКА 400 ГНЕЗДА) | 1 | For prototyping |
| 14 | Resistor 220 Ω, ¼ W | elimex резистори | 1 | R_g (gate drive) |
| 15 | Resistor 10 kΩ, ¼ W | as above | 1 | R_pd (pull-down) |
| 16 | Resistor 33 Ω, ½ W | as above | 1 | R_s (piezo series limiter) |
| 17 | 1N4148 small-signal diode | elimex диоди | 1 | Flyback / clamp |
| 18 | 2-way screw terminal 5 mm pitch | elimex съединители | 2 | Power-in, piezo-out |
| 19 | Dupont jumper wires M-F | elimex hobby section | 1 pack | Pi → breadboard |
| 20 | Hookup wire (silicone, 22 AWG) | elimex.bg/category/1173-kabeli-i-provodnitsi-montazhni | small reel | Internal wiring |
| 21 | Small heatsink + thermal pad for Pi 4 | elimex охладители section | 1 | Pi 4 runs warm under continuous PWM duty |
| 22 | Clear neutral-cure silicone sealant | local hardware store | 1 tube | For sealing horn + PIR through the enclosure |

> **Pricing note:** elimex.bg renders prices client-side in JavaScript, so live лв prices were not present in the static page HTML at the time of writing. Open each product URL in your browser to confirm current prices in лв (BGN, with VAT). All URLs above were validated as live elimex.bg product pages with confirmed titles and (where shown in metadata) specs.

### 8. Troubleshooting & FAQ

**"I can't hear anything."** Expected — it's ultrasonic.
1. Verify with Spectroid (Android) / SpectrumView (iOS) within 50 cm of the horn — a clear peak between 20 and 24 kHz.
2. Multimeter on DC volts across the piezo: idle ≈ 12 V (MOSFET off); during a burst, time-average ≈ 6 V (50 % duty).
3. LED + 1 kΩ test: swap an LED in series with 1 kΩ for the piezo, set PWM to 2 Hz, watch it blink.

**PIR false-triggers.**
- Hot air, sunlight glints, wind-swayed foliage in front of the lens. Aim the PIR at a shady, calm field of view.
- Trim the SEN0018's two onboard potentiometers: SENS (down) reduces sensitivity, TIME sets hold-on time.
- Keep the PIR ≥ 30 cm from the warm Pi and away from sun-warmed walls.

**Nothing happens at all.**
1. `systemctl status pigpiod` — must be active.
2. `journalctl -u catdeter -n 50` — read the service log.
3. Common ground: continuity-beep between Pi pin 6 and the 12 V barrel sleeve.
4. Pin numbering: code uses **BCM**. BCM17 = physical pin 11, BCM18 = physical pin 12. NOT physical pins 17 / 18.
5. With Pi off, measure the gate-to-source resistance — should read the ≈ 10 kΩ pull-down.

**The Pi won't boot or keeps rebooting.** Almost always undervoltage. Use a 5.1 V / 3 A USB-C PSU; check `dmesg | grep -i voltage` for under-voltage messages; re-flash the SD if boot is patchy.

**The MOSFET gets hot.** At 20 kHz into a small capacitive load it should be cool. If hot: raise R_s to 47 Ω, confirm the 220 Ω gate resistor is present, check for accidental shorts.

**The piezo crackles / distorts.** Either rail voltage exceeds the piezo's max (rare at 12 V) or the series resistor is missing.

---

## Recommendations

**Phase 1 — Build at low power and confirm safety for the dogs.**
1. Buy all parts from elimex.bg per §7. Use the 12 V / 1 A adapter (product 64509), not 18 V/24 V.
2. Build on a breadboard first; verify the PIR with `pir_test.py` and the ultrasonic output on Spectroid with `tone_sweep.py`.
3. Install the systemd service with `DUTY = 250_000` (25 % duty, half-volume) and the default 22:00–07:00 quiet hours.
4. Mount in the garden aimed strictly along the cat-entry path, AWAY from the dogs.
5. Watch the dogs for one week. Benchmark: if either dog shows ear-flattening, avoidance of garden areas it formerly used, or unexplained anxiety, **lower** duty cycle to 12 % (`125_000`) or reposition further from their habitual areas.

**Phase 2 — Tune for cat efficacy.**
6. After one week, if the dogs are unaffected, raise duty cycle to 50 % (`500_000`). Log how often the SQLite `events` table shows fires per night; benchmark: a healthy install should show 0–5 events/day after week 2 (cats learn to avoid the area).
7. If cat visits persist after two weeks at 50 % duty / 12 V, swap to the 12 V / 1.5 A adapter (product 72724) — same voltage, more current headroom — and then consider stepping up to an 18 V adapter from elimex's category 956.

**Phase 3 — Upgrades (optional).**
8. Add a USB or Pi Camera and modify `catdeter.py` to record a 10-s clip on each fire — gives you evidence of which cats are being deterred.
9. Add a small Flask dashboard on the Pi (`pip install flask`) that reads the SQLite DB and shows daily / hourly fire counts.
10. v2 PCB: anti-phase H-bridge for +6 dB SPL (two IRLZ44Ns driven from BCM18 + BCM19), and an LC resonance boost on the piezo for another +6 dB.

**Recommendation thresholds that would change the design choice.**
- If SPL measurement at 1 m falls below ~88 dB → step rail to 18 V before attempting the H-bridge.
- If dogs show clear discomfort → drop rail to 9 V (elimex stocks 9 V adapters too) and shorten BURST_SECONDS to 2 s.
- If false-triggers exceed ~30/day → replace the PIR with a narrower-FOV unit; or aim it through a small cardboard mask to restrict its arc.

---

## Caveats

- **Live elimex.bg prices are not in this guide.** The site is a Next.js app that renders prices via JavaScript after page load; a static fetch of any product URL returns only the metadata (title, image, specs in og:description). All URLs cited were confirmed as live, valid elimex product pages with matching titles, but actual лв prices must be read off the live site in your browser before checkout.
- **F28 impedance** is not stated on the elimex page; other Bulgarian retailers list nominally-equivalent F28-class piezo horns at 4–8 Ω marketing ratings, but piezos are dominantly capacitive (~30–80 nF) and the "ohm" rating is largely cosmetic at ultrasonic frequencies.
- **Pi 4 USB-C PSU on elimex:** elimex's adapter category did not surface a Raspberry-Pi-branded 5.1 V / 3 A USB-C supply during this research; assume you must source this elsewhere or use the official Pi PSU you already own. The 12 V adapter for the emitter stage IS on elimex.
- **Single-MOSFET drive is single-ended.** Maximum SPL is bounded by the rail voltage. If your real-world measurement falls short of 96 dB / 1 m, raise the rail to 18 V (then re-measure) before adding the anti-phase / H-bridge upgrade.
- **SEN0018 detection geometry differs from earlier project notes.** DFRobot's official wiki specifies **detect angle 110°** and **detect range 7 m** (not 120° / 6 m as sometimes cited in third-party listings). The OUT pin is "Output level(HIGH): 4V" — directly compatible with a Pi 3.3 V input *as a HIGH* (the Pi treats > 1.8 V as logic-1) but technically 4 V exceeds the 3.3 V GPIO absolute-max-input spec. For a clean implementation, add a simple voltage divider (e.g. 10 kΩ from OUT to GPIO17, 22 kΩ from GPIO17 to GND) to drop the 4 V to ~2.7 V. In practice the SEN0018's output current is limited and many builders connect it directly without damage, but the divider is the formally-correct beginner-safe option.
- **Dog tolerance is individual.** Every dog is different — the placement and quiet-hours guidance is conservative but you must observe your own dogs closely for the first week. If you have any breed prone to anxiety, start at 12 % duty cycle.
- **The peer-reviewed Catwatch© SPL figures** (96 dB / 1 m, 56 dB / 7 m, 44 dB / 13 m) are from the original commercial unit — your build's measured numbers will vary somewhat with horn placement, enclosure, and rail voltage. Measure with a smartphone SPL meter at 1 m as a sanity check; if the reading is wildly off, the most likely culprits are (a) a missing common ground, (b) an IRFZ44N substituted for the IRLZ44N, or (c) the piezo wired with no series resistor and oscillating chaotically.
