"""Thin wrapper over stem.control.Controller."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from stem import CircStatus, ControllerError, Signal
from stem.connection import AuthenticationFailure, IncorrectPassword, MissingPassword, UnreadableCookieFile
from stem.control import Controller, EventType
from stem.response.events import CircuitEvent, StreamEvent

PORTS = (9051, 9151)  # tor daemon, Tor Browser


class TorError(Exception):
    """Any user-presentable failure talking to Tor."""


@dataclass
class Hop:
    role: str  # Guard / Middle / Exit
    fingerprint: str
    nickname: str
    ip: str
    country: str
    flags: list[str]


@dataclass
class Circuit:
    id: str
    purpose: str
    hops: list[Hop]


def connect(password: str | None = None) -> Controller:
    """Try each ControlPort in order; raise TorError with a clear reason."""
    errors: list[str] = []
    for port in PORTS:
        try:
            # Controller.from_port opens the TCP socket to 127.0.0.1:<port>
            ctl = Controller.from_port(port=port)
        except Exception as e:  # stem raises SocketError (ConnectionRefused) when closed
            errors.append(f"{port}: puerto cerrado ({e})")
            continue
        try:
            # authenticate() auto-picks NONE / SAFECOOKIE / COOKIE / PASSWORD from PROTOCOLINFO
            ctl.authenticate(password=password)
            return ctl
        except UnreadableCookieFile:
            errors.append(f"{port}: sin permiso para leer la cookie (añade tu usuario al grupo debian-tor)")
        except (MissingPassword, IncorrectPassword):
            errors.append(f"{port}: requiere contraseña (--password) o es incorrecta")
        except AuthenticationFailure as e:
            errors.append(f"{port}: fallo de autenticación ({e})")
        ctl.close()
    raise TorError("No se pudo conectar a Tor:\n  " + "\n  ".join(errors))


def built_circuits(ctl: Controller) -> list[Circuit]:
    """All BUILT circuits with per-hop data from the consensus."""
    out: list[Circuit] = []
    for c in ctl.get_circuits():  # GETINFO circuit-status
        if c.status != CircStatus.BUILT:
            continue
        hops: list[Hop] = []
        for i, (fp, nick) in enumerate(c.path):
            try:
                ns = ctl.get_network_status(fp)  # GETINFO ns/id/<fp> -> router status entry
                ip, flags = ns.address, list(ns.flags)
                # GETINFO ip-to-country/<ip>: Tor's local GeoIP db, nothing leaves the machine
                cc = ctl.get_info(f"ip-to-country/{ip}", "??")
            except Exception:  # relay not in cached consensus (e.g. just rotated out)
                ip, flags, cc = "?", [], "??"
            last = i == len(c.path) - 1
            # "Exit" only means something on GENERAL circuits; HS/dir circuits end at an ordinary relay
            role = "Guard" if i == 0 else ("Exit" if str(c.purpose) in ("GENERAL", "CONFLUX_LINKED", "CONFLUX_UNLINKED") else "Final") if last else "Middle"
            hops.append(Hop(role, fp, nick or fp[:8], ip, cc, flags))
        out.append(Circuit(c.id, str(c.purpose), hops))
    return sorted(out, key=lambda c: int(c.id))


def listen(ctl: Controller, on_stream: Callable[[StreamEvent], None],
           on_circ: Callable[[CircuitEvent], None], on_close: Callable[[], None]) -> None:
    """Register async listeners; stem runs them in its own event thread."""
    # SETEVENTS STREAM CIRC under the hood
    ctl.add_event_listener(on_stream, EventType.STREAM)
    ctl.add_event_listener(on_circ, EventType.CIRC)
    # Fires on CLOSED when Tor drops the control connection mid-monitoring
    ctl.add_status_listener(lambda _c, status, _t: on_close() if str(status) == "CLOSED" else None)


def new_identity(ctl: Controller) -> None:
    """Clean existing circuits for new connections (rotates exit IP)."""
    if not ctl.is_newnym_available():
        raise TorError(f"NEWNYM limitado por Tor, espera {ctl.get_newnym_wait():.0f}s")
    ctl.signal(Signal.NEWNYM)  # SIGNAL NEWNYM


def set_exit_country(ctl: Controller, cc: str | None) -> None:
    """Pin exits to a country ({de} uses Tor's GeoIP db); None removes the restriction.

    Runtime-only (not saved to torrc). Applies to new circuits; existing ones are retired via NEWNYM.
    """
    try:
        if cc:
            ctl.set_options({"ExitNodes": "{%s}" % cc.lower(), "StrictNodes": "1"})  # SETCONF
        else:
            ctl.reset_conf("ExitNodes", "StrictNodes")  # RESETCONF
    except ControllerError as e:
        raise TorError(f"Tor rechazó la configuración: {e}")
    if ctl.is_newnym_available():
        ctl.signal(Signal.NEWNYM)


def relays_in_country(ctl: Controller, cc: str) -> list:
    """Relays of the consensus located in `cc`, strongest first.

    shortcut: one GETINFO ip-to-country per relay (~9k round trips, a few seconds); cache if it gets slow.
    """
    cc = cc.lower()
    # GETINFO ns/all: every router status entry (flags, bandwidth, address) in the consensus
    rs = [r for r in ctl.get_network_statuses() if ctl.get_info(f"ip-to-country/{r.address}", "??").lower() == cc]
    return sorted(rs, key=lambda r: r.bandwidth or 0, reverse=True)


def usable_exits(relays: list) -> list:
    return [r for r in relays if "Exit" in r.flags and "BadExit" not in r.flags and "Running" in r.flags]
