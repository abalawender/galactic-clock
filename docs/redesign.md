# Redesign: display/runtime architecture (proposal)

Status: proposal for discussion. Nothing here is merged; this doc exists so
the architecture has a written home before more code lands.

## Goals

1. Make screens and their timing testable without the board (host-simulable,
   deterministic).
2. Stop multiplexing concerns by hand: today `main.py` mixes a cooperative
   "screen loop", deadlined sleeps, button IRQs, and sensor polling in one
   implicit timeline. That is the source of every "why did the ring skip a
   beat" bug we have.
3. Keep the current feature set stable while the runtime under it changes.

## Non-goals (for now)

- No new user-facing features in the same change.
- No firmware swap yet (stays MicroPython + `usl/ssd`, same deploy path).
- No graphics-stack rework beyond what the screens already need.

## Target architecture

Same idea as the service/actor split that already exists informally, made
explicit and testable:

    ┌──────────── services (domain, no GPIO) ────────────┐
    │  clock   weather   co2   alerts   …                │
    └───────▲──────────────▲──────────────▲─────────────┘
            │ subscribe()  │              │ publish()
    ┌───────┴──────────────┴──────────────┴─────────────┐
    │              bus (publish/subscribe)               │
    └───────▲──────────────▲──────────────▲─────────────┘
            │              │              │
     ┌──────┴─────┐ ┌──────┴─────┐ ┌──────┴─────┐
     │  runtime   │ │  ui views  │ │ platform   │
     │ (loop,     │ │ (pure      │ │ (buttons,  │
     │  timers)   │ │  render)   │ │  sensors)  │
     └────────────┘ └────────────┘ └────────────┘

- **services/** own *state + policy* (what to show, when it changes). Pure:
  no board imports, no I/O, no globals. They are the whole reason tests stay
  simple: each service can be driven and asserted in isolation.
- **platform/** owns *how to talk to hardware* (buttons, sensor reads,
  display). It never decides anything; it exposes events/frames.
- **ui/** owns *presentation*: mapping (state, event) → pixels. Pure code —
  every screen is a function of (state, tick) → framebuffer.
- **runtime/** owns *concurrency and cadence*: the loop that ticks, the
  sleep/schedule boundary, the event dispatch. That is the only place that
  knows there is a wall clock, an event loop, or an RTOS at all.

## Runtime strategy

Keep all logic decoupled from the scheduler so the backing implementation is
a swap, not a rewrite:

- **v1 (start here):** cooperative scheduler in `runtime/scheduler.py` —
  a list of `(next_due, callable)` tasks multiplexed by `select`-able sleep.
  This is MicroPython-faithful (no threads, no asyncio on the critical path)
  and is enough to get *all* downstream screens working under one model.
- **v2 (later, when v1 hits a timing or complexity ceiling):** swap the
  runtime to `asyncio`-backed tasks, or add a worker thread for anything
  unexpectedly slow (network, sensors). The interface the rest of the code
  sees (`runtime.call_later`, `runtime.call_periodic`, `runtime.now`) does
  not change.

We deliberately do *not* chase async/await inside the application for now.
It complicates every callback into a state machine for a scheduling problem
that a single cooperative loop solves cleanly at this scale.

## Module layout

    src/
      runtime.py      scheduler + event loop glue (tiny)
      bus.py          tiny pub/sub used by services to notify ui
      platform/       board drivers (buttons, sensors, display, wifi)
      services/       clock, weather, co2, alerts — pure logic
      ui/             renderers + swimlanes between them
    main.py           bootstrap: build runtime, wire services ↔ ui

The board-facing `main.py` shrinks to composition. Every other module is
host-testable in isolation, which is what turns "did my change break the
co2 strip?" into a unit test instead of a deploy-and-observe cycle.

## Migration plan (small steps, each shippable)

1. Introduce `runtime.py` (scheduler) and make the existing screens run on
   it. No behavior change.
2. Extract `services/clock.py`, `services/weather.py`, `services/co2.py` as
   pure modules; move the logic in `main.py` into them.
3. Add the bus and route events (button, tick, sensor ready) through it;
   delete direct imports between features.
4. Only then consider a runtime upgrade (threads or asyncio) — by then the
   difference is a one-file change, not a refactor of every screen.

## Testing

Each migration step keeps the existing sim (`sim/`) and its golden tests
green — that is the acceptance rule for the whole plan. New: `services/`
gets direct unit tests (no board, no sim needed), which is the fastest
possible feedback loop for the aggregation/trend logic we keep iterating on.

## Out of scope / deferred

- Real-time scheduling, watchdog integration, OTA.
- Anything that requires more than screen-state + a couple of I/O events
  (if that ever changes, revisit the runtime choice above).
