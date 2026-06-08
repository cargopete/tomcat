"""Tests for the dashboard's aggregation logic (no Flask server needed)."""
import sqlite3

import app as dashboard  # dashboard/ is on sys.path via conftest


def make_db(rows):
    """In-memory events table. rows = list of (ts, fired, note)."""
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE events (ts TEXT, fired INTEGER, note TEXT)")
    db.executemany("INSERT INTO events VALUES (?,?,?)", rows)
    db.commit()
    return db


def test_empty_db():
    stats = dashboard.gather_stats(make_db([]))
    assert stats["total"] == 0
    assert stats["fired"] == 0
    assert stats["suppressed"] == 0
    assert stats["hourly"] == [0] * 24
    assert stats["daily"] == []
    assert stats["recent"] == []


def test_counts_and_suppressed():
    rows = [
        ("2026-06-08 09:00:00", 1, ""),
        ("2026-06-08 09:05:00", 1, ""),
        ("2026-06-08 23:30:00", 0, "quiet-hours"),
        ("2026-06-08 09:06:00", 0, "cooldown"),
    ]
    stats = dashboard.gather_stats(make_db(rows))
    assert stats["total"] == 4
    assert stats["fired"] == 2
    assert stats["suppressed"] == 2


def test_hourly_histogram_bucketing():
    rows = [
        ("2026-06-08 09:00:00", 1, ""),
        ("2026-06-08 09:59:00", 1, ""),
        ("2026-06-08 23:30:00", 1, ""),
        ("2026-06-08 23:00:00", 0, "quiet-hours"),  # not a fire -> not counted
    ]
    stats = dashboard.gather_stats(make_db(rows))
    assert stats["hourly"][9] == 2
    assert stats["hourly"][23] == 1
    assert sum(stats["hourly"]) == 3


def test_daily_grouping_and_recent_order():
    rows = [
        ("2026-06-07 10:00:00", 1, ""),
        ("2026-06-08 10:00:00", 1, ""),
        ("2026-06-08 11:00:00", 1, ""),
    ]
    stats = dashboard.gather_stats(make_db(rows))
    # daily is newest-first
    assert stats["daily"][0]["date"] == "2026-06-08"
    assert stats["daily"][0]["fires"] == 2
    assert stats["daily"][1]["date"] == "2026-06-07"
    # recent is newest-first
    assert stats["recent"][0]["ts"] == "2026-06-08 11:00:00"
    assert stats["recent"][0]["fired"] is True
