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
- **State**: the M/Monit check status, such as `Status ok` or `Running`
- **Attribute**: `status_message` contains the detailed check output

## Branding

This repository bundles M/Monit logo assets. M/Monit and related marks belong to their respective owners. The integration code is GPL-3.0, but the bundled third-party logos are not relicensed under GPL.
