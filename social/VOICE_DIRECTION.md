# FinanceHub narration direction

The sound we want: a calm, confident documentary narrator (the style of big explainer
channels), not a hype voice and not an announcer. Use a recording of a real person as the
clone reference, never a famous creator's voice.

## Delivery rules (applied to every script)
1. **Hook in under 2 seconds.** First line is short and lands on a number or a twist.
   Write it as two beats: "Your bank pays you half a percent. ... And charges you twenty."
2. **One idea per line.** Max ~12 words. Each line becomes its own take, so pacing stays tight.
3. **Pauses are written, not hoped for.** `...` = 0.4 s breath before a reveal; a full stop
   = normal beat; a line break = 0.25 s gap added at assembly.
4. **Say numbers the way people speak them.** "seventy-eight thousand dollars", not "$78,000";
   "half a percent", not "0.5%". Round in speech, keep exact figures on screen.
5. **Stress one word per line**, marked in the script with *asterisks*; the take is redone
   until that word carries the weight (rise in pitch, tiny slowdown).
6. **Drop the pitch at the end of statements.** Questions only rise when they are real questions.
7. **The last line is quiet.** Slower, lower, no exclamation: "Time does the heavy lifting."

## Chatterbox settings (tts/cb_batch.py)
| setting | value | why |
|---|---|---|
| `exaggeration` | 0.55 for body lines, 0.7 for the hook | expressive without sounding acted |
| `cfg_weight` | 0.35 | slower, more deliberate pacing |
| `temperature` | 0.75 | natural variation between takes |
| takes per line | 3, keep the best | removes robotic reads |
| reference clip | `tts/my_voice.wav`, 20-30 s, quiet room, phone 15 cm away, calm read | the biggest single quality gain |

## Voice polish (ffmpeg, per line before assembly)
```
highpass=f=80, lowpass=f=12000,
afftdn=nf=-25,                              # gentle noise clean-up
equalizer=f=200:t=q:w=1:g=-2,               # remove boxiness
equalizer=f=3500:t=q:w=1.2:g=2,             # presence / clarity
deesser=i=0.4,
acompressor=threshold=-18dB:ratio=3:attack=10:release=120:makeup=3,
loudnorm=I=-14:TP=-1.5:LRA=7
```
Music bed sits 18-20 dB under the voice and ducks a further 4 dB while words are spoken.

## Re-voicing the existing 14 Shorts
Captions are timed word-by-word to the current voice, so a new voice means a full
re-render on the PC: re-voice each line with the settings above, then run `produce.mjs`
for each script. About 1 hour for all 14 on the GTX 1650.
