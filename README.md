# Tor Circuit Monitor

Interactive Python CLI to inspect and monitor, in real time, the circuits of **your own** Tor client through its `ControlPort`, built on [`stem`](https://stem.torproject.org/) and [`rich`](https://github.com/Textualize/rich).

## Features

| Key | What it does |
|---|---|
| `c` Circuits | Table of `BUILT` circuits: `purpose`, and per hop the role (Guard / Middle / Exit / Final), flag and country, nickname, IP and flags. |
| `m` Monitor | Live view of `STREAM` and `CIRC` events: which destination your app opens and over which `CircID`. `Ctrl+C` returns to the menu. |
| `n` New identity | Sends `SIGNAL NEWNYM` to retire circuits and rotate the exit IP. |
| `e` Exit country | Pins the exit country (`ExitNodes` + `StrictNodes`). Checks first that the country has usable exits. Leave empty to remove the restriction. |
| `b` Browse relays | Lists the relays of a country (all, exits only or guards only) with fingerprint, weight and flags, and counts usable exits. |

Also:
- **Auto-detection**: tries port `9051` (Tor daemon) first, then `9151` (Tor Browser).
- **Clear errors**: closed port, unreadable cookie, missing or wrong password, and Tor disconnecting while monitoring.
- **Country lookup without sending IPs to third parties**: uses Tor's local GeoIP database (`GETINFO ip-to-country/<ip>`).

## Requirements

- Python 3.10+
- Tor running with the `ControlPort` enabled
- Tor's GeoIP database for node countries (`sudo apt install tor-geoipdb` on Debian/Ubuntu)
- A terminal with an emoji font to see flags (the country name is always shown too)

## Installation

```bash
git clone https://github.com/estebanramos/tor_monitor.git && cd tor_monitor
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## Configuring Tor

**Option A: Tor Browser (port 9151).** No setup needed: open it and run the tool.

**Option B: Tor daemon (port 9051).** In `/etc/tor/torrc`:

```
ControlPort 9051
CookieAuthentication 1
```

```bash
sudo systemctl restart tor
sudo usermod -aG debian-tor "$USER"   # log out and back in
```

The cookie (`/run/tor/control.authcookie`) belongs to the `debian-tor` group (a Debian/Ubuntu name; other distros use `tor` or similar). Group-free alternative: set `HashedControlPassword` in `torrc` and use `--password`.

> Do not loosen the cookie's permissions or run the tool as root. If your `SocksPort` listens on `0.0.0.0`, change it to `127.0.0.1:9050`.

## Usage

```bash
python main.py                  # cookie authentication
python main.py --password PW    # password authentication
```

To generate test traffic and see its `CircID` in the monitor (`m`):

```bash
curl --socks5-hostname 127.0.0.1:9050 https://check.torproject.org/api/ip
```

## How it works

| Action | `stem` call | Control protocol command |
|---|---|---|
| Connect | `Controller.from_port()`, `authenticate()` | `PROTOCOLINFO` / `AUTHENTICATE` |
| Circuits | `get_circuits()` | `GETINFO circuit-status` |
| Relay details | `get_network_status(fp)` | `GETINFO ns/id/<fp>` |
| Country of an IP | `get_info("ip-to-country/<ip>")` | `GETINFO ip-to-country/<ip>` |
| All relays | `get_network_statuses()` | `GETINFO ns/all` |
| Events | `add_event_listener(..., STREAM, CIRC)` | `SETEVENTS STREAM CIRC` |
| New identity | `signal(Signal.NEWNYM)` | `SIGNAL NEWNYM` |
| Exit country | `set_options({...})` / `reset_conf(...)` | `SETCONF` / `RESETCONF` |

The tool **observes and constrains**; it does not build circuits. Tor builds them. `ExitNodes` only affects circuits that exit to the internet (`GENERAL`, `CONFLUX_*`), not `.onion` service circuits.

## Layout

```
main.py             CLI (menu, tables, live monitor)
tor_controller.py   stem logic (connection, circuits, relays, ExitNodes)
utils.py            flag, country name and flag formatting
tests/test_utils.py tests for utils
```

## Tests

```bash
pip install pytest
pytest
```

Tests cover `utils.py` only. Anything that talks to Tor needs a running Tor and has no automated tests.

## Status and limitations

- Manually tested against Tor 0.4.9 (Debian/Ubuntu): connection, circuits, monitor, `NEWNYM`, exit country and relay browsing. Only `utils.py` has automated tests. Other Tor versions or distros may differ: please open an issue with the error.
- Browsing by country makes one query to Tor per relay (~9000) and takes a few seconds.
- Pinning the exit country **reduces your anonymity** (smaller relay set, traffic easier to correlate). Use it for testing or region-specific access, not as a default.
- If the country has no exits, Tor cannot build circuits with `StrictNodes=1`; the tool checks this before applying.
- `ExitNodes` is changed at runtime only; `torrc` is not modified.

## Responsible use

Meant to observe and manage **your own** Tor client. It only connects to the local `ControlPort` (`127.0.0.1`).

## License

MIT. See [LICENSE](LICENSE).
