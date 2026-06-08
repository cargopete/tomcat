"""Tests for the quiet-hours window logic.

The midnight-wrapping case (22:00 -> 07:00) is the classic off-by-one trap,
so it gets the most coverage.
"""
import datetime

import catdeter


def at(hour):
    """A datetime fixed to a given hour (date is irrelevant to the logic)."""
    return datetime.datetime(2026, 6, 8, hour, 30, 0)


# --- Wrapping window: the real default, 22:00 -> 07:00 -------------------
def test_wrapping_window_late_evening_is_quiet():
    assert catdeter.in_quiet_hours(at(22), start_h=22, end_h=7) is True
    assert catdeter.in_quiet_hours(at(23), start_h=22, end_h=7) is True


def test_wrapping_window_after_midnight_is_quiet():
    assert catdeter.in_quiet_hours(at(0), start_h=22, end_h=7) is True
    assert catdeter.in_quiet_hours(at(6), start_h=22, end_h=7) is True


def test_wrapping_window_boundaries():
    # start is inclusive, end is exclusive
    assert catdeter.in_quiet_hours(at(7), start_h=22, end_h=7) is False
    assert catdeter.in_quiet_hours(at(21), start_h=22, end_h=7) is False


def test_wrapping_window_daytime_is_loud():
    for h in (8, 12, 17, 21):
        assert catdeter.in_quiet_hours(at(h), start_h=22, end_h=7) is False


# --- Non-wrapping window: e.g. a daytime-only quiet block -----------------
def test_non_wrapping_window():
    assert catdeter.in_quiet_hours(at(9), start_h=8, end_h=17) is True
    assert catdeter.in_quiet_hours(at(8), start_h=8, end_h=17) is True   # inclusive start
    assert catdeter.in_quiet_hours(at(17), start_h=8, end_h=17) is False  # exclusive end
    assert catdeter.in_quiet_hours(at(7), start_h=8, end_h=17) is False


# --- Degenerate window: start == end means disabled ----------------------
def test_equal_bounds_disables_quiet_hours():
    for h in range(24):
        assert catdeter.in_quiet_hours(at(h), start_h=0, end_h=0) is False


# --- Defaults wired up from module config --------------------------------
def test_defaults_match_module_config():
    # Sanity: calling with no explicit bounds uses the module defaults.
    expected = catdeter.in_quiet_hours(
        at(23), start_h=catdeter.QUIET_START_H, end_h=catdeter.QUIET_END_H
    )
    assert catdeter.in_quiet_hours(at(23)) == expected
