#!/usr/bin/env python3
"""Play a gated tone at each frequency given on the command line.

Gated at GATE_HZ so a recorder elsewhere can pull it out of a noisy room with
a lock-in: nothing in an ordinary environment flickers at exactly 5 Hz inside
a 240 Hz-wide slice of the ultrasonic band.

Usage: sudo python3 freq_probe.py 21000 22000
       sudo python3 freq_probe.py            # plays nothing, a silent control
"""
import atexit
import pathlib
import signal
import sys
import time

CHIP = pathlib.Path("/sys/class/pwm/pwmchip0")
CH = CHIP / "pwm0"
if not CH.exists():
    (CHIP / "export").write_text("0")
    time.sleep(0.3)


def silence():
    try:
        (CH / "enable").write_text("0")
        (CH / "duty_cycle").write_text("0")
    except OSError:
        pass


atexit.register(silence)
for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    signal.signal(s, lambda *_: sys.exit(0))

LEAD_IN_S, TONE_S, GAP_S, GATE_HZ = 4.0, 4.0, 1.5, 5.0
SLOTS = [5_000, 19_000, 20_000, 21_000, 22_000, 23_000]
play = {int(a) for a in sys.argv[1:]}
half = 1.0 / (2 * GATE_HZ)

print(f"lead-in {LEAD_IN_S}s", flush=True)
time.sleep(LEAD_IN_S)
# Every slot takes the same wall-clock time whether or not it sounds, so the
# recording's structure gives nothing away about which were chosen.
for f in SLOTS:
    if f in play:
        p = int(1_000_000_000 / f)
        (CH / "duty_cycle").write_text("0")
        (CH / "period").write_text(str(p))
        (CH / "duty_cycle").write_text(str(p // 2))
        end = time.time() + TONE_S
        while time.time() < end:
            (CH / "enable").write_text("1")
            time.sleep(half)
            (CH / "enable").write_text("0")
            time.sleep(half)
    else:
        time.sleep(TONE_S)
    time.sleep(GAP_S)
silence()
print("done", flush=True)
