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


def run_aggressive():
    rng = random.SystemRandom()
    steps = list(range(AGG_LOW_HZ, AGG_HIGH_HZ + 1, AGG_STEP_HZ))
    print(f"aggressive: {AGG_LOW_HZ // 1000}-{AGG_HIGH_HZ // 1000} kHz, "
          f"random jumps every {AGG_JUMP_MIN_S * 1000:.0f}-{AGG_JUMP_MAX_S * 1000:.0f} ms, "
          f"bursts {AGG_BURST_MIN_S}-{AGG_BURST_MAX_S}s, "
          f"gaps {AGG_GAP_MIN_S}-{AGG_GAP_MAX_S}s, "
          f"gated {AGG_GATE_MIN_HZ:.0f}-{AGG_GATE_MAX_HZ:.0f} Hz, "
          f"{DUTY / 10_000:g}% duty", flush=True)
    while not _stop:
        # One burst: a fresh gate rate, and a fresh length, every time. Nothing
        # about the next burst can be predicted from the last one.
        burst_end = time.time() + rng.uniform(AGG_BURST_MIN_S, AGG_BURST_MAX_S)
        period = 1.0 / rng.uniform(AGG_GATE_MIN_HZ, AGG_GATE_MAX_HZ)
        on_t, off_t = period * AGG_GATE_ON, period * (1.0 - AGG_GATE_ON)
        while not _stop and time.time() < burst_end:
            # Jump frequency several times within a single gate-on window, so
            # the tone is moving even while the amplitude is steady. The two
            # rhythms are unrelated on purpose: nothing here forms a pattern an
            # animal can learn to anticipate.
            gate_end = time.time() + on_t
            while not _stop and time.time() < gate_end:
                pwm.set(rng.choice(steps), DUTY)
                pwm.on()
                time.sleep(min(rng.uniform(AGG_JUMP_MIN_S, AGG_JUMP_MAX_S),
                               max(0.0, gate_end - time.time())))
            pwm.silence()
            time.sleep(off_t)
        pwm.silence()
        nap(rng.uniform(AGG_GAP_MIN_S, AGG_GAP_MAX_S))


if MODE == "sweep":
    run_sweep()
else:
    run_aggressive()
