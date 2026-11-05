<p align="center">
  <img src="logo.png" width="128" alt="M/Monit integration logo">
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/marketplace_repository/?owner=pschmitt&amp;repository=homeassistant-mmonit&amp;category=integration"><img src="https://my.home-assistant.io/badges/marketplace_repository.svg" alt="Open this integration in Home Assistant Marketplace"></a>
</p>

<h1 align="center">M/Monit for Home Assistant</h1>

<p align="center">Monitor hosts and checks from M/Monit, Monarch or direct Monit agents.</p>

## Features

- **Three backends:** Connect to an M/Monit server, a Monarch server or a direct Monit agent. See [Monitoring](docs/monitoring.md).
- **Host devices:** Discover monitored hosts and expose a problem binary sensor for each.
- **Check sensors:** Show check states and detailed output, without treating startup as a failure.
- **Multiple entries:** Configure separate monitoring servers and agents through the UI.

## Install

Use the Marketplace badge above on Home Assistant 2026.11 or later to add this
repository as a custom integration. On older versions, add it as a HACS
custom repository of type **Integration**. Install and restart Home Assistant.
The badge does not imply a public catalog listing. For manual installation,
copy `custom_components/mmonit/` into Home Assistant's `custom_components/`
directory and restart.

## Quick start

1. Add **M/Monit** under **Settings → Devices & services → Add integration**.
2. Choose **M/Monit**, **Monarch** or **Direct Monit** and enter its URL and credentials.
3. Inspect the discovered host devices, problem indicators and check sensors.

## Documentation

| Topic | Description |
|-------|-------------|
| [Monitoring](docs/monitoring.md) | Connection modes, sensor states and dashboard behavior |

## License

[GPL-3.0](LICENSE). M/Monit logos belong to their respective owners and are
not relicensed under GPL.
