"""Turn one Daily edition (site/media/daily/YYYY-MM-DD/01.jpg ...) into a vertical news Short.

Each 4:5 slide sits in the middle of a 9:16 frame over a blurred, darkened copy of itself,
with a slow push-in, soft crossfades and the FinanceHubW mark at the bottom. The music bed is
synthesized here (no samples), so the channel owns the audio outright. No voice.

    python social/daily_short.py 2026-10-09        -> build/daily-2026-10-09.mp4
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "motion"))
import sound  # noqa: E402

W, H, FPS = 1080, 1920, 30
HOLD, FADE = 4.6, 0.5           # seconds each slide is on screen, crossfade length
COVER_HOLD = 3.2                # the cover is the hook; keep it short


def frame(slide: Path, out: Path) -> None:
    img = Image.open(slide).convert("RGB")
    bg = img.resize((int(H * img.width / img.height), H)).crop((0, 0, W, H)) \
        if img.width / img.height < W / H else img.resize((W, int(W * img.height / img.width)))
    bg = bg.resize((W, H)).filter(ImageFilter.GaussianBlur(40))
    bg = ImageEnhance.Brightness(bg).enhance(0.22)
    fg = img.resize((W, int(W * img.height / img.width)), Image.LANCZOS)
    y = (H - fg.height) // 2 - 40
    bg.paste(fg, (0, y))
    icon = ROOT / "brand" / "financehubw-icon.png"
    if icon.exists():
        m = Image.open(icon).convert("RGBA")
        m.thumbnail((96, 96))
        bg.paste(m, ((W - m.width) // 2, H - 230), m)
    bg.save(out, quality=95)


def music(seconds: float, out: Path) -> None:
    chords = [[0, 3, 7], [-4, 0, 3], [-2, 2, 5], [-5, -1, 2]]   # Am  F  G  Em, slow
    step = 4.0
    n = int(seconds * sound.SR)
    mix = np.zeros(n)
    t = 0.0
    i = 0
    while t < seconds:
        seg = sound.pad([sound.note(c) for c in chords[i % 4]], min(step + 0.8, seconds - t + 0.01), vol=0.16)
        a = int(t * sound.SR)
        mix[a:a + len(seg)] += seg[: max(0, n - a)]
        t += step
        i += 1
    for k in range(int(seconds / step)):                       # felt piano on each chord change
        p = sound.piano(sound.note(chords[k % 4][2] + 12), 2.0, 0.10)
        a = int(k * step * sound.SR)
        mix[a:a + len(p)] += p[: max(0, n - a)]
    fade = np.minimum(1, np.arange(n) / sound.SR / 1.0) * np.minimum(1, (n - np.arange(n)) / sound.SR / 2.0)
    mix *= fade
    st = np.stack([mix, mix], 1)
    wavfile.write(out, sound.SR, (st / max(1e-6, np.abs(st).max()) * 0.8 * 32767).astype(np.int16))


def build(date: str) -> Path:
    folder = ROOT / "site" / "media" / "daily" / date
    slides = sorted(folder.glob("[0-9][0-9].jpg"))
    if not slides:
        sys.exit(f"no slides in {folder}")
    out = ROOT / "build" / f"daily-{date}.mp4"
    out.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        holds = [COVER_HOLD] + [HOLD] * (len(slides) - 1)
        args, filt = [], []
        for i, s in enumerate(slides):
            f = td / f"{i:02d}.jpg"
            frame(s, f)
            d = holds[i] + FADE
            args += ["-loop", "1", "-t", f"{d:.2f}", "-i", str(f)]
            n = int(d * FPS)
            filt.append(f"[{i}:v]scale=1188:-1,zoompan=z='1+0.06*on/{n}':x='iw/2-(iw/zoom/2)':"
                        f"y='ih/2-(ih/zoom/2)':d={n}:s={W}x{H}:fps={FPS},setsar=1[v{i}]")
        last, off = "v0", 0.0
        for i in range(1, len(slides)):
            off += holds[i - 1]
            filt.append(f"[{last}][v{i}]xfade=transition=fade:duration={FADE}:offset={off:.2f}[x{i}]")
            last = f"x{i}"
        total = sum(holds) + FADE
        wav = td / "m.wav"
        music(total, wav)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", *args, "-i", str(wav),
               "-filter_complex", ";".join(filt) + f";[{len(slides)}:a]loudnorm=I=-16:TP=-1.5[a]",
               "-map", f"[{last}]", "-map", "[a]", "-t", f"{total:.2f}",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
               "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
        subprocess.run(cmd, check=True)
    return out


if __name__ == "__main__":
    print(build(sys.argv[1]))
