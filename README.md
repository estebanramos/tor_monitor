# Tor Circuit Monitor

CLI interactiva en Python para inspeccionar y monitorear en tiempo real los circuitos de **tu propio** cliente Tor a través del `ControlPort`, usando [`stem`](https://stem.torproject.org/) y [`rich`](https://github.com/Textualize/rich).

## Funcionalidades

| Opción | Qué hace |
|---|---|
| `c` Circuitos | Tabla de circuitos `BUILT`: `purpose`, y por salto el rol (Guard / Middle / Exit / Final), bandera y país, nickname, IP y flags. |
| `m` Monitor | Vista en vivo de eventos `STREAM` y `CIRC`: a qué destino se conecta tu app y por qué `CircID` viaja. `Ctrl+C` vuelve al menú. |
| `n` Nueva identidad | Envía `SIGNAL NEWNYM` para renovar circuitos y rotar la IP de salida. |
| `e` Exit por país | Fija el país de salida (`ExitNodes` + `StrictNodes`). Antes comprueba que el país tenga exits usables. Dejar vacío quita la restricción. |
| `b` Buscar nodos | Lista los relays de un país (todos, solo exits o solo guards) con fingerprint, peso y flags, y cuenta los exits usables. |

Además:
- **Autodetección**: prueba el puerto `9051` (demonio) y luego el `9151` (Tor Browser).
- **Errores claros**: puerto cerrado, cookie ilegible, contraseña faltante o incorrecta, y desconexión de Tor durante el monitoreo.
- **Países sin enviar IPs a terceros**: usa la base GeoIP local de Tor (`GETINFO ip-to-country/<ip>`).

## Requisitos

- Python 3.10+
- Tor corriendo con el `ControlPort` habilitado
- Para el país de cada nodo: base GeoIP de Tor (`sudo apt install tor-geoipdb` en Debian/Ubuntu)
- Una terminal con fuente de emoji si quieres ver las banderas (el nombre del país se muestra igualmente)

## Instalación

```bash
git clone <url-del-repo> && cd tor_monitor
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## Configurar Tor

**Opción A: Tor Browser (puerto 9151).** No requiere configuración: ábrelo y ejecuta la herramienta.

**Opción B: demonio de Tor (puerto 9051).** En `/etc/tor/torrc`:

```
ControlPort 9051
CookieAuthentication 1
```

```bash
sudo systemctl restart tor
sudo usermod -aG debian-tor "$USER"   # cierra sesión y vuelve a entrar
```

La cookie (`/run/tor/control.authcookie`) pertenece al grupo `debian-tor` (nombre propio de Debian/Ubuntu; en otras distros puede ser `tor` u otro). Alternativa sin grupo: `HashedControlPassword` en el `torrc` y la opción `--password`.

> No abras los permisos de la cookie ni ejecutes la herramienta como root. Si tu `SocksPort` escucha en `0.0.0.0`, cámbialo a `127.0.0.1:9050`.

## Uso

```bash
python main.py                  # autenticación por cookie
python main.py --password PW    # autenticación por contraseña
```

Para generar tráfico de prueba y ver su `CircID` en el monitor (`m`):

```bash
curl --socks5-hostname 127.0.0.1:9050 https://check.torproject.org/api/ip
```

## Cómo funciona

| Acción | Llamada de `stem` | Comando del protocolo de control |
|---|---|---|
| Conectar | `Controller.from_port()`, `authenticate()` | `PROTOCOLINFO` / `AUTHENTICATE` |
| Circuitos | `get_circuits()` | `GETINFO circuit-status` |
| Datos de un relay | `get_network_status(fp)` | `GETINFO ns/id/<fp>` |
| País de una IP | `get_info("ip-to-country/<ip>")` | `GETINFO ip-to-country/<ip>` |
| Todos los relays | `get_network_statuses()` | `GETINFO ns/all` |
| Eventos | `add_event_listener(..., STREAM, CIRC)` | `SETEVENTS STREAM CIRC` |
| Nueva identidad | `signal(Signal.NEWNYM)` | `SIGNAL NEWNYM` |
| Exit por país | `set_options({...})` / `reset_conf(...)` | `SETCONF` / `RESETCONF` |

La herramienta **observa y restringe**; no construye circuitos. Los circuitos los construye Tor. `ExitNodes` solo afecta a los circuitos que salen a internet (`GENERAL`, `CONFLUX_*`), no a los de servicios `.onion`.

## Estructura

```
main.py                         CLI (menú, tablas, monitor en vivo)
tor_controller.py               lógica de stem (conexión, circuitos, relays, ExitNodes)
utils.py                        bandera, nombre de país y formato de flags
tests/test_utils.py             tests de utils
conceptos_para_notebooklm.md    conceptos de Tor y de la herramienta (material de estudio)
```

## Tests

```bash
pip install pytest
pytest
```

Los tests cubren solo `utils.py`. La parte que habla con Tor requiere un Tor en ejecución y no tiene tests automáticos.

## Estado y limitaciones

- Desarrollada con pruebas de importación y de `utils.py`. La interacción con un Tor en vivo (listado de circuitos, monitor, `ExitNodes`, `get_network_statuses()` con Tor 0.4.9) no está validada de extremo a extremo: si algo falla, abre un issue con el error.
- La búsqueda por país hace una consulta a Tor por relay (~9000) y tarda unos segundos.
- Fijar el país de salida **reduce tu anonimato** (conjunto de relays más pequeño, tráfico más fácil de correlacionar). Úsalo para pruebas o para acceder a contenido por región, no como configuración habitual.
- Si el país no tiene exits, Tor no puede construir circuitos con `StrictNodes=1`; la herramienta lo comprueba antes de aplicarlo.
- `ExitNodes` se cambia solo en tiempo de ejecución; no modifica el `torrc`.

## Uso responsable

Pensada para observar y administrar **tu propio** cliente Tor. Se conecta únicamente al `ControlPort` local (`127.0.0.1`).

## Licencia

MIT. Ver [LICENSE](LICENSE).
