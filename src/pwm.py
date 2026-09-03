#!/usr/bin/env python3
"""Kernel hardware PWM through sysfs.

This project used to drive GPIO18 with pigpio. pigpio has been dropped from
Debian trixie, which is the base of current Raspberry Pi OS. The client pieces
(`python3-pigpio`, `pigpio-tools`, `libpigpiod-if2-1t64`) are all still
packaged, but the `pigpiod` daemon they talk to is not, so `pigpio.pi()`
connects to nothing and `pi.connected` is False. Nothing warns you; the import
succeeds and the program simply never makes a sound.

The SoC's PWM peripheral is reachable directly once `dtoverlay=pwm-2chan` is
in `/boot/firmware/config.txt`, which maps PWM0 to GPIO18 (physical pin 12).
That is the same hardware pigpio was poking at, reached through the kernel
instead of through /dev/mem. See docs/BUILD.md section 4.

Duty is expressed 0..1_000_000, matching the range TOMCAT_DUTY already used,
so existing .env files carry over unchanged.
"""
import pathlib
import time

DUTY_RANGE = 1_000_000


class PWMUnavailable(RuntimeError):
    """The sysfs PWM interface is not present, usually a missing overlay."""


class HardwarePWM:
    """One channel of the SoC's PWM peripheral, via /sys/class/pwm.

    Nothing touches sysfs until open() is called, so this module imports
    cleanly on a laptop.
    """

    def __init__(self, chip=0, channel=0):
        self.chipdir = pathlib.Path(f"/sys/class/pwm/pwmchip{chip}")
        self.channel = channel
        self.path = self.chipdir / f"pwm{channel}"
        # What we last wrote, so set() can skip writes that change nothing and
        # avoid the duty-zeroing dance unless the period is actually shrinking
        # past the loaded duty.
        self._period = 0
        self._duty = 0

    def open(self):
        if not self.chipdir.exists():
            raise PWMUnavailable(
                f"{self.chipdir} not found. Add 'dtoverlay=pwm-2chan' to "
                "/boot/firmware/config.txt and reboot."
            )
        if not self.path.exists():
            (self.chipdir / "export").write_text(str(self.channel))
            # udev has to create and chmod the new directory; it is quick but
            # not instant, and writing too early fails with ENOENT/EACCES.
            for _ in range(50):
                if (self.path / "enable").exists():
                    break
                time.sleep(0.02)
            else:
                raise PWMUnavailable(f"{self.path} did not appear after export")
        self.off()
        return self

    def _write(self, name, value):
        (self.path / name).write_text(str(value))

    def set(self, hz, duty):
        """Set frequency in Hz at the given duty (0..DUTY_RANGE).

        The kernel rejects a duty_cycle larger than period with EINVAL, which
        is why the naive version zeroes the duty before every period change.
        That is correct and, done two hundred times a second, audible: each
        momentary zero is a step discontinuity, and a step contains energy at
        every frequency including the ones humans hear. So the zeroing now
        happens only when it is actually needed, which is when the new period
        would fall below the duty currently loaded.
        """
        period = int(1_000_000_000 / hz)
        want = period * duty // DUTY_RANGE
        if period < self._duty:
            self._write("duty_cycle", 0)
            self._duty = 0
        if period != self._period:
            self._write("period", period)
            self._period = period
        if want != self._duty:
            self._write("duty_cycle", want)
            self._duty = want

    def on(self):
        self._write("enable", 1)

    def silence(self):
        """Stop driving the pin, but leave period and duty alone.

        This is the gating primitive: one file write instead of two, and it
        keeps the frequency loaded so the next on() resumes instantly. Used
        thousands of times an hour in aggressive mode, so the difference is
        worth having.
        """
        try:
            self._write("enable", 0)
        except OSError:
            pass

    def off(self):
        """Fully idle the output. Safe to call from a signal handler or twice.

        Unlike silence(), this also zeroes the duty cycle, which is what you
        want on the way out rather than between bursts.
        """
        try:
            self._write("enable", 0)
            self._write("duty_cycle", 0)
            self._duty = 0
        except OSError:
            pass
