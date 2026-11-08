---
name: unicorn
description: Board-specific MicroPython APIs on the Galactic Unicorn's Pimoroni firmware — the frozen `galactic` synth/audio API, probed on the board. For mpremote/REPL behavior (exec stops main.py) see the `mpremote` skill.
---

# Galactic Unicorn MicroPython gotchas — synth audio (`from galactic import GalacticUnicorn`)

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
