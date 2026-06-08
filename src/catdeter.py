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
import pigpio
import time
import sqlite3
import datetime
import signal
import sys
from pathlib import Path

# -------- CONFIG (edit me) --------
PIR_GPIO = 17
PWM_GPIO = 18
F_LOW_HZ = 20_000
F_HIGH_HZ = 24_000
SWEEP_STEP = 250
SWEEP_TICK_S = 0.020
DUTY = 500_000          # 50 % ; use 250_000 for half-volume test
BURST_SECONDS = 4.0
COOLDOWN_S = 8.0
QUIET_START_H = 22      # 22:00
QUIET_END_H = 7         # 07:00
DB_PATH = Path.home() / "catdeter.sqlite3"
# ----------------------------------


def in_quiet_hours(now=None):
    h = (now or datetime.datetime.now()).hour
    if QUIET_START_H == QUIET_END_H:
        return False
    if QUIET_START_H < QUIET_END_H:
        return QUIET_START_H <= h < QUIET_END_H
    return h >= QUIET_START_H or h < QUIET_END_H


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
