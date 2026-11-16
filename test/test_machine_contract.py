# MIT license; Copyright (c) 2026 contributors
"""Consumer contracts: run with native MicroPython RingIO, schedule and asyncio."""
import asyncio
import errno
import os
import sys
import time
import unittest

import mock_machine as machine


class MachineContract(unittest.TestCase):
    def setUp(self):
        machine.reset_simulation()

    def tearDown(self):
        machine.reset_simulation()

    def test_registration_uses_qualified_import(self):
        package = "machine_contract_import"
        previous = sys.modules.get("machine")
        os.mkdir(package)
        try:
            sys.path.insert(0, os.getcwd())
            with open(package + "/__init__.py", "w") as target:
                target.write("")
            with open(machine.__file__) as source:
                with open(package + "/hal.py", "w") as target:
                    target.write(source.read())
            qualified = __import__(package + ".hal", None, None, ("hal",))
            qualified.register_as_machine()
            peer = __import__("machine")
            events = []
            peer.Pin("SENSE", peer.Pin.IN, value=0).irq(
                lambda pin: events.append(pin.value()), trigger=peer.Pin.IRQ_RISING
            )
            qualified.Pin("SENSE").inject(1)
            time.sleep_ms(1)
            self.assertEqual(events, [1])
        finally:
            sys.path.pop(0)
            if previous is None:
                sys.modules.pop("machine", None)
            else:
                sys.modules["machine"] = previous
            sys.modules.pop(package + ".hal", None)
            sys.modules.pop(package, None)
            os.remove(package + "/hal.py")
            os.remove(package + "/__init__.py")
            os.rmdir(package)


    def test_pin_lookup_configuration_and_edges(self):
        Pin = machine.Pin
        Pin.configure_aliases({"BUTTON": 7, "BUTTON_COPY": 7})
        pin = Pin("BUTTON", Pin.IN, Pin.PULL_UP, value=0)
        events = []
        pin.irq(lambda p: events.append(p.id), trigger=Pin.IRQ_RISING)
        self.assertIs(Pin(7), pin)
        self.assertIs(Pin(Pin.board.BUTTON_COPY), pin)
        self.assertEqual(pin.snapshot(), {"id": 7, "mode": Pin.IN,
                                         "pull": Pin.PULL_UP, "value": 0})
        pin.inject(1)
        time.sleep_ms(1)
        self.assertEqual(events, [7])
        pin.inject(0)
        time.sleep_ms(1)
        self.assertEqual(events, [7])  # A falling edge must not match RISING.
        Pin("BUTTON").init(mode=Pin.OUT, pull=None)
        self.assertEqual(pin.mode(), Pin.OUT)
        self.assertEqual(pin.snapshot()["pull"], None)
        self.assertEqual(pin.value(), 0)
        pin.inject(1)
        time.sleep_ms(1)
        self.assertEqual(events, [7, 7])  # Reconfiguration preserved the IRQ.
        pin.inject(None)
        pin.inject(0)
        time.sleep_ms(1)
        self.assertEqual(events, [7, 7])
        machine.reset_simulation()
        with self.assertRaises(OSError):
            pin.value()
        self.assertIsNone(Pin("BUTTON").value())
        self.assertIsNot(Pin(7), Pin("BUTTON"))

    def test_falling_and_both_edge_masks(self):
        pin = machine.Pin(1)
        events = []
        pin.irq(lambda p: events.append(p.id), trigger=machine.Pin.IRQ_FALLING)
        pin.inject(1)  # Unknown to known is not an edge.
        pin.inject(0)
        time.sleep_ms(1)
        self.assertEqual(events, [1])
        pin.inject(1)
        time.sleep_ms(1)
        self.assertEqual(events, [1])
        pin.irq(lambda p: events.append(p.id))
        pin.inject(0)
        time.sleep_ms(1)
        pin.inject(1)
        time.sleep_ms(1)
        self.assertEqual(events, [1, 1, 1])

    def test_alias_ambiguity_is_rejected(self):
        for aliases in ({"A": "B", "B": 1}, {"A": "A"}, {"A": []}):
            with self.assertRaises(ValueError):
                machine.Pin.configure_aliases(aliases)
        machine.Pin.configure_aliases({"LED": 3})
        machine.Pin(3)
        with self.assertRaises(ValueError):
            machine.Pin.configure_aliases({"LED": 4})
        self.assertIs(machine.Pin("LED"), machine.Pin(3))

    def test_i2c_controller_preserves_devices_and_configuration(self):
        bus = machine.I2C(0, freq=100000)
        device = machine.RegisterBasedI2CDevice(0x40, bus)
        bus.writeto(0x40, b"\x02\x12\x34")
        self.assertIs(machine.I2C(0), bus)
        self.assertEqual(bus.freq, 100000)
        bus.writeto(0x40, b"\x02")
        result = bytearray(2)
        machine.I2C(0).readfrom_into(0x40, result)
        self.assertEqual(result, b"\x12\x34")
        self.assertEqual(bus.scan(), [0x40])
        with self.assertRaises(OSError):
            bus.readfrom(0x41, 1)
        bus.deinit()
        with self.assertRaises(OSError):
            machine.I2C(0).scan()
        bus.init(freq=400000)
        self.assertEqual(bus.scan(), [0x40])
        self.assertIs(bus.devices[0x40], device)
        machine.reset_simulation()
        self.assertEqual(machine.I2C(0).scan(), [])

    def test_spi_controller_transfer_and_bounded_observation(self):
        spi = machine.SPI(1, baudrate=2000000, polarity=1, phase=1)
        spi.read_buf = b"AB"
        spi.write(b"command")
        self.assertIs(machine.SPI(1), spi)
        self.assertEqual(spi.write_buf, b"command")
        self.assertEqual(spi.baudrate, 2000000)
        buf = bytearray(b"xy")
        spi.write_readinto(buf, buf)
        self.assertEqual(buf, b"AB")
        self.assertEqual(spi.write_buf, b"xy")
        with self.assertRaises(ValueError):
            spi.write_readinto(b"x", bytearray(2))
        with self.assertRaises(OSError):
            spi.read(3)
        for i in range(40):
            spi.write(bytes([i]) * 300)
        self.assertEqual(len(spi.writes), 16)
        self.assertEqual(spi.write_buf, bytes([39]) * 256)
        self.assertEqual(spi.num_writes, 42)
        spi.deinit()
        with self.assertRaises(OSError):
            machine.SPI(1).write(b"x")
        spi.init()
        self.assertEqual(spi.read(2), b"AB")
        spi.reset()
        with self.assertRaises(OSError):
            spi.read(1)

    def test_uart_responder_repeated_exchanges_and_absent_response(self):
        uart = machine.UART(1, 19200, txbuf=8, rxbuf=8)
        calls = []
        def responder(data):
            self.assertIsInstance(data, bytes)
            calls.append(data)
            return data.upper()
        uart.set_responder(responder)
        for _ in range(100):
            self.assertEqual(machine.UART(1).write(bytearray(b"ping")), 4)
            self.assertEqual(uart.read(), b"PING")
            self.assertTrue(uart.txdone())
        self.assertEqual(len(calls), 100)
        self.assertEqual(uart.baudrate, 19200)
        self.assertEqual(uart.get_written_data(), b"ping")
        uart.set_responder(lambda data: None)
        self.assertEqual(uart.write(b"missing"), 7)
        self.assertIsNone(uart.read())
        self.assertEqual(uart.any(), 0)
        uart.set_responder(None)
        self.assertEqual(uart.write(b"no peer"), 7)
        self.assertIsNone(uart.read())

    def test_uart_overflow_preserves_rx_and_tx_capture_is_bounded(self):
        uart = machine.UART(1, rxbuf=4, txbuf=4)
        uart.inject_data(b"old")
        with self.assertRaises(OSError) as error:
            uart.inject_data(b"xx")
        self.assertEqual(error.exception.args[0], errno.ENOBUFS)
        self.assertEqual(uart.read(), b"old")
        uart.set_responder(lambda data: b"12345")
        with self.assertRaises(OSError):
            uart.write(b"x")
        self.assertEqual(uart.any(), 0)
        uart.set_responder(None)
        self.assertEqual(uart.write(b"abcdef"), 4)
        self.assertIsNone(uart.write(b"g"))
        self.assertEqual(uart.ioctl(3, 4), 0)
        self.assertEqual(uart.get_written_data(), b"abcd")
        self.assertEqual(uart.ioctl(3, 4), 4)
        uart.set_responder(lambda data: None)
        self.assertEqual(uart.write(b"abcdefgh"), 8)
        self.assertEqual(uart.get_written_data(), b"efgh")

    def test_uart_flush_close_reinit_and_poll(self):
        uart = machine.UART(2, baudrate=38400)
        self.assertEqual(uart.ioctl(3, 0), 0)
        self.assertEqual(uart.ioctl(3, 5), 4)
        uart.write(b"tx")
        self.assertFalse(uart.txdone())
        self.assertEqual(uart.ioctl(1, 0), 0)
        self.assertTrue(uart.txdone())
        self.assertEqual(uart.get_written_data(), b"tx")
        uart.inject_data(b"rx")
        self.assertEqual(uart.ioctl(3, 1), 1)
        self.assertEqual(uart.ioctl(3, 4), 4)
        self.assertEqual(uart.ioctl(4, 0), 0)
        self.assertEqual(uart.ioctl(3, 5), 32)
        for operation in (uart.read, uart.readline, uart.any, uart.flush, uart.txdone,
                          lambda: uart.write(b"x"), lambda: uart.inject_data(b"x")):
            with self.assertRaises(OSError):
                operation()
        self.assertIs(machine.UART(2), uart)
        with self.assertRaises(OSError):
            uart.read()
        uart.init()
        self.assertEqual(uart.baudrate, 38400)
        self.assertIsNone(uart.read())
        self.assertTrue(uart.txdone())
        uart.inject_data(b"keep")
        with self.assertRaises(OSError):
            uart.init(rxbuf=16)
        self.assertEqual(uart.read(), b"keep")
        machine.reset_simulation()
        self.assertIsNot(machine.UART(2), uart)
        self.assertIsNone(machine.UART(2).read())

    def test_native_asyncio_stream(self):
        async def exercise():
            uart = machine.UART(1)
            uart.set_responder(lambda data: data.upper())
            stream = asyncio.StreamWriter(uart, {})
            stream.write(b"hello")
            await stream.drain()
            reader = asyncio.StreamReader(uart)
            self.assertEqual(await reader.readexactly(5), b"HELLO")
            async def receive_later():
                await asyncio.sleep_ms(1)
                uart.inject_data(b"ok\n")
            producer = asyncio.create_task(receive_later())
            self.assertEqual(await asyncio.wait_for_ms(reader.readline(), 1000), b"ok\n")
            await producer
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for_ms(reader.read(1), 10)
            # A full capture must block native POLLOUT until a consumer drains it.
            capture = machine.UART(3, txbuf=4)
            writer = asyncio.StreamWriter(capture, {})
            received = bytearray()
            async def consume():
                while len(received) < 6:
                    await asyncio.sleep_ms(1)
                    chunk = capture.get_written_data()
                    if chunk:
                        received.extend(chunk)
            consumer = asyncio.create_task(consume())
            writer.write(b"abcdef")
            await asyncio.wait_for_ms(writer.drain(), 1000)
            await asyncio.wait_for_ms(consumer, 1000)
            self.assertEqual(received, b"abcdef")
        asyncio.run(exercise())

    def test_reset_cancels_owned_timers(self):
        async def exercise():
            events = []
            timer = machine.Timer(-1)
            timer.init(period=10, callback=lambda value: events.append("timer"))
            rtc = machine.RTC()
            rtc.wakeup(10, lambda: events.append("rtc"))
            machine.WDT(10)
            await asyncio.sleep_ms(0)
            machine.reset_simulation()
            await asyncio.sleep_ms(30)
            self.assertEqual(events, [])
        asyncio.run(exercise())


if __name__ == "__main__":
    raise SystemExit(0 if unittest.main().wasSuccessful() else 1)
