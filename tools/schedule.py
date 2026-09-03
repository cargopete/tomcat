#!/usr/bin/env python3
"""Put the emitter where the clock says it should be.

Cats come at night, so the emitter runs nights: on at 22:00, off at 10:00.
This is a reconciler rather than a pair of start/stop jobs. It reads the clock,
works out whether the emitter ought to be running, and makes it so. That single
property is what makes every awkward path come out right:

  * A power cut at 02:00 resumes the horn on boot, because the window says so.
  * A power cut at 14:00 does not, for the same reason.
  * A missed 22:00 trigger (Pi off, or asleep) is caught by the timer's
    Persistent=true, and the reconciler still does the correct thing whichever
    boundary was missed, because it consults the clock rather than the trigger.

It deliberately runs only at the boundaries and at boot catch-up, never on a
short interval. If you throw the lever by hand at two in the afternoon, that
should stick until the next boundary rather than being quietly undone ten
minutes later by a machine that thinks it knows better.

Window is [start, end) on a 24h clock, wrapping past midnight. start == end
disables the schedule entirely and leaves the emitter alone.
"""
import datetime
import os
import subprocess
import sys

UNIT = os.environ.get("TOMCAT_WATCH_UNIT", "tomcat-tone")
START_H = int(os.environ.get("TOMCAT_NIGHT_START_H", 22))
END_H = int(os.environ.get("TOMCAT_NIGHT_END_H", 10))


def in_window(hour, start=START_H, end=END_H):
    """True if `hour` is inside the running window.

    Same wrapping logic as quiet hours in catdeter.py, inverted in meaning:
    there the window is when to stay silent, here it is when to make noise.
    """
    if start == end:
        return None          # schedule disabled; caller leaves well alone
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def sh(*args):
    return subprocess.run(args, capture_output=True, text=True, timeout=20)


def main():
    now = datetime.datetime.now()
    want = in_window(now.hour)
    if want is None:
        print(f"schedule disabled (start == end == {START_H}); leaving {UNIT} alone")
        return 0

    active = sh("systemctl", "is-active", UNIT).stdout.strip() == "active"
    window = f"{START_H:02d}:00-{END_H:02d}:00"

    if want == active:
        print(f"{now:%Y-%m-%d %H:%M} {window}: {UNIT} already "
              f"{'running' if active else 'stopped'}, nothing to do")
        return 0

    action = "start" if want else "stop"
    r = sh("systemctl", action, UNIT)
    if r.returncode != 0:
        print(f"{now:%Y-%m-%d %H:%M} {window}: {action} {UNIT} FAILED: "
              f"{r.stderr.strip()}", file=sys.stderr)
        return 1
    print(f"{now:%Y-%m-%d %H:%M} {window}: {action}ed {UNIT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
