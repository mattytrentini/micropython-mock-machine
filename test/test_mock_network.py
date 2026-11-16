# MIT License; Copyright (c) 2026 Matt Trentini
import sys
import unittest

import mock_network as network

IP = ("192.0.2.10", "255.255.255.0", "192.0.2.1", "192.0.2.53")


class TestNetwork(unittest.TestCase):
    def setUp(self):
        network.reset_simulation()

    def tearDown(self):
        network.reset_simulation()

    def test_connect_requires_activation_and_explicit_completion(self):
        wlan = network.WLAN(network.STA_IF)
        with self.assertRaises(OSError):
            wlan.connect("test", "private-password")
        wlan.active(True)
        wlan.connect("test", "private-password")
        self.assertEqual(wlan.status(), network.STAT_CONNECTING)
        self.assertFalse(wlan.isconnected())
        self.assertEqual(wlan.ifconfig()[0], "0.0.0.0")
        self.assertFalse("private-password" in str(wlan.snapshot()))
        with self.assertRaises(ValueError):
            wlan.set_link(True)
        wlan.set_link(True, ifconfig=IP)
        self.assertTrue(wlan.isconnected())
        self.assertEqual(wlan.status(), network.STAT_GOT_IP)
        self.assertEqual(wlan.ifconfig(), IP)
        wlan.connect("another")
        self.assertFalse(wlan.isconnected())
        self.assertEqual(wlan.status(), network.STAT_CONNECTING)

    def test_retrieval_preserves_state_and_interfaces_are_independent(self):
        sta = network.WLAN(network.STA_IF)
        ap = network.WLAN(network.AP_IF)
        sta.active(True)
        sta.set_link(True, ifconfig=IP)
        self.assertIs(network.WLAN(network.STA_IF), sta)
        self.assertTrue(network.WLAN().isconnected())
        self.assertFalse(ap.active())
        self.assertFalse(ap.isconnected())
        with self.assertRaises(ValueError):
            network.WLAN(99)
        with self.assertRaises(NotImplementedError):
            ap.connect("not-a-radio")

    def test_failures_disconnect_and_deactivation_are_coherent(self):
        wlan = network.WLAN()
        wlan.active(True)
        for status in (network.STAT_NO_AP_FOUND, network.STAT_WRONG_PASSWORD,
                       network.STAT_CONNECT_FAIL, network.STAT_HANDSHAKE_TIMEOUT):
            wlan.connect("test")
            wlan.set_link(False, status=status)
            self.assertEqual(wlan.status(), status)
            self.assertFalse(wlan.isconnected())
        wlan.set_link(True, ifconfig=IP)
        wlan.disconnect()
        self.assertTrue(wlan.active())
        self.assertFalse(wlan.isconnected())
        self.assertEqual(wlan.ifconfig(), IP)
        self.assertEqual(wlan.status(), network.STAT_IDLE)
        wlan.set_link(True)
        wlan.active(False)
        self.assertFalse(wlan.active())
        self.assertFalse(wlan.isconnected())
        self.assertEqual(wlan.status(), network.STAT_IDLE)
        with self.assertRaises(ValueError):
            wlan.set_link(True)
        with self.assertRaises(ValueError):
            wlan.set_link(False, status=network.STAT_CONNECTING)

    def test_rejected_transitions_do_not_partially_change_state(self):
        wlan = network.WLAN()
        wlan.active(True)
        wlan.connect("test")
        before = wlan.snapshot()
        with self.assertRaises(ValueError):
            wlan.set_link(True, ifconfig=IP, status=network.STAT_CONNECT_FAIL)
        self.assertEqual(wlan.snapshot(), before)
        with self.assertRaises(ValueError):
            wlan.set_link(False, ifconfig=IP, status=network.STAT_GOT_IP)
        self.assertEqual(wlan.snapshot(), before)
        for invalid in (("192.0.2.10",), ("999.1.1.1",) * 4, (None,) * 4):
            with self.assertRaises(ValueError):
                wlan.ifconfig(invalid)
            self.assertEqual(wlan.snapshot(), before)
        wlan.set_link(True, ifconfig=IP)
        with self.assertRaises(ValueError):
            wlan.ifconfig(("0.0.0.0",) * 4)
        self.assertTrue(wlan.isconnected())
        self.assertEqual(wlan.ifconfig(), IP)

    def test_lan_constructor_does_not_touch_driver_objects(self):
        class UnusableSPI:
            def write(self, data):
                raise AssertionError("LAN state must not emulate a physical PHY")
        lan = network.LAN(UnusableSPI(), phy_type=network.PHY_W5500,
                          phy_addr=0, cs=object(), int=object(), reset=object())
        lan.active(True)
        lan.ifconfig(IP)
        self.assertFalse(lan.isconnected())
        lan.set_link(True)
        self.assertIs(network.LAN(), lan)
        self.assertTrue(network.LAN().isconnected())
        self.assertFalse(network.LAN(id=1).active())
        self.assertEqual(lan.status(), network.STAT_GOT_IP)

    def test_reset_deactivates_old_handles_and_clears_identity(self):
        wlan = network.WLAN()
        lan = network.LAN()
        for interface in (wlan, lan):
            interface.active(True)
            interface.set_link(True, ifconfig=IP)
        network.reset_simulation()
        for old, new in ((wlan, network.WLAN()), (lan, network.LAN())):
            self.assertIsNot(old, new)
            self.assertFalse(old.active())
            self.assertFalse(old.isconnected())
            self.assertEqual(new.ifconfig(), ("0.0.0.0",) * 4)
            self.assertEqual(old.status(), network.STAT_IDLE)

    def test_registration_and_unsupported_operations(self):
        missing = object()
        previous = sys.modules.get("network", missing)
        try:
            network.register_as_network()
            self.assertIs(__import__("network"), network)
            with self.assertRaises(NotImplementedError):
                network.WLAN().scan()
            with self.assertRaises(NotImplementedError):
                network.LAN().config(dhcp=True)
            with self.assertRaises(TypeError):
                network.LAN(pretend_driver=True)
        finally:
            if previous is missing:
                sys.modules.pop("network", None)
            else:
                sys.modules["network"] = previous


if __name__ == "__main__":
    raise SystemExit(0 if unittest.main().wasSuccessful() else 1)
