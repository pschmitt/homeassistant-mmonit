# M/Monit for Home Assistant

`mmonit` is a Home Assistant custom integration for [M/Monit](https://mmonit.com/) and
[Monit](https://mmonit.com/monit/) that:

- supports two modes per config entry:
  - **M/Monit (centralized)**: talks to an M/Monit server and auto-discovers all hosts it collects,
  - **Monit (direct)**: talks directly to the embedded HTTP interface of a single Monit instance —
    no M/Monit server required,
- supports multiple servers/agents through config entries,
- creates one Home Assistant device per monitored host,
- creates one host-level problem binary sensor per monitored host,
- creates one sensor entity per check,
- stores the check state in the entity state and the detailed check output in the `status_message` attribute.

## Installation

### HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=pschmitt&repository=homeassistant-mmonit&category=integration)

1. Click the badge above, or open HACS and add `https://github.com/pschmitt/homeassistant-mmonit` as a custom repository of type **Integration**.
2. Install **M/Monit**.
3. Restart Home Assistant.

### Manual

Copy `custom_components/mmonit` from this repository into:

```text
custom_components/mmonit
```

## Configuration

The integration is configured from the Home Assistant UI:

1. Go to **Settings -> Devices & services**.
2. Add **M/Monit**.
3. Pick the mode:
   - **M/Monit server (centralized)**: enter the M/Monit URL, username, and password.
   - **Monit agent (direct)**: enter the URL of the Monit instance's embedded HTTP
     interface (e.g. `http://myhost:2812`) and the credentials of an
     `allow user:password` entry from its `set httpd` block.

Each configured server or agent creates sensor entities for all discovered checks.

### Direct Monit mode notes

- Monit's httpd restricts clients by IP/hostname *and* basic auth. Home Assistant must
  be covered by an `allow` rule (IP, network range, or hostname) in addition to the
  `allow user:password` credentials.
- One config entry maps to one Monit instance (one device in Home Assistant).

## Entity model

- **Device**: one per M/Monit host
- **Entity**: one binary sensor per host for the overall host status
- **Entity**: one sensor per host check
- **State**: the M/Monit check status, such as `OK`, `Waiting`, `Initializing`, or a failure description
- **Attribute**: `status_message` contains the detailed check output
- **Attribute**: `led` encodes the check or host state: `0` = failed (red), `1` = initializing/starting (yellow), `2` = OK (green), `3` = not monitored (black)

### Host status binary sensor

The host-level binary sensor uses the `problem` device class:

- **`on`** (problem): at least one check is in a failed state (`led == 0`)
- **`off`** (no problem): all checks are OK, unmonitored, or in a transient startup state

Checks that are **initializing or starting** (`led == 1`) are not counted as failures. Monit transitions
checks through this state briefly after a restart; treating them as failures would produce spurious alerts.

## Lovelace dashboard

A dashboard build script ships at `custom_components/mmonit/dashboard/build.py`.
It generates and pushes a Lovelace dashboard (`url_path: dashboard-monit`) that shows:

- a fleet health summary with per-host status cards (red = failed, amber = starting, green = ok)
- a failing-checks list filtered to `led == 0` only — starting/initializing checks are not shown as failures
- per-host popups with CPU/memory trends, check lists grouped by LED state, and action buttons

Run from any location where the HA credentials are available:

```sh
# via HACS install
python3 /config/custom_components/mmonit/dashboard/build.py --push

# via the hass-config wrapper (if present)
cd /path/to/hass-config/dashboards/monit && python3 build.py --push
```

## Branding

This repository bundles M/Monit logo assets. M/Monit and related marks belong to their respective owners. The integration code is GPL-3.0, but the bundled third-party logos are not relicensed under GPL.
