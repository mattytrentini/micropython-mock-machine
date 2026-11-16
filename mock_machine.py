# MIT license; Copyright (c) 2020-2025, Planet Innovation
# 436 Elgar Road, Box Hill, 3128, VIC, Australia
# Phone: +61 3 9945 7510
#

"""
Mock machine module that can be used in unit tests to test drivers.
"""

__version__ = "1.1.1"

import errno
import io
import logging
import time

try:
    from typing import Dict, Optional
except ImportError:
    pass

import asyncio
import micropython

log = logging.getLogger("mock_machine")

# Not concerned about unused arguments in mocks
# pylint: disable=unused-argument
# pylint: disable=no-member

_UNSET = object()
_cpu_hz = 0


def freq(value=None):
    """Read/set virtual CPU Hz; this never changes the host CPU."""
    global _cpu_hz
    if value is None:
        return _cpu_hz
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("frequency must be a positive integer")
    _cpu_hz = value


def _check_active(resource):
    if not resource._active:
        raise OSError(errno.ENODEV)


def register_as_machine():
    """
    This will register mock_machine as machine so it can be imported by other
    modules expecting `import machine` to work.
    """
    import sys

    log.warning("All imports of machine are mocked from here on")
    sys.modules["machine"] = sys.modules[__name__]


# machine module interfaces

SOFT_RESET = 0
PWRON_RESET = 1
HARD_RESET = 2
WDT_RESET = 3
DEEPSLEEP_RESET = 4
__reset_cause__ = PWRON_RESET


def reset_cause():
    """
    https://docs.micropython.org/en/latest/library/machine.html#machine.reset_cause
    """
    return __reset_cause__


class ADC:
    pin_adc_map: Dict[Pin, int] = {}  # noqa: F821
    """
    Unittest support class for machine.ADC.

    https://docs.micropython.org/en/latest/library/machine.ADC.html
    """

    def __init__(self, pin):
        self.pin = pin

    # Methods
    def init(self, *, sample_ns, atten):
        """
        Apply the given settings to the ADC.

        Only those arguments that are specified will be changed.
        """

    def block(self):
        """
        Return the ADCBlock instance associated with this ADC object.
        """

    def read_u16(self):
        """
        Take an analog reading and return an integer in the range 0-65535.

        The return value represents the raw reading taken by the ADC.
        """
        if self.pin in ADC.pin_adc_map:
            return ADC.pin_adc_map[self.pin]

        return 0

    def read_uv(self):
        """
        Take an analog reading and return an integer value with units of microvolts.

        It is up to the particular port whether or not this value is calibrated, and how
        calibration is done.
        Note: stm32 port does not include this functionality as of August 2023.
        """
        return self.value_uv


class I2C:
    """
    Unittest support class for machine.I2C.

    https://docs.micropython.org/en/latest/library/machine.I2C.html
    """

    _controllers = {}

    def __new__(cls, id=None, **kwargs):
        if id in cls._controllers:
            return cls._controllers[id]
        self = super().__new__(cls)
        cls._controllers[id] = self
        return self

    def __init__(self, id=None, *, scl=_UNSET, sda=_UNSET, freq=_UNSET):
        if not hasattr(self, "devices"):
            self.id = id
            self.devices = {}
            self.scl = self.sda = None
            self.freq = 400000
            self._active = True
        if scl is not _UNSET or sda is not _UNSET or freq is not _UNSET:
            self.init(scl, sda, freq=freq)

    # Device management methods
    def add_device(self, device):
        """
        Add I2CDevice at address I2CDevice.address.
        """
        _check_active(self)
        if device.addr in self.devices:
            raise ValueError("Device with given address already on bus.")
        self.devices[device.addr] = device

    # General methods
    def init(self, scl=_UNSET, sda=_UNSET, *, freq=_UNSET):
        """Re-enable/reconfigure without detaching devices."""
        if freq is not _UNSET:
            if not isinstance(freq, int) or freq <= 0:
                raise ValueError("frequency must be positive")
            self.freq = freq
        if scl is not _UNSET:
            self.scl = scl
        if sda is not _UNSET:
            self.sda = sda
        self._active = True

    def deinit(self):
        """Disable transfers; init() explicitly re-enables the bus."""
        self._active = False

    def scan(self):
        """
        Scan I2C for responding devices.

        Scans all I2C addresses between 0x08 and 0x77 inclusive and return a list of those that
        respond.

        Returns a list of addresses that responded to the scan.
        """
        _check_active(self)
        scan_list = []
        for addr in self.devices:
            if 0x08 <= addr <= 0x77:
                scan_list.append(addr)
        return scan_list

    # Standard bus operations
    def readfrom(self, addr, nbytes, stop=True):
        """
        Read nbytes from the peripheral specified by addr.

        If stop is true then a STOP condition is generated at the end of the transfer.

        Returns a bytes object with the data read.
        """
        _check_active(self)
        if addr not in self.devices:
            raise OSError(errno.ENODEV)
        return self.devices[addr].readfrom(nbytes, stop)

    def readfrom_into(self, addr, buf, stop=True):
        """
        Read into buf from the peripheral specified by addr.

        The number of bytes read will be the length of buf. If stop is true then a STOP condition
        is generated at the end of the transfer.

        The method returns None.
        """
        _check_active(self)
        if addr not in self.devices:
            raise OSError(errno.ENODEV)
        return self.devices[addr].readfrom_into(buf, stop)

    def writeto(self, addr, buf, stop=True):
        """
        Write the bytes from buf to the peripheral specified by addr.

        If a NACK is received following the write of a byte from buf then the remaining bytes are
        not sent. If stop is true then a STOP condition is generated at the end of the transfer,
        even if a NACK is received.

        The function returns the number of ACKs that were received.
        """
        _check_active(self)
        if addr not in self.devices:
            raise OSError(errno.ENODEV)
        return self.devices[addr].writeto(buf, stop)

    # Memory operations
    def readfrom_mem(self, addr, memaddr, nbytes, *args, addrsize=8):  # pylint: disable=unused-argument
        """
        Read nbytes from the peripheral specified by addr, starting at memaddr.

        Starting from the memory address specified by memaddr. The argument addrsize specifies the
        address size in bits.

        Returns a bytes object with the data read.
        """
        _check_active(self)
        if addr not in self.devices:
            raise OSError(errno.ENODEV)
        return self.devices[addr].readfrom_mem(memaddr, nbytes)

    def readfrom_mem_into(self, addr, memaddr, buf, *args, addrsize=8):
        """
        Read into buf from the peripheral specified by addr, starting at memaddr.

        The number of bytes read is the length of buf. The argument addrsize specifies the address
        size in bits.

        The method returns None.
        """
        _check_active(self)
        if addr not in self.devices:
            raise OSError(errno.ENODEV)
        return self.devices[addr].readfrom_mem_into(memaddr, buf)

    def writeto_mem(self, addr, memaddr, buf, *args, addrsize=8):
        """
        Write buf to the peripheral specified by addr, starting at memaddr.

        The number of bytes written is the length of buf. The argument addrsize specifies the
        address size in bits.

        The method returns None.
        """
        _check_active(self)
        if addr not in self.devices:
            raise OSError(errno.ENODEV)
        self.devices[addr].writeto_mem(memaddr, buf)


class I2CDevice:
    """
    A single I2C device added to a mock_machine.I2C bus.

    This is a utility class for simulating a real device, not
    representative of a "real" micropython machine class.
    """

    def __init__(self, addr, i2c):
        self.addr = addr

        # Dict of buffers used for addressed operations
        self.register_values = {}

        # A buffer used for non-addressed reads
        self.readbuf = bytes()

        # Add self to I2C
        i2c.add_device(self)

    # Standard bus operations
    def readfrom(self, nbytes, stop=True):
        """
        Read nbytes from the peripheral.

        Returns a bytes object with the data read.
        """
        if len(self.readbuf) < nbytes:
            raise ValueError(f"Insufficient bytes to read nbytes={nbytes} with readfrom()")
        buf = self.readbuf[:nbytes]
        return buf

    def readfrom_into(self, buf, stop=True):
        """
        Read into buf from the peripheral.

        The number of bytes read will be the length of buf.

        The method returns None.
        """
        if len(self.readbuf) < len(buf):
            raise ValueError(f"Insufficient bytes to read {len(buf)} with readfrom_into()")
        buf[:] = self.readbuf[: len(buf)]

    @staticmethod
    def writeto(buf, stop=True):
        """
        Write the bytes from buf to the peripheral.

        If a NACK is received following the write of a byte from buf then the remaining bytes are
        not sent.

        If `writeto` is required for a peripheral, then this function will need to be overridden
        with desired functionality. Otherwise this function defaults to ACK for all bytes.

        The function returns the number of ACKs that were received.
        """
        return len(buf)

    # Memory operations
    def readfrom_mem(self, memaddr, nbytes):
        """
        Read nbytes from the peripheral starting at memaddr.

        Returns a bytes object with the data read.
        """
        if memaddr not in self.register_values:
            raise IndexError(
                f"Unknown memory address memaddr={memaddr}",
            )
        if len(self.register_values[memaddr]) < nbytes:
            raise ValueError(f"Insufficient bytes to read nbytes={nbytes} from memaddr={memaddr}")
        buf = self.register_values[memaddr][:nbytes]
        return buf

    def readfrom_mem_into(self, memaddr, buf):
        """
        Read into buf from the peripheral specified by addr, starting at memaddr.

        The number of bytes read is the length of buf. The argument addrsize specifies the address
        size in bits.

        The method returns None.
        """
        if memaddr not in self.register_values:
            raise IndexError(
                f"Unknown memory address memaddr=0x{memaddr:x}",
            )
        if len(self.register_values[memaddr]) < len(buf):
            raise ValueError(
                f"Insufficient bytes to read len(buf)={len(buf)} from memaddr={memaddr}"
            )
        buf[:] = self.register_values[memaddr][: len(buf)]

    def writeto_mem(self, memaddr, buf):
        """
        Write buf to the peripheral specified by addr, starting at memaddr.

        The number of bytes written is the length of buf. The argument addrsize specifies the
        address size in bits.

        The method returns None.
        """
        self.register_values[memaddr] = buf


class RegisterBasedI2CDevice(I2CDevice):
    """
    I2C device that uses register-based protocol (common for RTCs, sensors, etc.).

    This device simulates the common I2C protocol where:
    1. Master writes register address
    2. Master reads/writes data from/to that register

    This matches the protocol used by many I2C devices like the PCF85063 RTC.
    """

    def __init__(self, addr, i2c, register_count=32):
        """
        Initialize register-based I2C device.

        Args:
            addr: I2C address of the device
            i2c: I2C bus to attach to
            register_count: Number of registers (default 32)
        """
        super().__init__(addr, i2c)
        self.registers = bytearray(register_count)
        self.current_register = None

    def writeto(self, buf, stop=True):
        """
        Write bytes to device.

        First byte is register address, subsequent bytes are written to registers.
        """
        if len(buf) == 0:
            return 0

        # First byte is register address
        self.current_register = buf[0]

        # If more bytes, write them to registers
        if len(buf) > 1:
            for i, value in enumerate(buf[1:]):
                reg_addr = self.current_register + i
                if reg_addr < len(self.registers):
                    self.registers[reg_addr] = value

        return len(buf)

    def readfrom(self, nbytes, stop=True):
        """Read through the same register protocol as readfrom_into."""
        buf = bytearray(nbytes)
        self.readfrom_into(buf, stop)
        return bytes(buf)

    def readfrom_into(self, buf, stop=True):
        """
        Read bytes from device into buffer.

        Reads from the current register address set by previous writeto.
        """
        if self.current_register is None:
            raise ValueError("No register address set")

        for i in range(len(buf)):
            reg_addr = self.current_register + i
            if reg_addr < len(self.registers):
                buf[i] = self.registers[reg_addr]
            else:
                buf[i] = 0


class Memory:
    """
    https://docs.micropython.org/en/latest/library/machine.html#memory-access
    """

    def __init__(self, data):
        self.data = data

    def __getitem__(self, idx):
        return self.data


mem8 = Memory(0xFF)
mem16 = Memory(0xFFFF)
mem32 = Memory(0xFFFFFFFF)


class Pin:
    """
    Unittest support class for machine.Pin

    Allows manual setting of input or output pin's value.

    https://docs.micropython.org/en/latest/library/machine.Pin.html

    """

    # mode
    IN = 0
    OUT = 1
    OPEN_DRAIN = 2
    ALT = 3
    ALT_OPEN_DRAIN = 4
    ANALOG = 5

    # pull
    PULL_UP = 0
    PULL_DOWN = 1

    IRQ_RISING = 1
    IRQ_FALLING = 2

    pins: Dict[str, "Pin"] = {}
    _aliases = {}

    @classmethod
    def configure_aliases(cls, mapping):
        """Install one-level board aliases before constructing pins."""
        aliases = dict(mapping)
        for alias, canonical in aliases.items():
            if not isinstance(alias, str) or not alias:
                raise ValueError("aliases must be nonempty strings")
            if isinstance(canonical, bool) or not isinstance(canonical, (int, str)):
                raise ValueError("canonical pin IDs must be integers or strings")
            if canonical in aliases:
                raise ValueError("alias chains and cycles are ambiguous")
        if aliases == cls._aliases:
            return
        if cls.pins:
            raise ValueError("configure aliases before creating pins")
        cls._aliases = aliases

    """
    Configuring Pin.board and Pin.cpu definitions.
    The actual pin names for your project can be configured
    in this mock Pin class by providing your real board pins.csv file like:
    `Pin.board.configure("../path/to/my-board/pins.csv")`
    After this your mock Pin.board.<PIN_NAME> and Pin.cpu.<GPIO_NAME>
    attributes will work similar to the real hardware.
    """

    class _PinNamespace:
        """Base class for pin name namespaces (board/cpu)"""

        def __init__(self, column_index: int, namespace_name: str):
            self._pins: Dict[str, str] = {}
            self._magic_mode: bool = True
            self._column_index = column_index
            self._namespace_name = namespace_name

        def _load_pins(self, pins_csv_path: Optional[str] = None) -> None:
            """Load pins from CSV file

            Args:
                pins_csv_path: Explicit path to pins.csv file
                              - If provided and exists: STRICT mode (only defined pins allowed)
                              - If None or file missing: MAGIC mode (any pin name works)

            The pins.csv format expected is:
                BOARD_PIN,CPU_PIN
                # Comments start with #
                -HIDDEN_PIN,GPIO_yyy  # Pins starting with - are skipped
            """
            self._pins = {}

            if pins_csv_path is None:
                # No CSV specified - use magic mode for maximum compatibility
                self._magic_mode = True
                return

            try:
                with open(pins_csv_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        # Skip comments and empty lines
                        if not line or line.startswith("#"):
                            continue

                        # Parse CSV: BOARD_PIN,CPU_PIN
                        parts = line.split(",")
                        if len(parts) >= 2:
                            board_pin = parts[0].strip()
                            cpu_pin = parts[1].strip()
                            # Skip hidden pins (prefixed with -)
                            if not board_pin.startswith("-"):
                                # Store mapping based on namespace type
                                if self._column_index == 0:
                                    # Pin.board: board name → CPU pin
                                    self._pins[board_pin] = cpu_pin
                                else:
                                    # Pin.cpu: CPU pin → CPU pin
                                    self._pins[cpu_pin] = cpu_pin

                # CSV loaded successfully - use strict mode
                self._magic_mode = False
                log.info(
                    f"Pin.{self._namespace_name} configured with "
                    + f"{len(self._pins)} pins from {pins_csv_path}"
                )

            except OSError as e:
                # CSV file not found - fall back to magic mode
                self._magic_mode = True
                log.warning(
                    f"Pin.{self._namespace_name}: Could not load "
                    + f"{pins_csv_path}, using magic mode: {e}"
                )

        def __getattr__(self, name: str) -> str:
            """Get a pin name from this namespace

            In strict mode (CSV loaded), only returns defined pins.
            In magic mode (no CSV), returns any requested name.
            """
            if name.startswith("_"):
                # Don't intercept private attributes
                raise AttributeError(f"Pin.{self._namespace_name} has no attribute '{name}'")
            if self._namespace_name == "board" and name in Pin._aliases:
                return Pin._aliases[name]
            if name in self._pins:
                return self._pins[name]
            if self._magic_mode:
                return name  # Return any requested name
            raise AttributeError(f"Pin.{self._namespace_name}.{name} not defined in pins.csv")

    class _PinBoard(_PinNamespace):
        """Board pin names namespace

        Maps board pin names to CPU pin names.
        Example: Pin.board.SPI5_SCK_NEN returns 'GPIO_AD_08'
        """

        def __init__(self):
            super().__init__(column_index=0, namespace_name="board")

        def configure(self, pins_csv_path: Optional[str] = None) -> None:
            """Configure Pin.board and Pin.cpu with pins from CSV file"""
            self._load_pins(pins_csv_path)
            # Also configure cpu namespace
            Pin.cpu._load_pins(pins_csv_path)  # noqa: F821

    class _PinCPU(_PinNamespace):
        """CPU pin names namespace

        Maps CPU pin names to themselves (identity mapping).
        Example: Pin.cpu.GPIO_AD_08 returns 'GPIO_AD_08'
        """

        def __init__(self):
            super().__init__(column_index=1, namespace_name="cpu")

    board = _PinBoard()
    cpu = _PinCPU()

    # pylint: disable=redefined-builtin
    def __new__(cls, id, mode=_UNSET, pull=_UNSET, value=_UNSET, drive=_UNSET, alt=_UNSET):
        if isinstance(id, Pin):
            return id
        id = cls._aliases.get(id, id)
        if isinstance(id, bool) or not isinstance(id, (int, str)):
            raise ValueError("pin ID must be an integer or string")
        if id in cls.pins:
            return cls.pins[id]
        self = super().__new__(cls)
        self.id = id
        cls.pins[id] = self
        return self

    # pylint: disable=redefined-builtin
    def __init__(self, id, mode=_UNSET, pull=_UNSET, value=_UNSET, drive=_UNSET, alt=_UNSET):
        if not hasattr(self, "_active"):
            self._active = True
            self._value = None
            self._mode = self.IN
            self._pull = None
            self._alt = None
            self._drive = None
            self._irq_handler = None
            self._irq_trigger = 0
            self._irq_generation = 0
        self.init(mode=mode, pull=pull, alt=alt, value=value, drive=drive)

    def init(self, mode=_UNSET, pull=_UNSET, alt=_UNSET, value=_UNSET, drive=_UNSET):
        _check_active(self)
        if mode is not _UNSET:
            self._mode = mode
        if pull is not _UNSET:
            self._pull = pull
        if alt is not _UNSET:
            self._alt = alt
        if drive is not _UNSET:
            self._drive = drive
        if value is not _UNSET:
            self.inject(value)

    def value(self, new_value=None):
        _check_active(self)
        if new_value is None:
            return self._value
        self.inject(new_value)

    def inject(self, value):
        """Set the sampled level; None means unknown/released, not an edge."""
        _check_active(self)
        if value is not None and value not in (0, 1):
            raise ValueError("pin level must be 0, 1 or None")
        old = self._value
        self._value = None if value is None else int(value)
        edge = 0
        if old == 0 and self._value == 1:
            edge = self.IRQ_RISING
        elif old == 1 and self._value == 0:
            edge = self.IRQ_FALLING
        if edge & self._irq_trigger and self._irq_handler:
            micropython.schedule(self._dispatch_irq, (self._irq_handler, self._irq_generation))

    def _dispatch_irq(self, event):
        handler, generation = event
        if self._active and generation == self._irq_generation:
            handler(self)

    def snapshot(self):
        _check_active(self)
        return {"id": self.id, "mode": self._mode, "pull": self._pull, "value": self._value}

    def on(self):
        self.value(1)

    def off(self):
        self.value(0)

    def high(self):
        self.value(1)

    def low(self):
        self.value(0)

    def irq(
        self, handler=None, trigger=IRQ_FALLING | IRQ_RISING, priority=1, wake=None, hard=False
    ):
        _check_active(self)
        if hard:
            raise NotImplementedError("hard IRQs are not simulated")
        self._irq_generation += 1
        self._irq_handler = handler
        self._irq_trigger = trigger
        return self  # non-standard return value

    def mode(self):
        _check_active(self)
        return self._mode

    def __call__(self, x=None):
        return self.value(x)


class PWM:
    """
    https://docs.micropython.org/en/latest/library/machine.PWM.html
    """

    def __init__(
        self,
        dest: Pin,
        *,
        freq: int,
        duty_u16: Optional[int] = None,
        duty_ns: Optional[int] = None,
        invert: bool = False,
    ):
        self._pin = dest
        self._freq = freq
        self._duty_u16 = duty_u16
        self._duty_ns = duty_ns
        if duty_ns is None and duty_u16 is None:
            raise ValueError("Needs duty_ns or duty_u16 provided")
        self.invert = invert

    def init(self, freq, duty_u16, duty_ns):
        self._freq = freq
        self._duty_u16 = duty_u16
        self._duty_ns = duty_ns

    def deinit(self):
        self._freq = None
        self._duty_u16 = None
        self._duty_ns = None

    def freq(self, value=None):
        if value is None:
            return self._freq
        self._freq = value

    def duty_u16(self, value=None):
        if value is None:
            return self._duty_u16
        self._duty_u16 = value

    def duty_ns(self, value=None):
        if value is None:
            return self._duty_ns
        self._duty_ns = value


class RTC:
    """
    https://docs.micropython.org/en/latest/library/machine.RTC.html
    """

    _instances = []

    def __init__(self):
        self._callback = None
        self._timeout = None
        self._stop = False
        self._running = False
        self._task = None  # don't start task yet
        self._instances.append(self)

    def wakeup(self, timeout=None, callback=None):
        """
        Register a wakeup timer.

        :param timeout: Wakeup interval in ms
        :param callback: Function to call on wakeup
        """
        log.info("RTC: Registering a wakeup in: %s, callback is: %s", timeout, callback)

        self._stop = False
        self._timeout = timeout
        self._callback = callback
        if callback:
            assert callable(self._callback)

        # Start the async loop only when first used
        if not self._task:
            self._task = asyncio.create_task(self._wakeup())

    async def _wakeup(self):
        log.info("RTC: Starting RTC task")
        self._running = True

        while not self._stop:
            timeout = self._timeout if self._timeout else 1000  # default 1s
            await asyncio.sleep_ms(timeout)

            if self._callback:
                try:
                    self._callback()
                except Exception as e:
                    log.error("RTC callback raised: %s", e)

        self._running = False
        log.info("RTC: stopped wakeup task")

    def stop(self):
        log.info("RTC: Calling Stop")
        self._stop = True
        if self._task:
            self._task.cancel()
            self._task = None
        self._running = False

    @staticmethod
    def info():
        return 1 << 28  # Default "RTC is good" value

    @staticmethod
    def init():
        pass

    @staticmethod
    def datetime(datetime=None):
        now = time.time()
        t = tuple(time.localtime(now))
        return t[:3] + (t[6],) + t[3:6] + (round(now * 1000000) % 1000000,)


class Signal:
    """
    https://docs.micropython.org/en/latest/library/machine.Signal.html
    """

    def __init__(self, pin, invert):
        self.pin = pin
        self.invert = invert

    def on(self):
        self.pin.value(0 if self.invert else 1)

    def off(self):
        self.pin.value(1 if self.invert else 0)

    def value(self, val):
        self.pin.value(val)
        return self.pin.value()


class SPI:
    """Shared virtual SPI controller; receive bytes must be supplied explicitly."""

    MSB = 0
    LSB = 1
    _controllers = {}
    capture_limit = 256
    history_limit = 16

    def __new__(cls, id=None, *args, **kwargs):
        if id in cls._controllers:
            return cls._controllers[id]
        self = super().__new__(cls)
        cls._controllers[id] = self
        return self

    def __init__(
        self, id=None, baudrate=_UNSET, *, polarity=_UNSET, phase=_UNSET,
        bits=_UNSET, firstbit=_UNSET, sck=_UNSET, mosi=_UNSET, miso=_UNSET, pins=_UNSET,
    ):
        if not hasattr(self, "_active"):
            self.id = id
            self._active = True
            self.baudrate = 1000000
            self.polarity = self.phase = 0
            self.bits = 8
            self.firstbit = self.MSB
            self.sck = self.mosi = self.miso = self.pins = None
            self.reset()
        settings = (baudrate, polarity, phase, bits, firstbit, sck, mosi, miso, pins)
        if any(value is not _UNSET for value in settings):
            self.init(baudrate, polarity=polarity, phase=phase, bits=bits,
                      firstbit=firstbit, sck=sck, mosi=mosi, miso=miso, pins=pins)

    def init(
        self, baudrate=_UNSET, *, polarity=_UNSET, phase=_UNSET, bits=_UNSET,
        firstbit=_UNSET, sck=_UNSET, mosi=_UNSET, miso=_UNSET, pins=_UNSET,
    ):
        """Re-enable/reconfigure without clearing supplied RX or captured TX."""
        if baudrate is not _UNSET and (not isinstance(baudrate, int) or baudrate <= 0):
            raise ValueError("baudrate must be positive")
        if bits is not _UNSET and bits != 8:
            raise NotImplementedError("only byte-wide SPI is simulated")
        for name, value in (
            ("baudrate", baudrate), ("polarity", polarity), ("phase", phase),
            ("bits", bits), ("firstbit", firstbit), ("sck", sck), ("mosi", mosi),
            ("miso", miso), ("pins", pins),
        ):
            if value is not _UNSET:
                setattr(self, name, value)
        self._active = True

    def deinit(self):
        self._active = False

    def read(self, nbytes, write=0x00):
        _check_active(self)
        if nbytes < 0:
            raise ValueError("negative read size")
        if not 0 <= write <= 255:
            raise ValueError("write must be a byte")
        if nbytes == 0:
            return b""
        if self.read_buf:
            source = self.read_buf
        elif self.reads:
            source = self.reads[0]
        else:
            raise OSError(errno.ENODEV)
        if len(source) < nbytes:
            raise OSError(errno.EIO)
        result = bytes(memoryview(source)[:nbytes])
        if not self.read_buf:
            self.reads.pop(0)
        self.num_reads += 1
        return result

    def readinto(self, buf, write=0x00):
        buf[:] = self.read(len(buf), write)

    def write(self, buf):
        _check_active(self)
        self.write_buf = bytes(memoryview(buf)[-self.capture_limit:])
        if len(self.writes) >= self.history_limit:
            self.writes.pop(0)
        self.writes.append(self.write_buf)
        self.num_writes += 1

    def write_readinto(self, write_buf, read_buf):
        _check_active(self)
        if len(write_buf) != len(read_buf):
            raise ValueError("SPI buffers must have equal lengths")
        self.write(write_buf)
        self.readinto(read_buf)

    def reset(self):
        """Clear supplied receive data, bounded observations and counters."""
        _check_active(self)
        self.write_buf = b""
        self.read_buf = b""
        self.writes = []
        self.reads = []
        self.num_reads = 0
        self.num_writes = 0




class Timer:
    """
    https://docs.micropython.org/en/latest/library/machine.Timer.html
    """

    ONE_SHOT = 0
    PERIODIC = 1

    _instances = []

    def __init__(self, id=0, channel=None, mode=None, period=None, callback=None):
        self._id = id  # Micropython timer first positional param is id.
        self._start = None
        self._period = period
        self._mode = mode
        self._callback = callback
        self._task = None
        self._channel = channel
        self._freq = 1000  # default frequency
        self._instances.append(self)

        if mode or period or callback:
            self.init(freq=self._freq, mode=mode, period=period, callback=callback)

    def init(self, freq=1000, mode=PERIODIC, period=-1, callback=None):
        if self._task:
            self._task.cancel()
        self._freq = freq or 1000
        self._mode = mode
        self._period = period if period > 0 else 1000  # fallback to 1s
        self._callback = callback
        self._task = asyncio.create_task(self._timer())

    async def _timer(self):
        while True:
            await asyncio.sleep_ms(self._period)
            if self._callback:
                self._callback(time.time())
            if self._mode == self.PERIODIC:
                continue
            return

    def deinit(self):
        if self._task:
            self._task.cancel()
            self._task = None


class WDT:
    """
    https://docs.micropython.org/en/latest/library/machine.WDT.html
    """

    _instances = []

    def __init__(self, timeout):
        self._timeout = timeout
        self._last_pat = time.ticks_ms()
        self._disabled = False
        self.running = True
        self._task = asyncio.create_task(self._tick())
        self._instances.append(self)

    def disable(self):
        self._disabled = True
        self.running = False
        self._task.cancel()

    def feed(self):
        assert self._disabled or self.running, "you are late, WDT already stopped"
        self._last_pat = time.ticks_ms()

    async def _tick(self):
        log.info("Starting WDT loop, timeout is: %s", self._timeout)

        while self.running:
            await asyncio.sleep_ms(10)
            diff = time.ticks_ms() - self._last_pat

            if diff >= self._timeout:
                log.error("\nWDT timeout:%s > %s\n", diff, self._timeout)
                self.running = False
                raise RuntimeError()


class _UARTPoll:
    """Bridge virtual readiness to the Unix port's file-descriptor poller."""

    def __init__(self):
        import os
        import socket
        import struct

        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        path = "/tmp/mock-uart-" + os.urandom(8).hex()
        # MicroPython's Unix socket API accepts native sockaddr bytes.
        address = struct.pack("H", socket.AF_UNIX) + path.encode() + b"\0"
        bound = False
        self.stream = self.peer = None
        try:
            listener.bind(address)
            bound = True
            listener.listen(1)
            self.peer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.peer.connect(address)
            self.stream, _ = listener.accept()
            self.stream.setblocking(False)
            self.peer.setblocking(False)
        except Exception:
            self.close()
            raise
        finally:
            listener.close()
            if bound:
                os.remove(path)
        self.notified = False
        self.blocked = False
        self.filler = b"\0" * 4096

    def sync(self, readable, writable):
        if readable and not self.notified:
            if self.peer.send(b"\1") != 1:
                raise OSError(errno.EIO)
            self.notified = True
        elif not readable and self.notified:
            self.stream.recv(1)
            self.notified = False
        if not writable and not self.blocked:
            while True:
                try:
                    if not self.stream.send(self.filler):
                        raise OSError(errno.EIO)
                except OSError as error:
                    if error.args[0] != errno.EAGAIN:
                        raise
                    break
            self.blocked = True
        elif writable and self.blocked:
            while True:
                try:
                    if not self.peer.recv(4096):
                        raise OSError(errno.EIO)
                except OSError as error:
                    if error.args[0] != errno.EAGAIN:
                        raise
                    break
            self.blocked = False

    def close(self):
        for stream in (self.stream, self.peer):
            if stream is not None:
                stream.close()
        self.stream = self.peer = None


class UART(io.IOBase):
    """Nonblocking virtual UART backed by native RingIO buffers."""

    INV_TX = 0x01
    INV_RX = 0x02
    RTS = 0x01
    CTS = 0x02
    _controllers = {}

    def __new__(cls, id=None, *args, **kwargs):
        if id in cls._controllers:
            return cls._controllers[id]
        self = super().__new__(cls)
        cls._controllers[id] = self
        return self

    def __init__(
        self, id=None, baudrate=_UNSET, bits=_UNSET, parity=_UNSET, stop=_UNSET,
        tx=_UNSET, rx=_UNSET, txbuf=_UNSET, rxbuf=_UNSET, timeout=_UNSET,
        timeout_char=_UNSET, invert=_UNSET, flow=_UNSET, read_buf_len=_UNSET,
        data_for_read=_UNSET, *, rts=_UNSET, cts=_UNSET,
    ):
        if not hasattr(self, "_active"):
            super().__init__()
            self.id = id
            self._active = True
            self.baudrate = 9600
            self.bits = 8
            self.parity = self.tx = self.rx = self.rts = self.cts = None
            self.stop = 1
            self.timeout = self.timeout_char = self.invert = self.flow = 0
            self.txbuf = self.rxbuf = 256
            self._rx_ring = micropython.RingIO(self.rxbuf)
            self._tx_ring = micropython.RingIO(self.txbuf)
            self._responder = None
            self._tx_pending = 0
            self.num_writes = 0
            self._poll = None
        settings = (
            baudrate, bits, parity, stop, tx, rx, txbuf, rxbuf, timeout,
            timeout_char, invert, flow, read_buf_len, rts, cts,
        )
        if any(value is not _UNSET for value in settings):
            self.init(baudrate, bits, parity, stop, tx=tx, rx=rx, txbuf=txbuf,
                      rxbuf=rxbuf, timeout=timeout, timeout_char=timeout_char,
                      invert=invert, flow=flow, read_buf_len=read_buf_len, rts=rts, cts=cts)
        if data_for_read is not _UNSET:
            self.inject_data(data_for_read)

    def init(
        self, baudrate=_UNSET, bits=_UNSET, parity=_UNSET, stop=_UNSET, *,
        tx=_UNSET, rx=_UNSET, txbuf=_UNSET, rxbuf=_UNSET, timeout=_UNSET,
        timeout_char=_UNSET, invert=_UNSET, flow=_UNSET, read_buf_len=_UNSET,
        rts=_UNSET, cts=_UNSET,
    ):
        """Re-enable/reconfigure; nonempty buffers cannot be resized."""
        if rxbuf is _UNSET:
            rxbuf = read_buf_len
        for size in (rxbuf, txbuf):
            if size is not _UNSET and (not isinstance(size, int) or size <= 0):
                raise ValueError("buffer sizes must be positive integers")
        if baudrate is not _UNSET and (not isinstance(baudrate, int) or baudrate <= 0):
            raise ValueError("baudrate must be positive")
        if bits is not _UNSET and bits not in (7, 8, 9):
            raise ValueError("unsupported UART bits")
        if parity is not _UNSET and parity not in (None, 0, 1):
            raise ValueError("parity must be None, 0 or 1")
        if stop is not _UNSET and stop not in (1, 2):
            raise ValueError("stop must be 1 or 2")
        if rxbuf is not _UNSET and rxbuf != self.rxbuf and self._rx_ring.any():
            raise OSError(errno.EAGAIN)
        if txbuf is not _UNSET and txbuf != self.txbuf and self._tx_ring.any():
            raise OSError(errno.EAGAIN)
        if rxbuf is not _UNSET and rxbuf != self.rxbuf:
            self._rx_ring = micropython.RingIO(rxbuf)
            self.rxbuf = rxbuf
        if txbuf is not _UNSET and txbuf != self.txbuf:
            self._tx_ring = micropython.RingIO(txbuf)
            self.txbuf = txbuf
        for name, value in (
            ("baudrate", baudrate), ("bits", bits), ("parity", parity), ("stop", stop),
            ("tx", tx), ("rx", rx), ("timeout", timeout), ("timeout_char", timeout_char),
            ("invert", invert), ("flow", flow), ("rts", rts), ("cts", cts),
        ):
            if value is not _UNSET:
                setattr(self, name, value)
        self._active = True
        self._sync_poll()

    def _sync_poll(self):
        if self._poll is not None:
            self._poll.sync(
                bool(self._rx_ring.any()),
                self._responder is not None or self._tx_ring.any() < self.txbuf,
            )

    def set_responder(self, callback):
        """Attach a consuming peer: accepted immutable TX bytes -> RX bytes/None."""
        _check_active(self)
        if callback is not None and not callable(callback):
            raise TypeError("responder must be callable or None")
        self._responder = callback
        self._tx_ring.read()
        self._tx_pending = 0
        self._sync_poll()

    def inject_data(self, data):
        """Atomically enqueue RX; overflow raises ENOBUFS without losing bytes."""
        _check_active(self)
        if len(data) > self.rxbuf - self._rx_ring.any():
            raise OSError(errno.ENOBUFS)
        accepted = self._rx_ring.write(data)
        self._sync_poll()
        return accepted

    def write(self, data):
        _check_active(self)
        if isinstance(data, str):
            data = data.encode()
        if not data:
            return 0
        if self._responder is None:
            accepted = self._tx_ring.write(data)
            if not accepted:
                return None
            self._tx_pending += accepted
        else:
            accepted = len(data)
            immutable = bytes(data)
            self._tx_ring.read()
            self._tx_ring.write(memoryview(immutable)[-self.txbuf:])
            self._tx_pending = accepted
            try:
                response = self._responder(immutable)
                if response is not None:
                    self.inject_data(response)
            finally:
                self._tx_pending = 0
        self.num_writes += 1
        self._sync_poll()
        return accepted

    def read(self, nbytes=-1):
        _check_active(self)
        if nbytes is None or nbytes == -1:
            data = self._rx_ring.read() if self._rx_ring.any() else None
        else:
            if nbytes < 0:
                raise ValueError("negative read size")
            if nbytes == 0:
                return b""
            data = self._rx_ring.read(nbytes) if self._rx_ring.any() else None
        self._sync_poll()
        return data

    def readinto(self, buf, nbytes=None):
        _check_active(self)
        if nbytes is None:
            nbytes = len(buf)
        if nbytes < 0 or nbytes > len(buf):
            raise ValueError("invalid read size")
        if nbytes == 0:
            return 0
        if not self._rx_ring.any():
            return None
        count = self._rx_ring.readinto(buf, nbytes)
        self._sync_poll()
        return count

    def readline(self):
        _check_active(self)
        data = self._rx_ring.readline() if self._rx_ring.any() else None
        self._sync_poll()
        return data

    def flush(self):
        """Complete virtual TX, retaining the bounded observation capture."""
        _check_active(self)
        self._tx_pending = 0

    def txdone(self):
        _check_active(self)
        return self._tx_pending == 0

    def deinit(self):
        """Close the stream and discard pending data and its peer."""
        self._active = False
        self._rx_ring.read()
        self._tx_ring.read()
        self._responder = None
        self._tx_pending = 0
        if self._poll is not None:
            self._poll.close()
            self._poll = None

    def close(self):
        self.deinit()

    def any(self):
        _check_active(self)
        return self._rx_ring.any()

    def ioctl(self, op, arg):
        if op == 10:  # MP_STREAM_GET_FILENO, required by Unix select.poll
            _check_active(self)
            if self._poll is None:
                self._poll = _UARTPoll()
            self._sync_poll()
            return self._poll.stream.fileno()
        if op == 3:  # MP_STREAM_POLL
            if not self._active:
                return 0x0020  # POLLNVAL
            ready = 0x0001 if self._rx_ring.any() else 0
            if self._responder is not None or self._tx_ring.any() < self.txbuf:
                ready |= 0x0004  # POLLOUT
            return ready & arg
        if op == 1:  # MP_STREAM_FLUSH
            self.flush()
            return 0
        if op == 4:  # MP_STREAM_CLOSE
            self.close()
            return 0
        raise OSError(errno.EINVAL)

    def get_written_data(self):
        """Drain TX capture (latest bounded suffix when a responder is attached)."""
        _check_active(self)
        data = self._tx_ring.read()
        if data is not None:
            self._tx_pending = max(0, self._tx_pending - len(data))
        self._sync_poll()
        return data


def reset_simulation():
    """Isolate sessions; no host reset or native-module replacement occurs."""
    global _cpu_hz, __reset_cause__
    for pin in Pin.pins.values():
        pin._active = False
        pin._irq_handler = None
        pin._irq_generation += 1
    Pin.pins.clear()
    Pin._aliases = {}
    Pin.board.configure(None)
    for cls in (I2C, SPI, UART):
        for controller in cls._controllers.values():
            controller.deinit()
        cls._controllers.clear()
    ADC.pin_adc_map.clear()
    for timer in Timer._instances:
        timer.deinit()
    Timer._instances.clear()
    for rtc in RTC._instances:
        rtc.stop()
    RTC._instances.clear()
    for watchdog in WDT._instances:
        watchdog.disable()
    WDT._instances.clear()
    _cpu_hz = 0
    __reset_cause__ = PWRON_RESET
