#!/usr/bin/env python3
"""Drive the ultrasonic horn on GPIO18 (PWM0) via the kernel's hardware PWM.

Two modes, selected with TOMCAT_MODE:

  sweep       The original: a smooth 20 -> 24 kHz triangle, 250 Hz per 20 ms.
  aggressive  The default. Randomised bursts of randomly jumping frequency,
              amplitude-gated. Considerably harder to ignore, and considerably
              harder to get used to.

Why aggressive is shaped the way it is:

* **The band moved down to 19-23 kHz.** This is not a guess. In the blind
  acoustic trials (docs/MEASUREMENTS.md) 19 kHz scored the strongest detection
  of any frequency tested, 18.0 against a silent baseline of 4.7, while 22 kHz
  managed 12.9 and 23 kHz was undetectable. The horn simply radiates better
  lower down, so the sweep now spends its time where the sound actually comes
  out. It stays above the hearing of essentially every adult.

* **Frequency jumps rather than a smooth ramp.** A slow glide is a texture an
  animal settles into. A tone that lands somewhere unpredictable every few tens
  of milliseconds keeps triggering the startle response instead.

* **Randomised bursts with randomised gaps.** Habituation is driven by
  predictability far more than by loudness. A constant tone becomes furniture
  within days; a stimulus that cannot be anticipated does not. This is the
  single biggest change here and it costs nothing.

* **Amplitude gating at 7-22 Hz inside each burst.** Roughness. A gated tone is
  perceptually harsher than a steady one at identical power, and the gating
  sidebands sit within a few tens of Hz of the carrier, so it all stays
  ultrasonic.

Requires `dtoverlay=pwm-2chan` in /boot/firmware/config.txt, and root.
"""
import atexit
import math
import os
import random
import signal
import sys
import time

from pwm import HardwarePWM, PWMUnavailable

MODE = os.environ.get("TOMCAT_MODE", "aggressive").strip().lower()
PWM_CHIP = int(os.environ.get("TOMCAT_PWM_CHIP", 0))
PWM_CHANNEL = int(os.environ.get("TOMCAT_PWM_CHANNEL", 0))
DUTY = int(os.environ.get("TOMCAT_DUTY", 500_000))     # 50 % of 1_000_000

# Sweep mode keeps the historical band and step.
F_LOW_HZ = int(os.environ.get("TOMCAT_F_LOW_HZ", 20_000))
F_HIGH_HZ = int(os.environ.get("TOMCAT_F_HIGH_HZ", 24_000))
SWEEP_STEP = int(os.environ.get("TOMCAT_SWEEP_STEP", 250))
TICK_S = float(os.environ.get("TOMCAT_SWEEP_TICK_S", 0.020))

# Aggressive mode. Band sits lower deliberately; see the module docstring.
AGG_LOW_HZ = int(os.environ.get("TOMCAT_AGG_LOW_HZ", 19_000))
AGG_HIGH_HZ = int(os.environ.get("TOMCAT_AGG_HIGH_HZ", 23_000))
AGG_STEP_HZ = int(os.environ.get("TOMCAT_AGG_STEP_HZ", 250))
# Prowl mode. Every one of these is a rate rather than a switch, on purpose.
PROWL_TICK_S = float(os.environ.get("TOMCAT_PROWL_TICK_S", 0.005))
PROWL_RATE_MIN = float(os.environ.get("TOMCAT_PROWL_RATE_MIN", 6_000))
PROWL_RATE_MAX = float(os.environ.get("TOMCAT_PROWL_RATE_MAX", 25_000))
PROWL_AM_MIN_HZ = float(os.environ.get("TOMCAT_PROWL_AM_MIN_HZ", 3.0))
PROWL_AM_MAX_HZ = float(os.environ.get("TOMCAT_PROWL_AM_MAX_HZ", 11.0))
PROWL_FLOOR = float(os.environ.get("TOMCAT_PROWL_FLOOR", 0.35))
PROWL_DRIFT_S = (float(os.environ.get("TOMCAT_PROWL_DRIFT_MIN_S", 1.5)),
                 float(os.environ.get("TOMCAT_PROWL_DRIFT_MAX_S", 6.0)))

AGG_JUMP_MIN_S = float(os.environ.get("TOMCAT_AGG_JUMP_MIN_S", 0.015))
AGG_JUMP_MAX_S = float(os.environ.get("TOMCAT_AGG_JUMP_MAX_S", 0.045))
AGG_BURST_MIN_S = float(os.environ.get("TOMCAT_AGG_BURST_MIN_S", 2.0))
AGG_BURST_MAX_S = float(os.environ.get("TOMCAT_AGG_BURST_MAX_S", 7.0))
AGG_GAP_MIN_S = float(os.environ.get("TOMCAT_AGG_GAP_MIN_S", 0.08))
AGG_GAP_MAX_S = float(os.environ.get("TOMCAT_AGG_GAP_MAX_S", 0.45))
AGG_GATE_MIN_HZ = float(os.environ.get("TOMCAT_AGG_GATE_MIN_HZ", 7))
AGG_GATE_MAX_HZ = float(os.environ.get("TOMCAT_AGG_GATE_MAX_HZ", 22))
# Fraction of each gate cycle spent driving. A symmetric 50/50 gate sounds
# rough but throws away half the energy; skewing it hard keeps enough roughness
# to stop the tone reading as a steady drone while leaving the horn sounding
# essentially all the time. Together with the very short gaps below this puts
# on-time near 90 % of wall clock: a cat crossing the garden meets the sound
# within a fraction of a second of arriving, whichever moment it picks.
AGG_GATE_ON = float(os.environ.get("TOMCAT_AGG_GATE_ON", 0.92))
# Milliseconds spent ramping the amplitude in and out of each gate cycle.
# This is what keeps the thing inaudible. Switching enable hard on and off puts
# a step discontinuity at every edge, and a step contains energy at every
# frequency including the ones humans hear, so a hard gate on a 21 kHz carrier
# is heard as clicking. Ramping the duty cycle over a few milliseconds instead
# removes the discontinuity, and with it the audible part, while a cat still
# gets the same amplitude rhythm.
AGG_RAMP_MS = float(os.environ.get("TOMCAT_AGG_RAMP_MS", 4.0))
AGG_RAMP_STEPS = int(os.environ.get("TOMCAT_AGG_RAMP_STEPS", 8))
# Largest single frequency jump. Unbounded jumps across the whole band are
# themselves audible clicks; keeping each step small keeps the movement without
# the broadband snap.
AGG_MAX_JUMP_HZ = int(os.environ.get("TOMCAT_AGG_MAX_JUMP_HZ", 750))

try:
    pwm = HardwarePWM(PWM_CHIP, PWM_CHANNEL).open()
except PWMUnavailable as exc:
    raise SystemExit(str(exc)) from exc
except PermissionError as exc:
    raise SystemExit("sysfs PWM needs root: try sudo") from exc

# Both paths matter. atexit covers a clean return and SystemExit; the signal
# handlers cover SIGTERM from `systemctl stop`, which otherwise kills the
# process and leaves the PWM peripheral driving the pin on its own.
atexit.register(pwm.off)
_stop = False


def _quit(*_):
    global _stop
    _stop = True
    sys.exit(0)


for _sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    signal.signal(_sig, _quit)


def nap(seconds):
    """Sleep in slices so a stop lands promptly rather than a burst later."""
    end = time.time() + seconds
    while not _stop and time.time() < end:
        time.sleep(min(0.05, max(0.0, end - time.time())))


def run_sweep():
    print(f"sweeping {F_LOW_HZ // 1000}-{F_HIGH_HZ // 1000} kHz on GPIO18 at "
          f"{DUTY / 10_000:g}% duty", flush=True)
    pwm.set(F_LOW_HZ, DUTY)
    pwm.on()
    f, direction = F_LOW_HZ, +SWEEP_STEP
    while not _stop:
        pwm.set(f, DUTY)
        time.sleep(TICK_S)
        f += direction
        if f >= F_HIGH_HZ:
            direction = -SWEEP_STEP
        if f <= F_LOW_HZ:
            direction = +SWEEP_STEP


def run_prowl():
    """Aggressive, but with no discontinuity anywhere in the waveform.

    The first attempt at an aggressive mode gated the output hard on and off
    and jumped the frequency across the band. Both were plainly audible, and
    for the same reason: a step change contains energy at every frequency, so a
    sharp edge on a 21 kHz carrier is heard as a click regardless of how far
    above hearing the carrier itself sits.

    Everything here moves continuously instead. The frequency glides, and the
    speed and direction of that glide themselves drift. The amplitude breathes
    between a floor and full, sinusoidally, at a rate that also drifts. Nothing
    ever switches, so there is nothing to hear. An animal still gets a tone
    that will not hold still and a pulsing it cannot settle into, which is what
    resists habituation; the smoothness costs only the startle of the clicks.

    Every update is a small step: at 5 ms per update and a sweep rate capped
    near 25 kHz/s, no single frequency change exceeds ~125 Hz, which is half
    what the old inaudible triangle did per step.
    """
    rng = random.SystemRandom()
    mid = (AGG_LOW_HZ + AGG_HIGH_HZ) / 2.0
    freq = mid
    rate = rng.uniform(PROWL_RATE_MIN, PROWL_RATE_MAX)   # Hz per second
    direction = rng.choice((-1.0, 1.0))
    am_hz = rng.uniform(PROWL_AM_MIN_HZ, PROWL_AM_MAX_HZ)
    phase = 0.0
    dt = PROWL_TICK_S
    next_drift = time.time() + rng.uniform(*PROWL_DRIFT_S)

    print(f"prowl: {AGG_LOW_HZ // 1000}-{AGG_HIGH_HZ // 1000} kHz gliding at "
          f"{PROWL_RATE_MIN / 1000:g}-{PROWL_RATE_MAX / 1000:g} kHz/s, "
          f"amplitude breathing {PROWL_AM_MIN_HZ:g}-{PROWL_AM_MAX_HZ:g} Hz "
          f"between {PROWL_FLOOR:.0%} and full, "
          f"{DUTY / 10_000:g}% duty, no hard edges", flush=True)

    pwm.set(int(freq), DUTY)
    pwm.on()
    while not _stop:
        now = time.time()
        # Occasionally retarget the glide rate and the breathing rate. Both are
        # eased toward the new value rather than snapped to it.
        if now >= next_drift:
            rate = rng.uniform(PROWL_RATE_MIN, PROWL_RATE_MAX)
            am_hz = rng.uniform(PROWL_AM_MIN_HZ, PROWL_AM_MAX_HZ)
            if rng.random() < 0.35:
                direction = -direction
            next_drift = now + rng.uniform(*PROWL_DRIFT_S)

        freq += direction * rate * dt
        if freq >= AGG_HIGH_HZ:
            freq, direction = float(AGG_HIGH_HZ), -1.0
        elif freq <= AGG_LOW_HZ:
            freq, direction = float(AGG_LOW_HZ), 1.0

        phase = (phase + 2 * math.pi * am_hz * dt) % (2 * math.pi)
        # cos runs 1 -> -1, mapped onto floor -> full. Never reaches zero, so
        # the output never actually stops and there is no gate edge.
        env = PROWL_FLOOR + (1.0 - PROWL_FLOOR) * (0.5 + 0.5 * math.cos(phase))
        pwm.set(int(freq), int(DUTY * env))
        time.sleep(dt)


if MODE == "sweep":
    run_sweep()
else:
    run_prowl()
