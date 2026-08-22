# Measurements

What has actually been measured on this build, how, and what the numbers do
not say. Everything here is reproducible with the scripts in `tools/`.

## 2026-08-22 — acoustic output, 19–23 kHz

**Question.** Does the horn radiate anything in the 20–24 kHz band the whole
project depends on? An earlier audible probe had suggested it died above 8 kHz,
but that was taken from *behind* a directional horn using human ears that roll
off across the same band, so it settled nothing.

**Apparatus.** Raspberry Pi 4 driving GPIO18 through an IRLZ44N into a piezo
horn on a 12 V rail. MacBook Pro internal microphone at 48 kHz mono, placed
20–30 cm directly in front of the horn's mouth. Outdoors, ordinary garden
noise, no attempt made to keep quiet.

**Method.** `tools/freq_probe.py` plays each tone gated on and off at exactly
5 Hz. `tools/lockin_analyse.py` looks for energy in a 240 Hz-wide slice around
each target that is itself flickering at 5 Hz. This is a software lock-in, and
it matters: raw band loudness is useless here, because a horn-off baseline in
the same garden reached a raw peak of 393 at 23 kHz on ambient noise alone.

**Design.** Eleven blind trials. Each trial the Pi played a randomly chosen
subset of {19, 20, 21, 22, 23} kHz, and the detector was asked about all of
them without being told which were chosen. 5 kHz played in every trial as a
mandatory control, since the horn is known to radiate strongly there; any trial
that could not see the control was voided rather than averaged in.

**Result.** 8 of 11 trials valid.

Pooled across 19–22 kHz, the range this microphone can actually hear:

| | n | mean | median |
|---|---|---|---|
| tone playing | 14 | 12.78 | 13.50 |
| silent | 18 | 4.96 | 5.26 |

Permutation test, 50 000 shuffles: **p = 0.00002**. Played observations
averaged 2.6× the silent ones, and 11 of 14 sat above the 95th percentile of
everything measured while silent.

23 kHz alone: played mean 3.83 (n=3), silent 4.54 (n=5), **p = 0.77**. This is
the predicted null. 23 kHz sits inside the anti-aliasing rolloff below the
48 kHz card's 24 kHz Nyquist limit, so the microphone physically cannot hear
it. The method returning nothing exactly where it cannot see is the strongest
evidence available that it is not manufacturing detections.

**Calibration.** Across 96 measurements on synthetic room noise with no tone,
the lock-in score had a median of 2.8, a 99th percentile of 5.3 and a worst
case of 5.4. Two horn-off recordings in the real garden peaked at 6.3. A tone
buried 40 dB beneath synthetic noise scored 269.

**Conclusion.** The horn radiates across 19–22 kHz. The earlier "dies above
8 kHz" reading is superseded and was an artefact of listening position and
human hearing.

**What this does not say.**

- **Nothing about loudness.** Uncalibrated microphone, rolling off across the
  band of interest. Presence is established; SPL and useful range are not.
- **Nothing above 23 kHz.** Untestable with a 48 kHz sound card.
- **Nothing about cats.** No cat has been observed. The 96 dB / 1 m figures in
  BUILD.md are from Nelson et al.'s study of the commercial CATWatch.

**Fault found.** 3 of 11 trials failed the 5 kHz control, meaning the horn
intermittently stopped reaching a microphone 30 cm away at a frequency it
radiates strongly. Roughly a one-in-four dropout rate. At the time of
measurement the 33 Ω series resistor was bridged with jumper leads rather than
seated in the breadboard, which is the prime suspect. This wants fixing before
any range or efficacy work is worth doing.

## Reproducing

On the Pi:

```bash
sudo python3 tools/freq_probe.py 21000 22000     # or no args for a silent control
```

On a machine with a microphone in front of the horn:

```bash
ffmpeg -f avfoundation -i ":0" -ar 48000 -ac 1 -t 42 -y capture.wav
python3 tools/lockin_analyse.py capture.wav
```

Always record a horn-off baseline in the same place first. Without it, the
numbers mean nothing.
