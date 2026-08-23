#!/usr/bin/env python3
"""The emitter's control panel.

Reads the health database the watchdog writes, and works the lever. Everything
shown here is a real reading: there is no synthetic data anywhere in this file
or its template, and a value we do not have renders as NO SIGNAL rather than as
zero, because a missing reading that looks like a good reading is the worst
thing this panel could do.

Binds to the Tailscale interface by default, falling back to loopback. It never
binds 0.0.0.0 on its own: the lever turns on a device pointed at a garden, and
that is not something to leave open on a LAN.

Working the lever needs a narrow sudoers rule; see systemd/tomcat-panel.sudoers.
"""
import math
import os
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, url_for

UNIT = os.environ.get("TOMCAT_WATCH_UNIT", "tomcat-tone")
DB_PATH = Path(os.environ.get("TOMCAT_HEALTH_DB", Path.home() / "tomcat-health.sqlite3"))
PWM_CHIP = os.environ.get("TOMCAT_PWM_CHIP", "0")
PWM_CHANNEL = os.environ.get("TOMCAT_PWM_CHANNEL", "0")
PWM = Path(f"/sys/class/pwm/pwmchip{PWM_CHIP}/pwm{PWM_CHANNEL}")
PORT = int(os.environ.get("TOMCAT_PANEL_PORT", 8090))

# The gauge is bound to SoC temperature, which is a real continuous value with
# real limits: the Pi 4 begins throttling at 80 °C.
TEMP_MIN, TEMP_MAX = 30.0, 85.0
SWEEP_DEG = 125          # -125 to +125 reads as an instrument; 360 does not.
CX, CY = 100.0, 105.0    # gauge centre, in the SVG's own coordinates


def gauge_ticks():
    """Eleven tick marks around the dial. Computed here because Jinja has no
    trigonometry, and a template is the wrong place to keep any."""
    out = []
    for i in range(11):
        deg = -SWEEP_DEG + i * (2 * SWEEP_DEG / 10)
        a = math.radians(deg)
        major = i % 5 == 0
        inner = 57 if major else 60
        out.append({
            "x1": round(CX + inner * math.sin(a), 2),
            "y1": round(CY - inner * math.cos(a), 2),
            "x2": round(CX + 64 * math.sin(a), 2),
            "y2": round(CY - 64 * math.cos(a), 2),
            "major": major,
        })
    return out

app = Flask(__name__)


def sh(*args):
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def read(path, cast=str, default=None):
    try:
        return cast(path.read_text().strip())
    except (OSError, ValueError):
        return default


def tailscale_ip():
    ip = sh("tailscale", "ip", "-4").splitlines()
    return ip[0].strip() if ip else None


def live_state():
    """Read the hardware directly rather than trusting the last stored sample.

    The panel must not tell you the emitter is live because it was live thirty
    seconds ago. `fault` is systemd content while the pin is idle, which is the
    dropout this whole apparatus exists to catch.
    """
    active = sh("systemctl", "is-active", UNIT) == "active"
    enable = read(PWM / "enable", int)
    period = read(PWM / "period", int)
    if not active:
        state = "silent"
    elif enable == 1:
        state = "live"
    else:
        state = "fault"
    return {
        "state": state,
        "unit_active": active,
        "enabled_at_boot": sh("systemctl", "is-enabled", UNIT) == "enabled",
        "pwm_enable": enable,
        "hz": (1_000_000_000 // period) if period else None,
        "soc_temp": soc_temp(),
        "uptime_s": read(Path("/proc/uptime"), lambda s: int(float(s.split()[0]))),
    }


def soc_temp():
    raw = sh("vcgencmd", "measure_temp")
    try:
        return float(raw.split("=")[1].split("'")[0])
    except (IndexError, ValueError):
        return None


def db():
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def watch_stats():
    """Derived from the watchdog's samples. All of it is absent-tolerant: with
    no database yet, every figure is None and the template says NO SIGNAL."""
    empty = {"samples_24h": None, "live_24h": None, "coverage": None,
             "faults_24h": None, "last_sample": None, "events": []}
    conn = db()
    if conn is None:
        return empty
    try:
        since = (datetime.now() - timedelta(hours=24)).isoformat(timespec="seconds")
        row = conn.execute(
            "SELECT count(*) n,"
            "       sum(state = 'live') live,"
            "       sum(state = 'fault') fault,"
            "       max(ts) last"
            "  FROM health WHERE ts >= ?", (since,)).fetchone()
        events = [dict(r) for r in conn.execute(
            "SELECT ts, kind, detail FROM events ORDER BY ts DESC LIMIT 12")]
        n = row["n"] or 0
        if n == 0:
            return {**empty, "events": events}
        live = row["live"] or 0
        return {
            "samples_24h": n,
            "live_24h": live,
            "coverage": round(100.0 * live / n, 1),
            "faults_24h": row["fault"] or 0,
            "last_sample": row["last"],
            "events": events,
        }
    finally:
        conn.close()


def snapshot():
    s = live_state()
    stats = watch_stats()
    t = s["soc_temp"]
    frac = None
    if t is not None:
        frac = min(1.0, max(0.0, (t - TEMP_MIN) / (TEMP_MAX - TEMP_MIN)))
    return {
        **s,
        **stats,
        "temp_frac": frac,
        "needle_deg": round(-SWEEP_DEG + 2 * SWEEP_DEG * frac, 1) if frac is not None else None,
        "ticks": gauge_ticks(),
        "unit": UNIT,
        "uptime_h": (s["uptime_s"] // 3600) if s["uptime_s"] else None,
        "uptime_m": ((s["uptime_s"] % 3600) // 60) if s["uptime_s"] else None,
    }


@app.get("/")
def index():
    return render_template("panel.html", d=snapshot())


@app.get("/api/status")
def api_status():
    return jsonify(snapshot())


@app.post("/lever")
def lever():
    """Throw the lever. The action is decided here, not sent by the browser, so
    a stale page cannot start something you meant to stop."""
    want = "stop" if sh("systemctl", "is-active", UNIT) == "active" else "start"
    subprocess.run(["sudo", "-n", "/usr/bin/systemctl", want, UNIT],
                   capture_output=True, timeout=15)
    return redirect(url_for("index"))


if __name__ == "__main__":
    host = os.environ.get("TOMCAT_PANEL_HOST") or tailscale_ip() or "127.0.0.1"
    print(f"panel on http://{host}:{PORT}/  (unit={UNIT}, db={DB_PATH})", flush=True)
    app.run(host=host, port=PORT)
