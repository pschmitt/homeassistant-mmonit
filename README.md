# M/Monit for Home Assistant

`mmonit` is a Home Assistant custom integration for [M/Monit](https://mmonit.com/) that:

- supports multiple M/Monit servers through config entries,
- auto-discovers hosts from every configured server,
- creates one Home Assistant device per monitored host,
- creates one host-level problem binary sensor per monitored host,
- creates one sensor entity per M/Monit check,
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
3. Enter the M/Monit URL, username, and password.

Each configured server creates sensor entities for all discovered checks.

## Entity model

- **Device**: one per M/Monit host
- **Entity**: one binary sensor per host for the overall host status
- **Entity**: one sensor per host check
- **State**: the M/Monit check status, such as `Status ok` or `Running`
- **Attribute**: `status_message` contains the detailed check output

## Branding

This repository bundles M/Monit logo assets. M/Monit and related marks belong to their respective owners. The integration code is GPL-3.0, but the bundled third-party logos are not relicensed under GPL.
