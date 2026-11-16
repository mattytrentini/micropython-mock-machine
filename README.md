# micropython-mock-machine

A MicroPython library providing generic `machine` and modeled `network` state for driver tests and Unix simulation. Version 1.1.1, MIT licensed.

This is a simulation foundation, not an ESP32 emulator or an N30/CO16 application bring-up. It supplies no board-specific chip, display-controller, meter or protocol models. Native MicroPython `asyncio`, `micropython.RingIO`, `framebuf`, time, GC and host networking remain native. Simulated results do not validate electrical behavior, timing, calibration or physical hardware.

## Features

Currently `mock_machine` implements:

- **I2C** - Inter-Integrated Circuit bus with device simulation
  - `init`, `deinit`, `scan`
  - `readfrom`, `readfrom_into`, `writeto`
  - `readfrom_mem`, `readfrom_mem_into`, `writeto_mem`
  - `add_device` (for simulating multiple devices on the bus)

- **SPI** - Serial Peripheral Interface
  - `init`, `deinit`
  - `read`, `readinto`, `write`, `write_readinto`

- **Pin** - Digital I/O pins
  - `init`, `value`, `on`, `off`, `high`, `low`
  - `irq` with IRQ_RISING and IRQ_FALLING triggers
  - `mode` configuration
  - `Pin.board` and `Pin.cpu` namespaces for pin name resolution

- **ADC** - Analog to Digital Converter
  - `read_u16`

- **PWM** - Pulse Width Modulation
  - Frequency and duty cycle control

- **UART** - Universal Asynchronous Receiver/Transmitter
  - Nonblocking streams, bounded capture, consuming responders, flush/close and asyncio polling

- **Timer** - Hardware timers
  - Periodic and one-shot modes

- **WDT** - Watchdog Timer
  - Timeout and feed operations

- **RTC** - Real Time Clock
  - Wakeup alarms and datetime

Additional utilities:
- **I2CDevice** - Helper class for simulating I2C devices with register-based interfaces
- **RegisterBasedI2CDevice** - Extended I2CDevice for testing register-based I2C devices (RTCs, sensors)
- **Signal** - Digital signal with inversion support
- **freq** - Explicit virtual CPU frequency, initially unknown (`0`); no host CPU changes
- **reset_simulation** - Session isolation for registries, aliases, frequency and owned timers

## Installation

### Using mip (recommended)

```python
import mip
mip.install("github:mattytrentini/micropython-mock-machine", version="v1.1.1")
```

### Manual installation

The manifest installs `mock_machine.py`, `mock_network.py`, the MIT license and pinned `logging` 0.6.2. Manual users must install `logging` 0.6.2 separately and copy the two modules to their MicroPython library path. The implementation requires native `micropython.RingIO` (use a current MicroPython Unix build, not CPython or the old v1.23.0 CI image).

## Usage

### Basic Example

```python
# In your test file
import mock_machine

# Register mock_machine as the machine module
mock_machine.register_as_machine()

# Now any import of 'machine' will use the mock
import machine

# Create mock hardware
i2c = machine.I2C(0)
pin = machine.Pin(0, machine.Pin.OUT)

# Use as normal
pin.value(1)
assert pin.value() == 1
```

### Simulating I2C Devices

```python
import mock_machine
from mock_machine import I2C, I2CDevice

# Create I2C bus
i2c = I2C(0)

# Create a mock device at address 0x68
device = I2CDevice(addr=0x68, i2c=i2c)

# Set up register values
device.register_values[0x00] = b'\x12\x34'  # WHO_AM_I register
device.register_values[0x01] = b'\x00\x00'  # Control register

# Your driver can now read from the device
data = i2c.readfrom_mem(0x68, 0x00, 2)
assert data == b'\x12\x34'
```

### Pin Interrupts

```python
import mock_machine
import asyncio

mock_machine.register_as_machine()
import machine

# Create a pin with interrupt
pin = machine.Pin(0, machine.Pin.IN)

# Set up interrupt handler
def pin_handler(pin):
    print(f"Pin interrupt! Value: {pin.value()}")

pin.irq(handler=pin_handler, trigger=machine.Pin.IRQ_RISING)

# Simulate pin change
pin.value(0)  # No interrupt
pin.value(1)  # Triggers interrupt (rising edge)
```

### SPI Communication

```python
import mock_machine
mock_machine.register_as_machine()
import machine

# Create SPI bus
spi = machine.SPI(0)

# Set up mock responses
spi.read_buf = b'\x01\x02\x03\x04'

# Test your SPI driver
data = spi.read(4)
assert data == b'\x01\x02\x03\x04'

# Check what was written
spi.write(b'\xAA\xBB')
assert spi.write_buf == b'\xAA\xBB'
```

### Stable state and isolated sessions

Call `reset_simulation()` before each independent test/application session. It clears pin and controller registries, aliases, ADC samples and virtual frequency, disables old resources, and cancels owned Timer/RTC/WDT tasks. It does not reboot the host, restore `sys.modules`, or reset the separate `mock_network` module; the embedding runtime owns those actions.

`register_as_machine()` installs the actual imported module, including qualified imports. Install it before importing consumers of `machine`.

```python
mock_machine.reset_simulation()
mock_machine.freq(120_000_000)  # explicit virtual state, not a board default
machine.Pin.configure_aliases({"BUTTON": 7})  # before any Pin construction
button = machine.Pin("BUTTON", machine.Pin.IN, pull=machine.Pin.PULL_UP)
button.inject(0)
assert machine.Pin(7) is button
assert button.snapshot()["value"] == 0
```

Pin lookup preserves configuration, sampled level and IRQs; only explicitly supplied constructor/init arguments change state. `pull=None` disables the modeled pull. Aliases are one-level names to integer/string canonical IDs; chains, cycles and live remapping are rejected. Existing `Pin.board.configure(pins_csv)` / `Pin.cpu` helpers remain supported.

Pins model a sampled digital value, not electrical contention: pulls do not force levels, an undriven level starts as `None`, and both `value(0/1)` and `inject(0/1)` change the sample. `inject(None)` releases it to unknown. Only actual `0 -> 1` / `1 -> 0` changes trigger matching IRQ masks, through native `micropython.schedule`; unknown transitions do not. Hard IRQs are unsupported.

I2C/SPI/UART construction with the same controller ID (including the default `None`) returns shared state. Plain lookup never reconfigures, reactivates or erases state. Explicit options or `init()` reconfigure/re-enable; omitted settings remain unchanged. `deinit()` rejects subsequent I/O until explicit reinitialization. I2C retains its attached devices across deinit/init; missing addresses raise `OSError`.

SPI supports byte-wide transfers. Supply `read_buf` for repeatable responses, or `reads` for a finite sequence consumed per call; absent/short responses raise `OSError` instead of fabricating bytes. `write_buf` retains the last transfer's final 256 bytes, `writes` retains at most 16 such captures, and `num_reads` / `num_writes` count transfers. These are bounded observations, not a full trace. `reset()` clears RX fixtures and observations without reconfiguring the controller.

### UART peers and lifecycle

```python
uart = machine.UART(1, baudrate=19200, txbuf=32, rxbuf=32)
uart.set_responder(lambda tx: tx.upper())  # generic consuming peer, not a protocol model
for _ in range(100):
    assert uart.write(b"ping") == 4
    assert uart.read() == b"PING"
```

The responder receives immutable accepted TX bytes and returns RX bytes or `None`. Exchanges are synchronous; a consuming peer cannot fill a stale TX capture ring. With a responder, `get_written_data()` drains only the latest exchange's bounded suffix (up to `txbuf`). Setting/removing a responder clears old TX capture.

Without a responder, writes fill bounded TX capture, can accept only a prefix, and return `None` when full; `get_written_data()` drains it. No peer/`None` response means **no RX data**, not a fabricated reply. RX injection and responder replies are atomic: overflow raises `OSError(ENOBUFS)` and preserves existing RX data.

Reads are always nonblocking: empty `read`, `readinto` and `readline` return `None` (not EOF), while zero-length reads return empty bytes/zero. Constructor/init options are recorded, not real baud timing, parity, inversion or flow-control physics. `timeout` / `timeout_char` do not block execution.

`txdone()` is false for pending unconsumed capture; `flush()` completes virtual TX without deleting its observation or inventing a reply. Responder TX completes synchronously. Draining capture also consumes pending TX. Poll respects requested read/write masks; full unconsumed TX capture is not writable. `close()` / `deinit()` discard buffers and the responder, disable I/O and report invalid polling until `init()`. Resizing a nonempty buffer raises `OSError(EAGAIN)` rather than discarding data.

Native Unix `select.poll` asks for an OS file descriptor, not just stream poll
flags. The UART creates a private local Unix-socket readiness bridge lazily when
polled; RX arrival and bounded TX backpressure wake the real event loop. No
external network endpoint is opened. This path needs writable `/tmp` and is
released by `deinit()`/`reset_simulation()`.

The separate `mock_network` models interface/link/configuration intent only; it does not emulate Wi-Fi/LAN hardware or replace native Unix sockets/DNS. Unsupported operations are not evidence of hardware support. Older auxiliary classes retain their limited test-helper semantics, not MCU emulation.


## Examples

The `examples/` directory contains sample drivers with tests:
- `hardware_revision.py` - Reading hardware revision from I2C EEPROM
- `tmp117.py` - TMP117 temperature sensor driver with I2C communication

## Testing

Use the native MicroPython runner and dependencies described in [test/README.md](test/README.md). The suite requires `unittest`, pinned `logging` 0.6.2, native RingIO/schedule/asyncio, a writable working directory for CSV/import fixtures, and the repository root on `MICROPYPATH`; plain CPython/pytest is not a substitute.

The consumer-visible regression suite is `test/test_machine_contract.py`; existing machine/example tests remain part of the runner.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

Copyright (c) 2020-2024 Planet Innovation Pty Ltd
