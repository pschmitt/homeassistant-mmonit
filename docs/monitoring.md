# Monitoring

Choose one of three sources when adding the integration in Home Assistant:

- **M/Monit server:** Enter the server URL, username and password. The
  integration discovers the hosts collected by M/Monit.
- **Monarch server:** Enter its URL and an API token created under Monarch's
  user menu. A viewer token is read-only; use an operator-role account or
  higher to start, stop or restart services from Home Assistant.
- **Direct Monit agent:** Enter a single agent's embedded HTTP interface URL
  and credentials from an `allow user:password` entry in its `set httpd`
  block. The agent must also allow Home Assistant's client address through
  Monit's IP or hostname access rules.

Multiple servers or agents can be configured as separate entries. A direct
Monit entry corresponds to one Home Assistant device.

## Entities and state

Each discovered host gets a device, a host-level problem binary sensor and a
sensor per check. Check state describes the status (for example `OK`,
`Waiting` or `Initializing`), with detailed check output in `status_message`.
The `led` attribute indicates failed (`0`), initializing (`1`), OK (`2`) or
unmonitored (`3`). The host problem sensor turns on only for failures (`0`):
starting and initializing checks are not failures.

A separate `custom:monit` Lovelace strategy builds a view dynamically from
the entity registry. It shows initializing checks as amber indicators without
counting them as failures.
