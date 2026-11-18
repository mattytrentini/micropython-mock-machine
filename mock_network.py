# MIT License; Copyright (c) 2026 Matt Trentini
"""Explicit LAN/WLAN link state, not radio, Ethernet, sockets or DNS emulation.

Native Unix sockets and DNS retain their real host-network behavior. Activating
an interface or requesting WLAN association never changes the host's network.
A test/model must explicitly supply an address and call set_link(True).
"""

import sys

__version__ = "1.2.0"

STA_IF = 0
AP_IF = 1
PHY_W5500 = 5
STAT_IDLE = 0
STAT_CONNECTING = 1
STAT_GOT_IP = 3
STAT_WRONG_PASSWORD = -3
STAT_NO_AP_FOUND = -2
STAT_CONNECT_FAIL = -1
STAT_HANDSHAKE_TIMEOUT = -4

# MicroPython v1.29.0 ports/esp32/modnetwork.h Ethernet enum.
# Existing generic STAT_* transition values remain unchanged.
ETH_CONNECTED = 3
_UNSET = object()
_INTEGER = type(0)
_DISCONNECTED = (STAT_IDLE, STAT_CONNECTING, STAT_WRONG_PASSWORD,
                 STAT_NO_AP_FOUND, STAT_CONNECT_FAIL, STAT_HANDSHAKE_TIMEOUT)
_hostname = ""


def hostname(name=_UNSET):
    """Get/set explicit simulation metadata; never change host DNS/networking."""
    global _hostname
    if name is _UNSET:
        return _hostname
    if not isinstance(name, str) or len(name) > 253 or "\x00" in name:
        raise ValueError("hostname requires a string of at most 253 characters")
    _hostname = name


def register_as_network():
    """Install this actual module, including when imported by a qualified name."""
    sys.modules["network"] = sys.modules[__name__]


def _address(configuration):
    if not isinstance(configuration, (tuple, list)) or len(configuration) != 4:
        raise ValueError("ifconfig requires (address, netmask, gateway, dns)")
    for address in configuration:
        if not isinstance(address, str):
            raise ValueError("ifconfig entries must be IPv4 strings")
        octets = address.split(".")
        if len(octets) != 4 or any(
            not part or not part.isdigit() or not 0 <= int(part) <= 255
            for part in octets
        ):
            raise ValueError("invalid IPv4 address")
    return tuple(configuration)


class _Interface:
    def _reset(self):
        self._active = False
        self._connected = False
        self._configuration = ("0.0.0.0",) * 4
        self._status = STAT_IDLE
        self._ssid = None
        self._password = None

        self._mac = b"\x00\x00\x00\x00\x00\x00"
    def active(self, value=_UNSET):
        if value is _UNSET:
            return self._active
        if not isinstance(value, (bool, int)) or value not in (False, True):
            raise ValueError("active requires a boolean")
        self._active = bool(value)
        if not self._active:
            self.disconnect()

    def isconnected(self):
        return self._connected

    def ifconfig(self, configuration=_UNSET):
        if configuration is _UNSET:
            return self._configuration
        configuration = _address(configuration)
        if self._connected and configuration[0] == "0.0.0.0":
            raise ValueError("a connected interface needs an address")
        self._configuration = configuration

    def status(self):
        return self._status

    def disconnect(self):
        """Drop link/association intent; retain any configured static address."""
        self._connected = False
        self._status = STAT_IDLE
        self._ssid = None
        self._password = None

    def set_link(self, connected, ifconfig=None, status=None):
        """Set modeled link state atomically; no packets or hardware operations.

        A positive link requires an active interface and a nonzero IPv4 address.
        Disconnected states can represent an idle, pending or failed connection.
        """
        if not isinstance(connected, (bool, int)) or connected not in (False, True):
            raise ValueError("connected requires a boolean")
        configuration = self._configuration if ifconfig is None else _address(ifconfig)
        if connected:
            if not self._active or configuration[0] == "0.0.0.0":
                raise ValueError("activate and configure an address before setting link")
            if status is not None and status != STAT_GOT_IP:
                raise ValueError("a connected interface must report STAT_GOT_IP")
            status = STAT_GOT_IP
        else:
            status = STAT_IDLE if status is None else status
            if status not in _DISCONNECTED:
                raise ValueError("invalid disconnected status")
            if not self._active and status != STAT_IDLE:
                raise ValueError("an inactive interface must report STAT_IDLE")
        self._configuration = configuration
        self._connected = bool(connected)
        self._status = status

    def snapshot(self):
        """Return JSON-safe diagnostic state, never SSIDs or credentials."""
        return {"kind": self._kind, "id": self._id, "active": self._active,
                "connected": self._connected, "ifconfig": self._configuration,
                "status": self._status}

    def config(self, *args, **kwargs):
        """Only explicit MAC metadata is modeled, not radio/PHY settings."""
        if len(args) == 1 and args[0] == "mac" and not kwargs:
            return self._mac
        if not args and len(kwargs) == 1 and "mac" in kwargs:
            value = kwargs["mac"]
            if not isinstance(value, (bytes, bytearray, memoryview)) or len(value) != 6:
                raise ValueError("mac requires six bytes")
            self._mac = bytes(value)
            return None
        raise NotImplementedError("only MAC metadata configuration is modeled")


class WLAN(_Interface):
    """Stable STA/AP identities. Only explicit models can complete association."""
    _instances = {}
    _kind = "WLAN"

    def __new__(cls, interface_id=STA_IF):
        if interface_id not in (STA_IF, AP_IF):
            raise ValueError("unsupported WLAN interface")
        if interface_id not in cls._instances:
            instance = super().__new__(cls)
            instance._id = interface_id
            instance._reset()
            cls._instances[interface_id] = instance
        return cls._instances[interface_id]

    def __init__(self, interface_id=STA_IF):
        pass  # A lookup must not reinitialize an existing interface.

    def connect(self, ssid, password=None):
        if self._id != STA_IF:
            raise NotImplementedError("AP association is not modeled")
        if not self._active:
            raise OSError("WLAN interface is inactive")
        if not isinstance(ssid, (str, bytes)) or not ssid:
            raise ValueError("ssid must be a nonempty string or bytes")
        if password is not None and not isinstance(password, (str, bytes)):
            raise ValueError("password must be a string or bytes")
        self._ssid = ssid
        self._password = password
        self._connected = False
        self._status = STAT_CONNECTING

    def scan(self):
        raise NotImplementedError("radio scanning is not modeled")



class LAN(_Interface):
    """Stable virtual LAN controllers; constructor wiring is metadata only.

    SPI and Pin objects are accepted but never used to emulate a physical PHY.
    Repeated construction preserves state and changes only supplied metadata.
    """
    _instances = {}
    _kind = "LAN"

    def __new__(cls, spi=_UNSET, *, id=0, phy_type=_UNSET, phy_addr=_UNSET,
                cs=_UNSET, int=_UNSET, reset=_UNSET, mdc=_UNSET, mdio=_UNSET,
                power=_UNSET):
        if not isinstance(id, (str, _INTEGER)):
            raise ValueError("LAN id must be an integer or string")
        if id not in cls._instances:
            instance = super().__new__(cls)
            instance._id = id
            instance._reset()
            instance._driver = {}
            cls._instances[id] = instance
        return cls._instances[id]

    def __init__(self, spi=_UNSET, *, id=0, phy_type=_UNSET, phy_addr=_UNSET,
                 cs=_UNSET, int=_UNSET, reset=_UNSET, mdc=_UNSET, mdio=_UNSET,
                 power=_UNSET):
        for key, value in (("spi", spi), ("phy_type", phy_type),
                           ("phy_addr", phy_addr), ("cs", cs), ("int", int),
                           ("reset", reset), ("mdc", mdc), ("mdio", mdio),
                           ("power", power)):
            if value is not _UNSET:
                self._driver[key] = value



def reset_simulation():
    """Deactivate existing handles and forget interface identities/configuration."""
    global _hostname
    _hostname = ""
    for registry in (WLAN._instances, LAN._instances):
        for interface in registry.values():
            interface._reset()
        registry.clear()
