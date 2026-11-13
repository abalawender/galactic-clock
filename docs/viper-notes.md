# Viper on the Pico W: lessons from the matrix rain

Experiment, not shipped: `render.draw_matrix` stays pure Python so the host
sim and the board run the same code. Numbers are from one-off probe scripts
run with `mpremote run` on the board (200-frame benches, `mpremote reset`
afterwards).

## Result

| variant | draw avg/frame | retained pens RAM |
|---|---|---|
| pure Python (naive v1) | 41 ms | — |
| pure Python (memoized dict pens) | 28–31 ms | ~17.5 KB (2151 entries) |
| pen-table arrays (array('i')) | 28.0 ms | ~47.6 KB (10400 slots) |
| `@micropython.native` (same body) | 25 ms (~17% faster) | ~17.5 KB |
| `@micropython.viper` (typed body) | **5.0 ms (~6× faster)** | same memo |
| scanout (`gu.update`) | 2.3 ms | — |

Viper output was verified **pixel-identical** to the Python path over 200
on-device frames (both paths sharing one pen-handle table; comparing the
normalized draw-call logs). Peak fps is tick-bound (`sleep(0.05)`), so the
6× never shows up on screen — that, plus keeping one rasterizer for
sim + board, is why it stayed a probe. Same reasoning demoted the
array('i') pen tables to a dict (dict wins on RAM, loses only ~3 ms that
the 50 ms tick absorbs anyway; see the `_PEN_MEMO` comment in render.py).

## Lessons

1. **Viper literals must fit machine ints.** On this 32-bit build a literal
   ≥ 2^30 stops being a small int and becomes an object; arithmetic mixing
   it with typed ints fails to compile (`ViperTypeError: can't do binary op
   between 'int' and 'object'`). The 32-bit LCG constant 2654435761 had to be
   split (`(x * 40503 << 16) + x * 14769 ≡ x * 2654435761 mod 2^32`). Same
   disease in pure Python: those bignum products cost ~16 ms/frame there.
2. **No `is None` on object locals** in this firmware's viper (`can't do
   binary op between 'object' and 'None'`). Workaround: pre-warm the tables
   and index the dict directly (`memo[key]`), or sentinel-compare.
3. **Typed locals reject object results.** `pen: int = create_pen(...)`
   fails ("local 'pen' has type 'int' but source is 'object'") — wrap with
   `int(...)`.
4. **Every global-object element is an object.** `TINTS[ti][0]` returns an
   object; each element needs `int(...)` before typed arithmetic. Hoisting
   the tint channels into typed locals first is cheapest.
5. **`ptr16`/`ptr32` reinterpret raw memory** — with an `array('h')`, a
   stored `-1` sentinel reads back as `65535` because ptr16 is unsigned;
   use a signed typecode (`'i'`) with `ptr32`, or a uint16-safe sentinel.
   On galactic-unicorn firmware pen handles are packed RGB ints
   (`create_pen(1,2,3)` → `0x010203`), so 16-bit slots were wrong anyway
   — a pure-Python bug Viper's ptr casting exposed.
6. **`exec()` into a plain dict does NOT publish new top-level defs** to the
   module namespace on this port (some snippets went into the dict,
   `NameError` at first call). exec into `globals()`, or pass needed
   objects through the globals mapping.
7. **No `inspect` module on the board** — copying a function body for a
   native variant means literally copying the source text.
8. **Decorated defs compile at import time**: keep viper/native bodies in
   try/except at module scope so a firmware without the emitters degrades
   cleanly (compile errors surface as `SyntaxError`/`ViperTypeError` then).
9. **Method calls (`d.pixel(x, j)`) from viper work fine** but stay object
   calls — the 6× came from typed scalar math and ptr indexing, not the
   draw calls; a buffer-writer API (writing RGB into a `memoryview`) would
   amplify the Viper gap even further.
10. **The fastest win is boring**: pen memoization (dict, ~17 KB) took
    the naive body from 41 ms to under 31 ms with zero portability cost.
    Viper/native only pay off after that, and only if fps actually
    matters.
