---
name: unicorn
description: The Galactic Unicorn board itself — LED matrix display snippets (`display.py`) and the frozen `galactic` MicroPython synth/audio API, probed on the board. For mpremote/REPL behavior (exec stops main.py) see the `mpremote` skill. Sensors (SCD41 etc.) get their own `sensors` skill if needed.
---

# Galactic Unicorn — LED matrix + frozen MicroPython APIs

## LED matrix display snippets (`display.py`)

Prerequisites: board attached to WSL (`scripts/attach.sh`, see README
"Connect"); `mpremote` installed (`apt install micropython-mpremote`).

```bash
python3 skills/unicorn/display.py                  # orange dots flying around, plays until interrupted
python3 skills/unicorn/display.py --text "Hi"      # static text (clips at 53 px)
python3 skills/unicorn/display.py --logo           # static Mistral logo
python3 skills/unicorn/display.py --icons          # HITL review: cycle all weather icons on the
                                                   # board, 3 s each, WMO code labelled ("n" =
                                                   # night variant); loops until interrupted.
                                                   # Host-only alternative: python3 sim/sim.py
                                                   # play --screen icons
python3 skills/unicorn/display.py --stop           # interrupt animation and clear
# after --icons, `mpremote reset` reboots the board back into main.py (weather clock)
```

Gotcha: `--icons` shows the *deployed* render.py — the on-board snippet does
`import render`, which resolves to the flashed `/render.py`, not the working
tree. After changing `src/render.py`, deploy first (`scripts/deploy.sh
--no-reset`), then run `--icons`; afterwards `--stop` + `mpremote reset`
return to the weather clock. Host-only alternative that always uses the
working tree: `python3 sim/sim.py play --screen icons`.

`display.py` builds a MicroPython snippet and runs it on the board via
`mpremote run`:

```python
from galactic import GalacticUnicorn
from picographics import PicoGraphics, DISPLAY_GALACTIC_UNICORN
gu = GalacticUnicorn()
d = PicoGraphics(display=DISPLAY_GALACTIC_UNICORN)
# ... draw ...
gu.update(d)
```

## Synth audio (`from galactic import GalacticUnicorn`)

Module name is `galactic` (NOT `galactic_unicorn`). Probed on the board:

- **No sound unless `gu.play_synth()` is called** — `trigger_attack()` /
  `play_tone()` alone only move the channel envelope; the synth output
  (PWM/DMA) stays off. `gu.stop_playing()` stops it again (frees DMA).
- `gu.synth_channel(i)` — **8 channels, 0..7**; channel 8 raises
  "channel out of range. Expected 0 to 7".
- Channel methods: `configure(waveforms=, frequency=, volume=, attack=,
  decay=, sustain=, release=, pulse_width=)`, `restore()`, getters/setters
  `waveforms/frequency/volume/attack_duration/decay_duration/sustain_level/
  release_duration/pulse_width`, `trigger_attack()`, `trigger_release()`,
  `play_tone(frequency, volume=None, attack=None, release=None)`.
  **There is no `stop()`** — stop a sustained note with `trigger_release()`.
- Waveform constants on the channel: `WAVE=1, SINE=8, TRIANGLE=16, SAW=32,
  SQUARE=64, NOISE=128`. `play_tone()` forces SINE + full sustain.
- `volume` is a float 0..1 (not 0..100). `frequency` must be an **int** —
  a float raises `TypeError: can't convert float to int`.
- A triggered channel sustains until `trigger_release()`; ADSR durations
  are seconds (float). A beep = `configure(...)` + `trigger_attack()` +
  sleep + `trigger_release()`.
- A second `GalacticUnicorn()` created inside `exec` can still play audio
  if it calls `play_synth()` itself (used for REPL tone demos); its
  `update()` calls fight the main loop's display updates.
