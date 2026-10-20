"""Tor circuit monitor CLI. Run: python main.py [--password PW]"""
from __future__ import annotations

import argparse
import threading
from collections import deque

from rich.console import Console
from rich.live import Live
from rich.prompt import Prompt
from rich.table import Table

import tor_controller as tc
from utils import country_flag, country_name, fmt_flags

console = Console()


def circuits_table(ctl) -> Table:
    t = Table(title="BUILT circuits")
    for col in ("Circ", "Purpose", "Hop", "Country", "Nickname", "IP", "Flags"):
        t.add_column(col)
    for c in tc.built_circuits(ctl):
        for i, h in enumerate(c.hops):
            row = [c.id if i == 0 else "", c.purpose if i == 0 else "", h.role, f"{country_flag(h.country)} \"{country_name(h.country)}\"", h.nickname, h.ip, fmt_flags(h.flags)]
            t.add_row(*row)
        t.add_section()
    return t


def country_table(ctl, cc: str, role: str) -> Table:
    relays = tc.relays_in_country(ctl, cc)
    exits = tc.usable_exits(relays)
    shown = {"all": relays, "exit": exits, "guard": [r for r in relays if "Guard" in r.flags]}[role][:25]
    t = Table(title=f"{country_flag(cc)} {country_name(cc)}: {len(relays)} relays, {len(exits)} usable exits (top 25 by weight)")
    for col in ("Nickname", "Fingerprint", "IP", "Weight KB/s", "Flags"):
        t.add_column(col)
    for r in shown:
        t.add_row(r.nickname, r.fingerprint[:8], r.address, str(r.bandwidth or 0), fmt_flags(list(r.flags)))
    return t


def monitor(ctl) -> None:
    """Live view of STREAM events (which CircID carries each destination)."""
    events: deque[tuple[str, str, str, str]] = deque(maxlen=20)
    lost = threading.Event()  # set when Tor goes away

    def on_stream(e) -> None:
        # StreamEvent: id, status (NEW/SENTCONNECT/SUCCEEDED/CLOSED...), circ_id, target
        events.append(("STREAM", e.id, str(e.circ_id or "-"), f"{e.status} {e.target}"))

    def on_circ(e) -> None:
        events.append(("CIRC", e.id, e.id, str(e.status)))

    tc.listen(ctl, on_stream, on_circ, lost.set)
    with Live(refresh_per_second=4, console=console) as live:
        try:
            while not lost.is_set():
                t = Table(title="Live events (Ctrl+C to go back)")
                for col in ("Type", "ID", "Circ", "Detail"):
                    t.add_column(col)
                for row in list(events):
                    t.add_row(*row)
                live.update(t)
                lost.wait(0.25)
        except KeyboardInterrupt:
            pass
    if lost.is_set():
        raise tc.TorError("Tor closed the control connection while monitoring")
    ctl.remove_event_listener(on_stream)
    ctl.remove_event_listener(on_circ)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--password", help="HashedControlPassword, if not using cookie auth")
    args = ap.parse_args()
    try:
        ctl = tc.connect(args.password)
    except tc.TorError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)
    console.print(f"[green]Connected to Tor {ctl.get_version()}[/green]")
    try:
        while True:
            op = Prompt.ask("\\[c]ircuits  \\[m]onitor  \\[n]ew identity  \\[e]xit country  \\[b]rowse relays  \\[q]uit",
                            choices=["c", "m", "n", "e", "b", "q"], default="c")
            try:
                if op == "c":
                    console.print(circuits_table(ctl))
                elif op == "m":
                    monitor(ctl)
                elif op == "n":
                    tc.new_identity(ctl)
                    console.print("[green]NEWNYM sent[/green]")
                elif op == "b":
                    cc = Prompt.ask("Country code (e.g. DE)").strip()
                    if country_name(cc) == "Unknown":
                        raise tc.TorError(f"Invalid country code: {cc}")
                    role = Prompt.ask("Show", choices=["all", "exit", "guard"], default="all")
                    with console.status("Querying the consensus..."):
                        table = country_table(ctl, cc, role)
                    console.print(table)
                elif op == "e":
                    cc = Prompt.ask("Country code (e.g. DE; empty = remove restriction)", default="").strip()
                    if cc and country_name(cc) == "Unknown":
                        raise tc.TorError(f"Invalid country code: {cc}")
                    if cc and not tc.usable_exits(tc.relays_in_country(ctl, cc)):
                        raise tc.TorError(f"{country_name(cc)} has no usable exits; not applied (Tor would be left without an exit)")
                    tc.set_exit_country(ctl, cc or None)
                    console.print(f"[green]Exit pinned to {country_name(cc)}[/green]" if cc
                                  else "[green]Exit restriction removed[/green]")
                else:
                    break
            except tc.TorError as e:
                console.print(f"[yellow]{e}[/yellow]")
                if not ctl.is_alive():
                    break
            except Exception as e:  # stem SocketClosed / ControllerError when Tor dies
                console.print(f"[red]Error: {e}[/red]")
                if not ctl.is_alive():
                    break
    finally:
        ctl.close()


if __name__ == "__main__":
    main()
