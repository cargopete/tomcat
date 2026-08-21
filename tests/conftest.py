"""Test bootstrap.

`catdeter` imports `gpiozero` at module load, which only resolves to real
hardware on a Raspberry Pi. We inject a minimal stub into sys.modules so the
pure-logic functions can be imported and tested on any machine (laptop, CI
runner).

`src/pwm.py` needs no stub: it touches /sys only inside open(), never at
import, precisely so it can be imported and unit-tested off the Pi.
"""
import sys
import types
from pathlib import Path

# Make src/ and dashboard/ importable as top-level modules.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "dashboard"))

# Minimal gpiozero stub: only what is touched at import time / module scope
# needs to exist. Nothing here is exercised by the logic tests.
if "gpiozero" not in sys.modules:
    stub = types.ModuleType("gpiozero")

    class _DigitalInputDevice:  # pragma: no cover - never instantiated in tests
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("gpiozero stub: no hardware available")

    class _MotionSensor(_DigitalInputDevice):  # pragma: no cover
        pass

    stub.DigitalInputDevice = _DigitalInputDevice
    stub.MotionSensor = _MotionSensor
    sys.modules["gpiozero"] = stub
