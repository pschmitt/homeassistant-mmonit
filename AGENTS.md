# AGENTS.md

## Repository overview

Custom Home Assistant integration for M/Monit and Monit. Two API backends, one entity model.

## Layout

```
custom_components/mmonit/
  api.py           — M/Monit centralized API client (JSON over HTTP)
  monit_api.py     — Direct Monit client (XML over HTTP)
  coordinator.py   — DataUpdateCoordinator, picks the right client per config entry
  models.py        — MMonitHost / MMonitCheck dataclasses (shared by both backends)
  binary_sensor.py — host-level problem sensor (on = led==0, off = ok/starting/unmonitored)
  sensor.py        — check-level sensors + host metric sensors (CPU, memory, uptime…)
  entity.py        — base entity classes with coordinator wiring
  registry.py      — unique-id helpers
  const.py         — constants (LED values, attribute names, mode names)
```

## LED semantics

The `led` attribute on check and host entities encodes health state:

| Value | Meaning | Host binary sensor |
|---|---|---|
| `0` | Failed (red) | `on` (problem) |
| `1` | Initializing / starting (yellow) | `off` (not a failure) |
| `2` | OK (green) | `off` |
| `3` | Not monitored (black) | `off` |

**Key invariant**: `is_on` on the host binary sensor is `True` only when `host.led == 0`. LED=1
(transient startup state) must never trigger a problem alert.

### Direct Monit mode

`_derive_check_led` in `monit_api.py` maps monit's `<monitor>` bitmask:
- `MONITOR_INIT` (0x2) → LED=1 (initializing)
- `MONITOR_WAITING` (0x4) → LED depends on last `<status>` (0=green, non-zero=red)
- `monitor == 0` → LED=3 (not monitored)
- `status != 0` → LED=0 (red)
- otherwise → LED=2 (green)

`_derive_host_led` in `monit_api.py` computes the host LED from check LEDs:
- any LED=0 check → host LED=0
- all checks unmonitored → host LED=3
- otherwise → host LED=2 (LED=1 checks do NOT bubble up to the host)

### M/Monit mode

The LED values come directly from the M/Monit API (`summary.get("led")` for the host,
`service.get("led")` for each check). M/Monit may report LED=1 for a host when its checks
are starting after a restart.

## Lovelace strategy

The Monit view is rendered by a JavaScript Lovelace custom strategy (`custom:monit`),
maintained separately from this integration. The strategy reads entity state at runtime —
no static config generation needed. Key invariants the strategy must respect:

- Failing checks section: filter to `attributes.led == 0` only
- LED=1 (starting/initializing): amber indicator, never counted as a failure
- `is_state('...', 'on')` on the host binary sensor reliably detects LED=0 only (after integration fix)

## Code conventions

- No test suite yet; validate manually by reloading the integration in HA.
- Format with `ruff format`, lint with `ruff check` (config in `.ruff_cache`).
- Keep `models.py` as pure dataclasses — no HA imports.
- `monit_api.py` parses Monit's XML; `api.py` parses M/Monit's JSON. Keep them independent.
- Attribute names are defined as constants in `const.py`; add new ones there, not inline.
