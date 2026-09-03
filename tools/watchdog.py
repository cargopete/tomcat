#!/usr/bin/env python3
"""Spike: keeps watch on the emitter, records what he sees, and barks when it stops.

The emitter has a known fault: it drops out intermittently. During acoustic
measurement 3 of 11 trials lost the horn entirely at a frequency it radiates
strongly, and the suspect is a series resistor bridged with jumper leads rather
than seated in the board. That fault is silent by construction, because the
output is ultrasonic. Nobody can hear it stop.

So this samples two independent things every TICK seconds:

  * whether systemd still considers the unit active, and
  * whether the PWM peripheral is actually driving the pin.

The second is the one that matters. A unit can sit there reporting `active`
while `enable` reads 0 and the garden is silent, which is precisely the failure
we cannot hear. Every sample goes to SQLite so a run can be picked apart
afterwards; transitions go to Discord so you find out at the time.

Configuration is by TOMCAT_* environment variables, as everywhere else here.
The webhook is a credential: put it in .env, which is gitignored, and never in
the repository.
"""
import datetime
import json
import os
import signal
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UNIT = os.environ.get("TOMCAT_WATCH_UNIT", "tomcat-tone")
TICK_S = float(os.environ.get("TOMCAT_WATCH_TICK_S", 30))
DB_PATH = Path(os.environ.get("TOMCAT_HEALTH_DB", Path.home() / "tomcat-health.sqlite3"))
WEBHOOK = os.environ.get("TOMCAT_DISCORD_WEBHOOK", "").strip()
# Discord fetches this per-message, so it has to be publicly reachable. The repo
# is public and the portrait lives in it, which is why this is a raw URL rather
# than an upload.
AVATAR = os.environ.get(
    "TOMCAT_DISCORD_AVATAR",
    "https://raw.githubusercontent.com/cargopete/tomcat/main/panel/static/spike.png",
)
PWM_CHIP = os.environ.get("TOMCAT_PWM_CHIP", "0")
PWM_CHANNEL = os.environ.get("TOMCAT_PWM_CHANNEL", "0")

PWM = Path(f"/sys/class/pwm/pwmchip{PWM_CHIP}/pwm{PWM_CHANNEL}")

# Discord embed colours, borrowed from the oxidation palette the panel uses so
# a notification and the panel agree about what green means.
VERDIGRIS = 0x5F9E7D
EMBER = 0xE8922A
RUST = 0xE86951
BRASS = 0xC9A227


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def read(path, cast=str, default=None):
    try:
        return cast(path.read_text().strip())
    except (OSError, ValueError):
        return default


def run(*args):
    """A tiny shell-out. Returns stripped stdout, or '' if the call failed."""
    import subprocess
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def sample():
    """One reading of everything worth knowing."""
    period = read(PWM / "period", int)
    return {
        "ts": now(),
        "unit_active": run("systemctl", "is-active", UNIT) == "active",
        # None, not 0. An unexported channel is absent, not silent, and the two
        # want telling apart when reading the log back.
        "pwm_enable": read(PWM / "enable", int),
        "pwm_hz": (1_000_000_000 // period) if period else None,
        "soc_temp": _temp(),
        "throttled": run("vcgencmd", "get_throttled").replace("throttled=", "") or None,
        "uptime_s": int(float(Path("/proc/uptime").read_text().split()[0])),
    }


def _temp():
    raw = run("vcgencmd", "measure_temp")           # temp=47.2'C
    try:
        return float(raw.split("=")[1].split("'")[0])
    except (IndexError, ValueError):
        return None


def verdict(s):
    """What state the emitter is in, in the machine's own words.

    `fault` is the interesting one: systemd is content, and the horn is silent.
    """
    if not s["unit_active"]:
        return "silent"
    if s["pwm_enable"] == 1:
        return "live"
    return "fault"


def open_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS health (
            ts TEXT NOT NULL,
            state TEXT NOT NULL,
            unit_active INTEGER NOT NULL,
            pwm_enable INTEGER,
            pwm_hz INTEGER,
            soc_temp REAL,
            throttled TEXT,
            uptime_s INTEGER);
        CREATE INDEX IF NOT EXISTS health_ts ON health(ts);
        CREATE TABLE IF NOT EXISTS events (
            ts TEXT NOT NULL,
            kind TEXT NOT NULL,
            detail TEXT);
        CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
    """)
    db.commit()
    return db


def notify(text, colour, fields=None, attempts=3):
    """Post to Discord. Never raises: a watchdog that dies of a failed HTTP
    call is worse than useless, so a failure is recorded and swallowed.

    Retries, because the single most important message this sends is the one
    most likely to fail. The reboot notice fires seconds after boot, when
    systemd considers the network online but wlan0 has not associated and DNS
    is not answering yet, so it dies with `[Errno -3] Temporary failure in name
    resolution`. That happened twice on 3 September and both times the message
    about a power failure was the message lost to the power failure.
    """
    if not WEBHOOK:
        return "no-webhook"
    payload = {
        "username": "Spike the Bulldog",
        "avatar_url": AVATAR,
        "embeds": [{
            "title": text,
            "color": colour,
            "timestamp": datetime.datetime.now().astimezone().isoformat(),
            "fields": fields or [],
        }],
    }
    req = urllib.request.Request(
        WEBHOOK,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "tomcat-watchdog"},
    )
    last = None
    for attempt in range(attempts):
        if attempt:
            # 5s, 15s, 45s ... capped. Enough to outlast Wi-Fi association and
            # the first DNS answers without stalling the sampling loop for long.
            time.sleep(min(5 * 3 ** (attempt - 1), 60))
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                if attempt:
                    return f"ok {r.status} after {attempt + 1} tries"
                return f"ok {r.status}"
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            last = e
    return f"failed after {attempts} tries: {last}"


def fields(s):
    def f(name, value, inline=True):
        return {"name": name, "value": str(value), "inline": inline}
    return [
        f("frequency", f"{s['pwm_hz']} Hz" if s["pwm_hz"] else "NO SIGNAL"),
        f("SoC", f"{s['soc_temp']} °C" if s["soc_temp"] is not None else "NO SIGNAL"),
        f("uptime", f"{s['uptime_s'] // 3600} h {(s['uptime_s'] % 3600) // 60} m"),
    ]


def main():
    db = open_db()
    stop = False

    def clean(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, clean)
    signal.signal(signal.SIGINT, clean)

    s = sample()
    state = verdict(s)
    db.execute("INSERT INTO events(ts,kind,detail) VALUES(?,?,?)",
               (now(), "watch-started", f"state={state} uptime={s['uptime_s']}s"))
    db.commit()
    # A watchdog starting up on a Pi that has only just booted means the power
    # came back, which is worth saying out loud. Record it as well as sending
    # it: an outage that leaves no ledger entry is one you cannot audit later,
    # and this Pi has no RTC, so the timestamp on a just-booted sample is
    # whatever fake-hwclock restored until NTP corrects it. uptime_s is the
    # only trustworthy figure at this moment, which is why it goes in the note.
    if s["uptime_s"] < 300:
        sent = notify("Pi rebooted, Spike is back on watch", BRASS, fields(s),
                      attempts=6)
        db.execute("INSERT INTO events(ts,kind,detail) VALUES(?,?,?)",
                   (now(), "rebooted",
                    f"uptime={s['uptime_s']}s at first sample | discord: {sent}"))
        db.commit()
    print(f"Spike watching {UNIT}, state={state}, tick={TICK_S}s, db={DB_PATH}",
          flush=True)

    while not stop:
        s = sample()
        new = verdict(s)
        db.execute(
            "INSERT INTO health(ts,state,unit_active,pwm_enable,pwm_hz,soc_temp,"
            "throttled,uptime_s) VALUES(?,?,?,?,?,?,?,?)",
            (s["ts"], new, int(s["unit_active"]), s["pwm_enable"], s["pwm_hz"],
             s["soc_temp"], s["throttled"], s["uptime_s"]))

        if new != state:
            msg = {
                ("live", "fault"): ("Emitter has gone silent under load", RUST),
                ("live", "silent"): ("Emitter stopped", EMBER),
                ("fault", "live"): ("Emitter recovered", VERDIGRIS),
                ("fault", "silent"): ("Emitter stopped while faulted", EMBER),
                ("silent", "live"): ("Emitter live", VERDIGRIS),
                ("silent", "fault"): ("Emitter started but is not driving", RUST),
            }.get((state, new), (f"Emitter {state} -> {new}", BRASS))
            sent = notify(msg[0], msg[1], fields(s))
            db.execute("INSERT INTO events(ts,kind,detail) VALUES(?,?,?)",
                       (s["ts"], f"{state}->{new}", f"{msg[0]} | discord: {sent}"))
            print(f"{s['ts']}  {state} -> {new}  ({sent})", flush=True)
            state = new

        db.commit()
        # Sleep in short slices so a stop lands promptly rather than up to a
        # full tick later.
        waited = 0.0
        while waited < TICK_S and not stop:
            time.sleep(0.5)
            waited += 0.5

    db.execute("INSERT INTO events(ts,kind,detail) VALUES(?,?,?)",
               (now(), "watch-stopped", f"state={state}"))
    db.commit()
    db.close()
    print("Spike stood down", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
