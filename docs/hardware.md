# Hardware resources: what's available and what the clock uses

Galactic Unicorn = Raspberry Pi Pico W (RP2040 + Infineon CYW43439 WiFi) with a
53x11 LED matrix, 1 W speaker/amp, buttons and an ambient light sensor.

Note on TLS: the RP2040 has **no hardware crypto accelerator** — HTTPS/TLS is
software (mbedTLS) inside Pimoroni's MicroPython firmware. The CA certs on the
flash (`isrg-root-x1.pem`, `gts-root-r4.pem`) are for verifying TLS in software.

## RP2040 resources

| Resource | Total | Used by the clock | Free |
|---|---|---|---|
| CPU clock | 125 MHz (measured `machine.freq()`); RP2040 rated to 133 MHz, SDK-certified 200 MHz; set at runtime with `machine.freq()`, resets on boot | stock 125 MHz | can overclock in `main.py` if ever needed |
| Cortex-M0+ cores | 2 | core 0 (MicroPython, all app code) | **core 1 — idle**, usable via `_thread.start_new_thread` |
| PIO blocks x state machines | 2 x 4 (8 SMs) | **1 SM** for the LED matrix (`pio_claim_unused_sm` once for the bitstream; autopull feeds it, no DMA), +1 more only while I2S audio plays | 6–7 SMs |

Buttons are plain GPIOs (see table below), so press interrupts work:
`Pin(n, Pin.IN, Pin.PULL_UP).irq(handler, Pin.IRQ_FALLING)` — IO_IRQ_BANK0 is
already enabled (measured). The frozen driver's `is_pressed()` only polls.

The onboard LED is the CYW43439's WL_GPIO0 (not a RP2040 pin): control it with
`machine.Pin("LED", machine.Pin.OUT)` — verified on the board.
| DMA channels | 16 | **none active — verified on the board** (probed all 16 CTRL EN/BUSY bits after every `gu.update()` for 350 frames with WiFi on: zero). Source-confirmed: the matrix PIO program uses autopull (threshold 8) and the CPU just fills the PIO FIFO; the cyw43 radio SPI is IRQ-driven. The GalacticUnicorn C++ lib *claims* DMA channels only for I2S audio (`play_synth`/`play_sample`), idle when silent. USB has its own separate DMA controller. | all 16 free (2–3 claimed only while audio plays) |
| SRAM | 264 KB | firmware + heap (TLS buffers are the big consumers) | — |
| UART | 2 | none (console is USB, not UART) | 2 |
| SPI | 2 | SPI0: CYW43439 radio (GP24/GP25/GP29) | SPI1 |
| I2C | 2 | I2C0 on GP4/GP5: SCD41 @ 0x62 (frozen `pimoroni_i2c`/`breakout_scd41`) | I2C1 |

DMA note: the RP2040 DMA can be paced by I2C DREQs (`DREQ_I2C0_TX/RX`,
`DREQ_I2C1_TX/RX`), so DMA-assisted I2C is possible at the hardware level —
but the SDK/MicroPython I2C driver polls/IRQs and does not use DMA (confirmed
by probe: I2C0_IRQ fires, no DMA channel busy). In practice you'd DMA only the
data phase; the address/command phase stays on the CPU.
| PWM | 16 slices | speaker/amp audio (frozen driver `play_synth`/`play_sample`) | most |
| ADC (12-bit, 500 ksps) | 4 ch + temp | ch2 GP28 = light sensor (`gu.light()`), ch4 = die temp, ch3 GP29 = VSYS/3 (radio conflict) | **none free**: ch0 = GP26 = BRIGHTNESS_DOWN button, ch1 = GP27 = SLEEP button |
| USB 1.1 device | 1 | mpremote REPL / deploy | — |
| Watchdog | 1 | unused | 1 |
| IRQs | 32/core (NVIC) | enabled on core 0 (measured NVIC ISER = 0x0000A02C): TIMER_IRQ_2/3 (MicroPython ticks/alarms), USBCTRL_IRQ (mpremote), IO_IRQ_BANK0 (GPIO: cyw43 host-wake + buttons), SIO_IRQ_PROC0 (inter-core). **Not** enabled: PIO IRQs (FIFO polled), I2C0_IRQ (SCD41 polled), DMA_IRQs (no audio playing), ADC_IRQ_FIFO (ADC polled) | plenty |

## Pico W radio (CYW43439)

- Full-MAC chip: it runs 802.11 itself; the RP2040 runs lwIP (TCP/IP) and talks
  to the radio over half-duplex SPI on **GP24/GP25/GP29** (board-internal, not on
  the header). `WL_REG_ON` = GP23 powers the chip (`wlan.active(False)`).
- **GP29 conflict:** it is also ADC3 (VSYS/3 divider). With WLAN active the
  radio owns the pin and ADC3 reads ~0 V; measured 4.80 V with the radio off,
  0.05 V with it on. Hence VSYS is only measurable at boot / with the radio
  powered down (see `read_vsys()` in `main.py`).
- Asyncio sockets are lwIP sockets in non-blocking mode on core 0 — DMA on the
  radio SPI does not make them parallel. True parallelism for network I/O needs
  core 1 (`_thread`).

## Galactic Unicorn board extras

- Light sensor: phototransistor divider on **GP28 (ADC2)**, read via the frozen
  `GalacticUnicorn.light()` (0..4095 float). Behind dark acrylic, so values are
  small (measured ~40/4095 indoors).
- Buttons (all read via `gu.is_pressed(GalacticUnicorn.SWITCH_*)`, frozen driver;
  brightness/volume/sleep are software-handled by the driver, the rest are free
  for user code):

  | Button | GPIO | | Button | GPIO |
  |---|---|---|---|---|
  | A | GP0 | | volume up | GP7 |
  | B | GP1 | | volume down | GP8 |
  | C | GP3 | | brightness up | GP21 |
  | D | GP6 | | brightness down | GP26 |
  | sleep | GP27 | | (light sensor | GP28) |
- Speaker: 1 W amp, PWM-driven audio via the frozen driver.
- Qw/ST (STEMMA QT) connectors: GP4/GP5 I2C — SCD41 CO2 sensor at 0x62.

## Provenance

Findings in this document are based on an agent's exploration of: the RP2040
datasheet and Pico SDK register headers (DREQ/IRQ tables), the Pimoroni
MicroPython firmware source (`pimoroni/unicorn`, `pimoroni/pimoroni-pico`
`libraries/galactic_unicorn/` and `micropython/modules/galactic_unicorn/`),
and live inspection of the board's memory-mapped registers via
`machine.mem32` (DMA channel CTRL at 0x50000000, NVIC ISER/ISPR at
0xE000E100/0xE000E200) plus `machine.freq()`.

## Current usage summary (main.py)

core 0 runs everything: rendering (PIO matrix), WiFi/NTP/open-meteo (lwIP over
the radio), SCD41 over I2C, ALS + die temp over ADC. Core 1, SPI1, I2C1, UARTs,
watchdog, and 7 PIO state machines are free for future use (e.g. offloading the
blocking weather fetch to core 1, or a status endpoint).
