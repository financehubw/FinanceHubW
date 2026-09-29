# FinanceHub in Motion

Short-form (1080x1920, ~15 s) kinetic motion-graphics Shorts/Reels in the FinanceHub brand style
(ink black, cream, vermilion), with an original, fully synthesized sound design.

## Files
- `engine.py`: frame renderer (SVG to PNG to ffmpeg). Scene types: `kicker`, `counter`, `chart`, `tiles`, `shrink`, `end`.
- `sound.py`: original score and SFX timed to each scene (pad, felt-piano motif, whooshes, ticks, impacts). No samples or licensed music, so the channel owns the audio outright.
- `scripts/*.json`: one file per video. Every figure is computed in code, not typed by hand.

## Render one video
```bash
pip install cairosvg pillow numpy scipy
python engine.py scripts/m1_ten_year_head_start.json out/m1.mp4
python sound.py  scripts/m1_ten_year_head_start.json out/m1.wav
ffmpeg -i out/m1.mp4 -i out/m1.wav -map 0:v -map 1:a -c:v copy \
  -af "loudnorm=I=-14:TP=-1.5:LRA=9" -c:a aac -b:a 192k -shortest final/m1.mp4
```
Fonts: Fraunces (900) and Archivo (800) must be installed (both SIL Open Font License).

## Preview a frame
```bash
python engine.py still scripts/m2_rule_of_72.json 5.0 preview.png
```

## Current videos
| File | Claim | Source of figure |
|---|---|---|
| m1_ten_year_head_start | $100/mo at 8% from 20 vs 30 to 65: $527,454 vs $229,388 | Future-value formula, monthly compounding |
| m2_rule_of_72 | $10k at 8% doubles every ~9 years, reaching $160k at 36 years | Rule of 72 |
| m3_100_shrinking | $100 at 3% inflation is worth about $49 after 24 years | 100 / 1.03^24 |
| m4_five_dollar_coffee | $5/day invested for 30 years at 8% grows to about $226,659 | FV of $152.08/mo |
| m5_1970_dollar | $1 (1970) has about $0.12 of buying power today | US CPI-U 1970 avg 38.8 vs about 322 |

All content is education, not financial advice.
