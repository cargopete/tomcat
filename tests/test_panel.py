"""Tests for the panel's scheduled-hours liveness calculation."""
import importlib.util
import sqlite3
from datetime import datetime
from pathlib import Path


PANEL = Path(__file__).resolve().parent.parent / "panel" / "app.py"
SPEC = importlib.util.spec_from_file_location("panel_app", PANEL)
panel = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(panel)


def health_db(path, rows):
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE health (
            ts TEXT NOT NULL,
            state TEXT NOT NULL,
            unit_active INTEGER NOT NULL,
            pwm_enable INTEGER,
            pwm_hz INTEGER,
            soc_temp REAL,
            throttled TEXT,
            uptime_s INTEGER);
        CREATE TABLE events (ts TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT);
    """)
    db.executemany(
        "INSERT INTO health VALUES (?, ?, 1, 1, 22000, 45.0, '0x0', 1)", rows,
    )
    db.commit()
    db.close()


def test_watch_stats_excludes_deliberately_silent_daytime(tmp_path, monkeypatch):
    path = tmp_path / "health.sqlite3"
    health_db(path, [
        ("2026-08-23T23:00:00", "live"),
        ("2026-08-24T09:59:30", "live"),
        ("2026-08-24T10:00:00", "silent"),
        ("2026-08-24T15:00:00", "silent"),
    ])
    monkeypatch.setattr(panel, "DB_PATH", path)
    monkeypatch.setattr(panel, "NIGHT_START_H", 23)
    monkeypatch.setattr(panel, "NIGHT_END_H", 10)
    monkeypatch.setattr(panel, "datetime", type("Clock", (), {
        "now": staticmethod(lambda: datetime(2026, 8, 24, 16)),
    }))

    stats = panel.watch_stats()

    assert stats["samples_24h"] == 2
    assert stats["live_24h"] == 2
    assert stats["coverage"] == 100.0
    assert stats["faults_24h"] == 0
    assert stats["last_sample"] == "2026-08-24T09:59:30"


def test_watch_stats_keeps_faults_inside_scheduled_window(tmp_path, monkeypatch):
    path = tmp_path / "health.sqlite3"
    health_db(path, [
        ("2026-08-23T23:00:00", "live"),
        ("2026-08-24T01:00:00", "fault"),
        ("2026-08-24T10:30:00", "fault"),
    ])
    monkeypatch.setattr(panel, "DB_PATH", path)
    monkeypatch.setattr(panel, "NIGHT_START_H", 23)
    monkeypatch.setattr(panel, "NIGHT_END_H", 10)
    monkeypatch.setattr(panel, "datetime", type("Clock", (), {
        "now": staticmethod(lambda: datetime(2026, 8, 24, 16)),
    }))

    stats = panel.watch_stats()

    assert stats["samples_24h"] == 2
    assert stats["live_24h"] == 1
    assert stats["coverage"] == 50.0
    assert stats["faults_24h"] == 1
