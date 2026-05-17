# M/Monit for Home Assistant

`mmonit` is a Home Assistant custom integration for [M/Monit](https://mmonit.com/) that:

- supports multiple M/Monit servers through config entries,
- auto-discovers hosts from every configured server,
- creates one Home Assistant device per monitored host,
- creates one sensor entity per M/Monit check,
- stores the check state in the entity state and the detailed check output in the `status_message` attribute.

## Installation

### HACS

1. Open HACS.
2. Add `https://github.com/pschmitt/homeassistant-mmonit` as a custom repository of type **Integration**.
3. Install **M/Monit**.
4. Restart Home Assistant.

### Manual

Copy this repository into:

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
- **Entity**: one sensor per host check
- **State**: the M/Monit check status, such as `Status ok` or `Running`
- **Attribute**: `status_message` contains the detailed check output

