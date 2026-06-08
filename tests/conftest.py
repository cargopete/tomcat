"""Test bootstrap.

`catdeter` imports `pigpio` at module load, which is only present on a
Raspberry Pi. We inject a minimal stub into sys.modules so the pure-logic
functions can be imported and tested on any machine (laptop, CI runner).
"""
import sys
import types
from pathlib import Path

# Make src/ importable as top-level modules.
SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

# Minimal pigpio stub: only the attributes touched at import time / module
# scope need to exist. Nothing here is exercised by the logic tests.
if "pigpio" not in sys.modules:
    stub = types.ModuleType("pigpio")
    stub.INPUT = 0
    stub.PUD_DOWN = 1

    def _pi(*_args, **_kwargs):  # pragma: no cover - never called in tests
        raise RuntimeError("pigpio stub: no hardware available")

    stub.pi = _pi
    sys.modules["pigpio"] = stub
