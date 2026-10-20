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
    t = Table(title="Circuitos BUILT")
    for col in ("Circ", "Purpose", "Salto", "Nickname", "IP", "Flags"):
        t.add_column(col)
    for c in tc.built_circuits(ctl):
        for i, h in enumerate(c.hops):
            row = [c.id if i == 0 else "", c.purpose if i == 0 else "", h.role, f"{country_flag(h.country)} \"{country_name(h.country)}\" {h.nickname}", h.ip, fmt_flags(h.flags)]
            t.add_row(*row)
        t.add_section()
    return t


def country_table(ctl, cc: str, role: str) -> Table:
    relays = tc.relays_in_country(ctl, cc)
    exits = tc.usable_exits(relays)
    shown = {"todos": relays, "exit": exits, "guard": [r for r in relays if "Guard" in r.flags]}[role][:25]
    t = Table(title=f"{country_flag(cc)} {country_name(cc)}: {len(relays)} relays, {len(exits)} exits usables (top 25 por peso)")
    for col in ("Nickname", "Fingerprint", "IP", "Peso KB/s", "Flags"):
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
                t = Table(title="Eventos en vivo (Ctrl+C para volver)")
                for col in ("Tipo", "ID", "Circ", "Detalle"):
                    t.add_column(col)
                for row in list(events):
                    t.add_row(*row)
                live.update(t)
                lost.wait(0.25)
        except KeyboardInterrupt:
            pass
    if lost.is_set():
        raise tc.TorError("Tor cerró la conexión de control durante el monitoreo")
    ctl.remove_event_listener(on_stream)
    ctl.remove_event_listener(on_circ)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--password", help="HashedControlPassword, si no usas cookie")
    args = ap.parse_args()
    try:
        ctl = tc.connect(args.password)
    except tc.TorError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)
    console.print(f"[green]Conectado a Tor {ctl.get_version()}[/green]")
    try:
        while True:
            op = Prompt.ask("[c]ircuitos  [m]onitor  [n]ueva identidad  [e]xit por país  [b]uscar nodos  [q]salir",
                            choices=["c", "m", "n", "e", "b", "q"], default="c")
            try:
                if op == "c":
                    console.print(circuits_table(ctl))
                elif op == "m":
                    monitor(ctl)
                elif op == "n":
                    tc.new_identity(ctl)
                    console.print("[green]NEWNYM enviado[/green]")
                elif op == "b":
                    cc = Prompt.ask("Código de país (ej. DE)").strip()
                    if country_name(cc) == "Desconocido":
                        raise tc.TorError(f"Código de país inválido: {cc}")
                    role = Prompt.ask("Mostrar", choices=["todos", "exit", "guard"], default="todos")
                    with console.status("Consultando el consenso..."):
                        table = country_table(ctl, cc, role)
                    console.print(table)
                elif op == "e":
                    cc = Prompt.ask("Código de país (ej. DE; vacío = quitar restricción)", default="").strip()
                    if cc and country_name(cc) == "Desconocido":
                        raise tc.TorError(f"Código de país inválido: {cc}")
                    if cc and not tc.usable_exits(tc.relays_in_country(ctl, cc)):
                        raise tc.TorError(f"{country_name(cc)} no tiene exits usables; no se aplicó (Tor quedaría sin salida)")
                    tc.set_exit_country(ctl, cc or None)
                    console.print(f"[green]Exit fijado a {country_name(cc)}[/green]" if cc
                                  else "[green]Restricción de exit quitada[/green]")
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
