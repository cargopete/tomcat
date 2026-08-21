"""Tests for the sysfs hardware-PWM wrapper.

No Pi required: we point HardwarePWM at a fake sysfs tree under tmp_path and
read back what it wrote. The one thing worth pinning down is the write order,
because the kernel rejects a duty_cycle larger than the period, which is
exactly what happens on every downward step of the sweep.
"""
import pytest

import pwm as pwm_mod
from pwm import DUTY_RANGE, HardwarePWM, PWMUnavailable


@pytest.fixture
def fake(tmp_path, monkeypatch):
    """A pre-exported pwmchip0/pwm0 tree, plus a log of every write."""
    chip = tmp_path / "pwmchip0"
    (chip / "pwm0").mkdir(parents=True)
    for f in ("period", "duty_cycle", "enable"):
        (chip / "pwm0" / f).write_text("0")

    p = HardwarePWM()
    p.chipdir = chip
    p.path = chip / "pwm0"

    writes = []
    original = HardwarePWM._write

    def spy(self, name, value):
        writes.append((name, str(value)))
        original(self, name, value)

    monkeypatch.setattr(HardwarePWM, "_write", spy)
    return p, writes


def read(path, name):
    return (path / name).read_text()


def test_set_computes_period_and_duty(fake):
    p, _ = fake
    p.set(20_000, DUTY_RANGE // 2)
    assert read(p.path, "period") == "50000"       # 20 kHz -> 50 us
    assert read(p.path, "duty_cycle") == "25000"   # 50 %


def test_set_at_24khz(fake):
    p, _ = fake
    p.set(24_000, DUTY_RANGE // 2)
    assert read(p.path, "period") == "41666"
    assert read(p.path, "duty_cycle") == "20833"


def test_duty_zeroed_before_period_shrinks(fake):
    """The kernel rejects duty_cycle > period, so duty must go to 0 first."""
    p, writes = fake
    p.set(20_000, DUTY_RANGE // 2)
    writes.clear()
    p.set(24_000, DUTY_RANGE // 2)   # shorter period than the previous duty

    names = [n for n, _ in writes]
    assert names == ["duty_cycle", "period", "duty_cycle"]
    assert writes[0][1] == "0"


def test_quarter_duty(fake):
    p, _ = fake
    p.set(20_000, 250_000)
    assert read(p.path, "duty_cycle") == "12500"


def test_off_is_idempotent_and_silences(fake):
    p, _ = fake
    p.set(20_000, DUTY_RANGE // 2)
    p.on()
    assert read(p.path, "enable") == "1"
    p.off()
    p.off()
    assert read(p.path, "enable") == "0"
    assert read(p.path, "duty_cycle") == "0"


def test_off_swallows_errors_so_it_is_handler_safe(tmp_path):
    """off() runs from signal handlers, where raising would be unhelpful."""
    p = HardwarePWM()
    p.path = tmp_path / "does-not-exist"
    p.off()


def test_missing_chip_names_the_overlay(tmp_path, monkeypatch):
    p = HardwarePWM()
    p.chipdir = tmp_path / "absent"
    with pytest.raises(PWMUnavailable, match="pwm-2chan"):
        p.open()


def test_open_exports_the_channel(tmp_path, monkeypatch):
    chip = tmp_path / "pwmchip0"
    chip.mkdir()
    (chip / "export").write_text("")

    p = HardwarePWM()
    p.chipdir = chip
    p.path = chip / "pwm0"

    # Stand in for udev: create the channel dir as soon as export is written.
    real_write = type(chip / "export").write_text

    def on_export(self, data, *a, **kw):
        result = real_write(self, data, *a, **kw)
        if self.name == "export":
            (chip / "pwm0").mkdir(exist_ok=True)
            for f in ("period", "duty_cycle", "enable"):
                (chip / "pwm0" / f).write_text("0")
        return result

    monkeypatch.setattr(type(chip / "export"), "write_text", on_export)
    monkeypatch.setattr(pwm_mod.time, "sleep", lambda _s: None)

    p.open()
    assert (chip / "pwm0" / "enable").read_text() == "0"
