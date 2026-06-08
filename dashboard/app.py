#!/usr/bin/env python3
"""TomCat dashboard - a tiny read-only Flask view over the event log.

Shows totals, a per-day breakdown, the hour-of-day distribution, and the most
recent detections from the SQLite DB that `catdeter.py` writes. Points at the
same DB via TOMCAT_DB_PATH (default ~/catdeter.sqlite3).

Run locally:
    pip install flask
    TOMCAT_DB_PATH=~/catdeter.sqlite3 python dashboard/app.py
    # then open http://<pi-ip>:8080/
"""
import os
import sqlite3
from pathlib import Path

from flask import Flask, jsonify, render_template

DB_PATH = Path(os.environ.get("TOMCAT_DB_PATH", Path.home() / "catdeter.sqlite3"))

app = Flask(__name__)


def connect_ro(path):
    """Open the DB read-only so the dashboard can never corrupt the log."""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def gather_stats(db, day_limit=30, recent_limit=20):
    """Aggregate the events table into a plain dict. Pure: takes a connection,
    returns data, touches no globals - which is what makes it unit-testable."""
    cur = db.cursor()

    total, fired = cur.execute(
        "SELECT COUNT(*), COALESCE(SUM(fired), 0) FROM events"
    ).fetchone()
    suppressed = total - fired

    last24_fired = cur.execute(
        "SELECT COALESCE(SUM(fired), 0) FROM events "
        "WHERE ts >= datetime('now', '-1 day')"
    ).fetchone()[0]

    daily = cur.execute(
        "SELECT date(ts) AS d, "
        "       COALESCE(SUM(fired), 0) AS fires, "
        "       COUNT(*) AS hits "
        "FROM events GROUP BY d ORDER BY d DESC LIMIT ?",
        (day_limit,),
    ).fetchall()

    # Hour-of-day histogram of actual fires, 0..23 (zero-filled).
    hourly = [0] * 24
    for hh, fires in cur.execute(
        "SELECT CAST(strftime('%H', ts) AS INTEGER) AS hh, "
        "       COALESCE(SUM(fired), 0) "
        "FROM events GROUP BY hh"
    ):
        if hh is not None:
            hourly[hh] = fires

    recent = cur.execute(
        "SELECT ts, fired, COALESCE(note, '') FROM events "
        "ORDER BY ts DESC LIMIT ?",
        (recent_limit,),
    ).fetchall()

    return {
        "total": total,
        "fired": fired,
        "suppressed": suppressed,
        "last24_fired": last24_fired,
        "daily": [{"date": d, "fires": f, "hits": h} for d, f, h in daily],
        "hourly": hourly,
        "recent": [
            {"ts": ts, "fired": bool(f), "note": note} for ts, f, note in recent
        ],
    }


def _load_stats():
    if not DB_PATH.exists():
        return None
    db = connect_ro(DB_PATH)
    try:
        return gather_stats(db)
    except sqlite3.OperationalError:
        # DB exists but the events table hasn't been created yet.
        return None
    finally:
        db.close()


@app.route("/")
def index():
    stats = _load_stats()
    return render_template("index.html", db_path=str(DB_PATH), stats=stats)


@app.route("/api/stats")
def api_stats():
    stats = _load_stats()
    return jsonify(stats or {"error": "no data", "db_path": str(DB_PATH)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
