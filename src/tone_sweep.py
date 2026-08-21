#!/usr/bin/env python3
"""Sweep 20 kHz -> 24 kHz on GPIO18 (PWM0) using the kernel's hardware PWM.

Use a phone spectrum analyser (Spectroid on Android, SpectrumView on iOS)
within ~50 cm of the horn to confirm a clear peak between 20 and 24 kHz.
You will not hear anything - that is the entire point. See docs/BUILD.md 4.2.

Requires `dtoverlay=pwm-2chan` in /boot/firmware/config.txt, and root.
Run: sudo python3 src/tone_sweep.py
"""
import atexit
import os
import signal
import sys
import time

from pwm import HardwarePWM, PWMUnavailable

PWM_CHIP = int(os.environ.get("TOMCAT_PWM_CHIP", 0))
PWM_CHANNEL = int(os.environ.get("TOMCAT_PWM_CHANNEL", 0))
F_LOW_HZ = int(os.environ.get("TOMCAT_F_LOW_HZ", 20_000))
F_HIGH_HZ = int(os.environ.get("TOMCAT_F_HIGH_HZ", 24_000))
SWEEP_STEP = int(os.environ.get("TOMCAT_SWEEP_STEP", 250))
TICK_S = float(os.environ.get("TOMCAT_SWEEP_TICK_S", 0.020))
DUTY = int(os.environ.get("TOMCAT_DUTY", 500_000))     # 50 % of 1_000_000

try:
    pwm = HardwarePWM(PWM_CHIP, PWM_CHANNEL).open()
except PWMUnavailable as exc:
    raise SystemExit(str(exc)) from exc
except PermissionError as exc:
    raise SystemExit("sysfs PWM needs root: try sudo") from exc

# Both paths matter. atexit covers a clean return and SystemExit; the signal
# handlers cover SIGTERM from `kill`, which otherwise kills the process and
# leaves the PWM peripheral happily driving the pin on its own.
atexit.register(pwm.off)
for _sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    signal.signal(_sig, lambda *_: sys.exit(0))

print(f"Sweeping {F_LOW_HZ // 1000}-{F_HIGH_HZ // 1000} kHz on GPIO18 at "
      f"{DUTY / 10_000:g}% duty. Verify with a phone spectrum analyser.",
      flush=True)

pwm.set(F_LOW_HZ, DUTY)
pwm.on()

f = F_LOW_HZ
direction = +SWEEP_STEP
while True:
    pwm.set(f, DUTY)
    time.sleep(TICK_S)
    f += direction
    if f >= F_HIGH_HZ:
        direction = -SWEEP_STEP
    if f <= F_LOW_HZ:
        direction = +SWEEP_STEP
