"""Environment-variable config overrides take effect at import time."""
import importlib


def test_env_overrides_apply(monkeypatch):
    monkeypatch.setenv("TOMCAT_DUTY", "250000")
    monkeypatch.setenv("TOMCAT_QUIET_START_H", "23")
    monkeypatch.setenv("TOMCAT_F_LOW_HZ", "18000")
    monkeypatch.setenv("TOMCAT_SWEEP_TICK_S", "0.05")
    monkeypatch.setenv("TOMCAT_DB_PATH", "/tmp/test.sqlite3")

    import catdeter
    catdeter = importlib.reload(catdeter)

    assert catdeter.DUTY == 250000
    assert catdeter.QUIET_START_H == 23
    assert catdeter.F_LOW_HZ == 18000
    assert catdeter.SWEEP_TICK_S == 0.05
    assert str(catdeter.DB_PATH) == "/tmp/test.sqlite3"


def test_defaults_when_unset(monkeypatch):
    for var in ("TOMCAT_DUTY", "TOMCAT_QUIET_START_H", "TOMCAT_F_LOW_HZ"):
        monkeypatch.delenv(var, raising=False)

    import catdeter
    catdeter = importlib.reload(catdeter)

    assert catdeter.DUTY == 500000
    assert catdeter.QUIET_START_H == 22
    assert catdeter.F_LOW_HZ == 20000
