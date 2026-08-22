#!/usr/bin/env python3
"""Find gated tones in a recording, using a software lock-in.

The problem this solves: an ultrasonic horn measured in a real garden competes
with insects, traffic hiss and rustling, all of which put broadband energy well
above 15 kHz. Raw loudness in a band is therefore useless - during a real
measurement the raw peak at 21 kHz read 820 with the tone playing and 338 with
it off, which sounds convincing until you notice the horn-off baseline had
already reached 393 at 23 kHz on its own.

So instead of asking "is this band loud", we ask "is this band flickering at
exactly 5 Hz", which is the rate tools/freq_probe.py gates each tone at.
Nothing in an ordinary environment does that inside a 240 Hz-wide slice of the
ultrasonic band.

Calibration, measured rather than assumed: across 96 trials on synthetic room
noise with no tone present, this score had a median of 2.8 and a worst case of
5.4; two horn-off recordings in a real garden peaked at 6.3. A real tone buried
40 dB under synthetic noise scored 269.

Usage: python3 tools/lockin_analyse.py capture.wav
"""
import sys
import wave

import numpy as np

FREQS = [5_000, 19_000, 20_000, 21_000, 22_000, 23_000]
GATE_HZ = 5.0       # must match tools/freq_probe.py
WIN = 2048          # 42.7 ms at 48 kHz -> 23.4 Hz bins
HOP = 512           # 10.7 ms -> 93.75 Hz envelope rate, ample for a 5 Hz gate
BAND_HZ = 120
DETECT, MARGINAL = 12.0, 6.0


def lockin_scores(path):
    w = wave.open(path)
    rate = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(float)
    win = np.hanning(WIN)
    frames = np.array([x[i:i + WIN] * win for i in range(0, len(x) - WIN, HOP)])
    spec = np.abs(np.fft.rfft(frames, axis=1))
    freqs = np.fft.rfftfreq(WIN, 1 / rate)
    env_rate = rate / HOP

    out = {}
    for f in FREQS:
        if f > rate / 2:
            out[f] = None          # above Nyquist: untestable, not absent
            continue
        sel = (freqs >= f - BAND_HZ) & (freqs <= f + BAND_HZ)
        env = spec[:, sel].sum(axis=1)
        e = env - env.mean()
        es = np.abs(np.fft.rfft(e * np.hanning(len(e))))
        ef = np.fft.rfftfreq(len(e), 1 / env_rate)
        gate = (ef > GATE_HZ - 0.4) & (ef < GATE_HZ + 0.4)
        other = (ef > 0.5) & (ef < env_rate / 2) & ~gate
        out[f] = float(es[gate].max() / max(np.median(es[other]), 1e-9))
    return rate, out


def main(path):
    rate, scores = lockin_scores(path)
    print(f"{path}: {rate} Hz sampling, Nyquist {rate // 2} Hz")
    print(f"lock-in at {GATE_HZ} Hz, band +/-{BAND_HZ} Hz\n")
    print(f"{'freq':>8} {'score':>8}  verdict")
    print("-" * 32)
    for f, s in scores.items():
        if s is None:
            print(f"{f:>8} {'--':>8}  above Nyquist, untestable")
            continue
        v = "DETECTED" if s >= DETECT else "marginal" if s >= MARGINAL else "not found"
        print(f"{f:>8} {s:>8.1f}  {v}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "capture.wav")
