"""Original sound design for FinanceHub in Motion Shorts.

Everything is synthesized from scratch (no samples, no third-party music),
so the channel owns the audio outright. The score is timed to the scene list:
  - warm pad + sub pulse bed in A minor (chord change per scene)
  - soft felt-piano motif on each kicker word
  - whoosh on every scene transition (matches the red wipe)
  - accelerating ticks while counters / charts / shrink animations run
  - low impact + bell when a number lands
Output: 48 kHz stereo WAV, mastered to about -14 LUFS by ffmpeg loudnorm.
"""
import json, math, sys
import numpy as np
from scipy.io import wavfile

SR = 48000
rng = np.random.default_rng(7)


def env(n, a=0.01, r=0.3):
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / max(r, 1e-4))
    return e


def lp(x, cutoff):
    """one-pole low-pass"""
    a = math.exp(-2 * math.pi * cutoff / SR)
    y = np.empty_like(x); acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc; y[i] = acc
    return y


def note(f):  # MIDI-ish helper: semitones from A3
    return 220.0 * 2 ** (f / 12)


def pad(freqs, dur, vol=0.14):
    n = int(dur * SR); t = np.arange(n) / SR
    x = np.zeros(n)
    for f in freqs:
        for det in (-0.12, 0.0, 0.12):  # gentle chorus
            ph = rng.uniform(0, 2 * np.pi)
            x += np.sin(2 * np.pi * f * (1 + det / 100) * t + ph) * 0.6
            x += np.sin(2 * np.pi * 2 * f * t + ph) * 0.12
    fade = np.minimum(1, t / 0.6) * np.minimum(1, (dur - t) / 0.6)
    return x / len(freqs) * vol * np.clip(fade, 0, 1)


def piano(f, dur=1.4, vol=0.22):
    n = int(dur * SR); t = np.arange(n) / SR
    x = sum(np.sin(2 * np.pi * f * k * t) * (0.5 ** (k - 1)) * np.exp(-t * (2.2 + k)) for k in range(1, 6))
    click = rng.normal(0, 1, n) * np.exp(-t * 400) * 0.05
    return (x + click) * vol * np.minimum(1, t / 0.004)


def whoosh(dur=0.45, vol=0.18):
    n = int(dur * SR); t = np.arange(n) / SR
    noise = rng.normal(0, 1, n)
    sweep = np.linspace(300, 5000, n)
    # crude swept band-pass: differentiate low-passed noise at rising cutoff
    y = np.zeros(n); acc = 0.0
    for i in range(n):
        a = math.exp(-2 * math.pi * sweep[i] / SR)
        acc = (1 - a) * noise[i] + a * acc; y[i] = acc
    shape = np.sin(np.pi * t / dur) ** 2
    return y * shape * vol


def tick(vol=0.05):
    n = int(0.03 * SR); t = np.arange(n) / SR
    return (np.sin(2 * np.pi * 2400 * t) + rng.normal(0, .3, n)) * np.exp(-t * 180) * vol


def impact(vol=0.6):
    n = int(1.6 * SR); t = np.arange(n) / SR
    f = 55 * np.exp(-t * 3) + 38
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.2)
    bell = sum(np.sin(2 * np.pi * note(24) * r * t) * np.exp(-t * d) for r, d in ((1, 2.5), (2.76, 4), (5.4, 6))) * 0.25
    return (boom + bell) * vol


def add(buf, x, at):
    i = int(at * SR)
    if i >= len(buf): return
    j = min(len(buf), i + len(x))
    buf[i:j] += x[: j - i, None] if x.ndim == 1 else x[: j - i]


# A minor progression (semitones from A3): Am, F, C, G, Am
PROG = [[0, 3, 7], [-4, 0, 3], [3, 7, 10], [-2, 2, 5], [0, 3, 7]]
MOTIF = [12, 15, 19, 17, 15, 12, 10, 12]


def score(spec_path, out_wav):
    scenes = json.load(open(spec_path))["scenes"]
    total = sum(s["dur"] for s in scenes)
    buf = np.zeros((int(total * SR) + SR, 2))
    t0 = 0.0; mi = 0
    for si, s in enumerate(scenes):
        d = s["dur"]
        chord = PROG[si % len(PROG)]
        p = pad([note(c) for c in chord], d + 0.6)
        add(buf, np.stack([p, np.roll(p, 240)], 1), max(0, t0 - 0.3))
        # sub pulse, like a slow heartbeat
        for b in np.arange(0.0, d, 0.5):
            n = int(0.25 * SR); tt = np.arange(n) / SR
            add(buf, np.sin(2 * np.pi * note(chord[0] - 24) * tt) * np.exp(-tt * 9) * 0.18, t0 + b)
        if si > 0: add(buf, whoosh(), t0 - 0.2)
        kind = s["t"]
        if kind in ("kicker", "end"):
            words = len(s.get("text", "").split())
            for w in range(words):
                add(buf, piano(note(MOTIF[mi % len(MOTIF)])), t0 + 0.02 + w * 0.07 * 1.0 if w == 0 else t0 + w * 0.07)
                mi += 1 if w % 2 == 0 else 0
            if kind == "end": add(buf, impact(0.45), t0 + 0.1)
        if kind in ("counter", "chart", "shrink"):
            a, b = 0.25, d - 0.6
            k = 0.0
            while k < 1:
                gap = (0.32 if kind == 'chart' else 0.2) - 0.1 * k  # accelerate, gentler
                add(buf, tick(), t0 + a + (b - a) * k)
                k += gap / (b - a)
            add(buf, impact(), t0 + b)
        if kind == "tiles":
            per = (d - 0.8) / len(s["steps"])
            for i in range(len(s["steps"])):
                add(buf, piano(note(MOTIF[i % len(MOTIF)] + 12), vol=0.3), t0 + i * per)
                if i: add(buf, tick(0.2), t0 + i * per)
            add(buf, impact(0.5), t0 + (len(s["steps"]) - 1) * per)
        t0 += d
    buf = buf[: int(total * SR)]
    # gentle tail fade
    fade = np.linspace(1, 0, int(0.5 * SR)); buf[-len(fade):] *= fade[:, None]
    buf /= max(1e-9, np.abs(buf).max()) / 0.9
    wavfile.write(out_wav, SR, (buf * 32767).astype(np.int16))


if __name__ == "__main__":
    score(sys.argv[1], sys.argv[2])
