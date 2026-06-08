#!/usr/bin/env python3
"""Sweep 20 kHz -> 24 kHz on GPIO18 (PWM0) using pigpio hardware PWM.

Use a phone spectrum analyser (Spectroid on Android, SpectrumView on iOS)
within ~50 cm of the horn to confirm a clear peak between 20 and 24 kHz.
You will not hear anything - that is the entire point. See docs/BUILD.md 4.2.
"""
import time

import pigpio

PWM_GPIO = 18          # BCM18 = pin 12 = hardware PWM0
F_LOW_HZ = 20_000
F_HIGH_HZ = 24_000
SWEEP_STEP = 250       # Hz per tick
TICK_S = 0.020         # 20 ms per step
DUTY = 500_000         # 50 %  (range 0..1_000_000)

pi = pigpio.pi()
if not pi.connected:
    raise SystemExit("pigpio daemon not running. sudo systemctl start pigpiod")

try:
    print("Sweeping. Use Spectroid on your phone to verify 20-24 kHz peaks.")
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
