#!/usr/bin/env python3
"""
TomCat - a CATWatch-style PIR-triggered ultrasonic cat deterrent.

- Detects motion on BCM17 (DFRobot SEN0018 PIR).
- Bursts a 20 kHz <-> 24 kHz frequency sweep on BCM18 (hardware PWM0) via an
  IRLZ44N logic-level MOSFET switching a piezo horn against a 12 V rail.
- Honours quiet hours so it never fires at night while the dogs are out.
- Cool-down between bursts to avoid habituation and excess.
- Logs every detection to a local SQLite DB.

See docs/BUILD.md for the full build, wiring and dog-safety guidance.
"""
import datetime
import os
import signal
import sqlite3
import sys
import time
from pathlib import Path

import pigpio


# -------- CONFIG --------
# Every setting can be overridden by an environment variable (TOMCAT_*), so the
# systemd unit / .env file carries the tuning and the source stays untouched.
# The literals below are the defaults. See .env.example.
def _env_int(name, default):
    return int(os.environ.get(name, default))


def _env_float(name, default):
    return float(os.environ.get(name, default))


PIR_GPIO = _env_int("TOMCAT_PIR_GPIO", 17)
PWM_GPIO = _env_int("TOMCAT_PWM_GPIO", 18)
F_LOW_HZ = _env_int("TOMCAT_F_LOW_HZ", 20_000)
F_HIGH_HZ = _env_int("TOMCAT_F_HIGH_HZ", 24_000)
SWEEP_STEP = _env_int("TOMCAT_SWEEP_STEP", 250)
SWEEP_TICK_S = _env_float("TOMCAT_SWEEP_TICK_S", 0.020)
DUTY = _env_int("TOMCAT_DUTY", 500_000)        # 50 % ; use 250_000 for half-volume
BURST_SECONDS = _env_float("TOMCAT_BURST_SECONDS", 4.0)
COOLDOWN_S = _env_float("TOMCAT_COOLDOWN_S", 8.0)
QUIET_START_H = _env_int("TOMCAT_QUIET_START_H", 22)   # 22:00
QUIET_END_H = _env_int("TOMCAT_QUIET_END_H", 7)        # 07:00
DB_PATH = Path(os.environ.get("TOMCAT_DB_PATH", Path.home() / "catdeter.sqlite3"))
# ------------------------


def in_quiet_hours(now=None, start_h=QUIET_START_H, end_h=QUIET_END_H):
    """True if `now` falls inside the quiet window [start_h, end_h).

    Handles a window that wraps past midnight (e.g. 22 -> 7). If start == end
    the window is empty (quiet hours disabled).
    """
    h = (now or datetime.datetime.now()).hour
    if start_h == end_h:
        return False
    if start_h < end_h:
        return start_h <= h < end_h
    return h >= start_h or h < end_h


def open_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("""CREATE TABLE IF NOT EXISTS events (
                    ts TEXT NOT NULL,
                    fired INTEGER NOT NULL,
                    note TEXT)""")
    db.commit()
    return db


def log_event(db, fired, note=""):
    db.execute("INSERT INTO events(ts,fired,note) VALUES(?,?,?)",
               (datetime.datetime.now().isoformat(timespec="seconds"),
                int(fired), note))
    db.commit()


def burst(pi):
    end_t = time.time() + BURST_SECONDS
    f = F_LOW_HZ
    direction = +SWEEP_STEP
    while time.time() < end_t:
        pi.hardware_PWM(PWM_GPIO, f, DUTY)
        time.sleep(SWEEP_TICK_S)
        f += direction
        if f >= F_HIGH_HZ:
            direction = -SWEEP_STEP
        if f <= F_LOW_HZ:
            direction = +SWEEP_STEP
    pi.hardware_PWM(PWM_GPIO, 0, 0)


def main():
    pi = pigpio.pi()
    if not pi.connected:
        sys.exit("pigpio not running: sudo systemctl start pigpiod")
    pi.set_mode(PIR_GPIO, pigpio.INPUT)
    pi.set_pull_up_down(PIR_GPIO, pigpio.PUD_DOWN)
    pi.hardware_PWM(PWM_GPIO, 0, 0)
    db = open_db()

    def clean(*_):
        pi.hardware_PWM(PWM_GPIO, 0, 0)
        pi.stop()
        db.close()
        sys.exit(0)
    signal.signal(signal.SIGTERM, clean)
    signal.signal(signal.SIGINT, clean)

    print("Warming up PIR for 30 s ...")
    time.sleep(30)
    print("Armed.")
    last_fire = 0.0

    while True:
        if pi.read(PIR_GPIO) == 1:
            now = time.time()
            quiet = in_quiet_hours()
            if quiet:
                log_event(db, fired=False, note="quiet-hours")
            elif (now - last_fire) < COOLDOWN_S:
                log_event(db, fired=False, note="cooldown")
            else:
                log_event(db, fired=True)
                burst(pi)
                last_fire = time.time()
        time.sleep(0.05)


if __name__ == "__main__":
    main()
