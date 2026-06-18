#!/usr/bin/env python3
"""Generate and push the Monit dashboard (url_path: dashboard-monit).

Builds a Lovelace config for all *direct* monit hosts (mmonit integration
entries in "monit" mode, i.e. devices with manufacturer "Monit"). Most cards
use auto-entities filters on the `server_url` attribute (only direct-monit
entities carry a `*:2812` URL), so check lists stay dynamic; the per-host
sections are generated from the device/entity registries and need a re-run
(`python3 build.py --push`) when hosts are added or removed.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import socket
import struct
import subprocess
import sys
from pathlib import Path

URL_PATH = "dashboard-monit"
TITLE = "Monit"
ICON = "mdi:monitor-eye"
SNAPSHOT = Path(__file__).with_name("monit_config.json")

AP_HINTS = ("wax", "wrt", "turris", "ap")


# ================================================================ WS plumbing
def get_creds():
    """Resolve (url, token): $HASS_URL/$HASS_TOKEN, else `zhj hass::secrets-gu5a`."""
    url, token = os.environ.get("HASS_URL"), os.environ.get("HASS_TOKEN")
    if url and token:
        return url, token
    out = subprocess.run(
        ["zsh", "-lc", "zhj hass::secrets-gu5a"],
        capture_output=True, text=True,
    ).stdout.strip().splitlines()
    for line in reversed(out):
        parts = line.split()
        if len(parts) == 2 and parts[0].startswith("http"):
            return parts[0], parts[1]
    raise SystemExit("Could not resolve HA URL/token. Set HASS_URL/HASS_TOKEN or unlock rbw.")


def _ws_send(s, payload):
    data = json.dumps(payload).encode()
    frame = bytearray([0x81])
    if len(data) < 126:
        frame.append(0x80 | len(data))
    elif len(data) < 65536:
        frame.append(0x80 | 126)
        frame.extend(struct.pack(">H", len(data)))
    else:
        frame.append(0x80 | 127)
        frame.extend(struct.pack(">Q", len(data)))
    mask = os.urandom(4)
    frame.extend(mask)
    frame.extend(bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
    s.sendall(bytes(frame))


def _ws_recv(s):
    h = b""
    while len(h) < 2:
        h += s.recv(2 - len(h))
    ln = h[1] & 0x7F
    if ln == 126:
        e = b""
        while len(e) < 2:
            e += s.recv(2 - len(e))
        ln = struct.unpack(">H", e)[0]
    elif ln == 127:
        e = b""
        while len(e) < 8:
            e += s.recv(8 - len(e))
        ln = struct.unpack(">Q", e)[0]
    d = b""
    while len(d) < ln:
        c = s.recv(min(65536, ln - len(d)))
        if not c:
            break
        d += c
    return json.loads(d.decode()) if d else {}


def _connect(url, token):
    host = url.split("://")[1].split(":")[0]
    port = int(url.rsplit(":", 1)[1]) if ":" in url.split("://")[1] else 8123
    s = socket.create_connection((host, port), timeout=30)
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall(
        f"GET /api/websocket HTTP/1.1\r\nHost: {host}:{port}\r\n"
        f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n".encode()
    )
    resp = b""
    while b"\r\n\r\n" not in resp:
        resp += s.recv(4096)
    _ws_recv(s)  # auth_required
    _ws_send(s, {"type": "auth", "access_token": token})
    assert _ws_recv(s).get("type") == "auth_ok", "auth failed"
    return s


def _call(s, payload, _id=[0]):
    _id[0] += 1
    _ws_send(s, dict(payload, id=_id[0]))
    while True:
        m = _ws_recv(s)
        if m.get("id") == _id[0]:
            return m


# ================================================================== discovery
def discover(s):
    """Return the direct-monit hosts: [{name, url, status, metrics: {key: entity_id}}]."""
    devices = _call(s, {"type": "config/device_registry/list"})["result"]
    entities = _call(s, {"type": "config/entity_registry/list"})["result"]

    by_device: dict[str, list[dict]] = {}
    for ent in entities:
        if ent.get("platform") == "mmonit" and ent.get("device_id"):
            by_device.setdefault(ent["device_id"], []).append(ent)

    hosts = []
    for dev in devices:
        if dev.get("manufacturer") != "Monit":
            continue
        name = dev.get("name_by_user") or dev["name"]
        host = {
            "name": name,
            "url": dev.get("configuration_url"),
            "status": None,
            "metrics": {},
            "check_sensors": [],
        }
        for ent in by_device.get(dev["id"], []):
            unique_id = ent.get("unique_id") or ""
            if unique_id.startswith("host_status_"):
                host["status"] = ent["entity_id"]
            elif unique_id.startswith("host_metric_"):
                key = unique_id.rsplit("_host_", 1)[-1]  # cpu_usage, uptime, ...
                host["metrics"][key] = ent["entity_id"]
            elif ent.get("entity_id", "").startswith("sensor."):
                cname = ent.get("name") or ent.get("original_name") or ent["entity_id"]
                host["check_sensors"].append({"entity_id": ent["entity_id"], "name": cname})
        if host["status"]:
            hosts.append(host)

    return sorted(hosts, key=lambda h: h["name"])


# ===================================================================== layout
DIRECT = "*2812*"  # only direct-monit entities carry a *:2812 server_url

# Jinja snippets (direct-monit entity sets)
J_HOSTS = (
    "{% set xs = states.binary_sensor"
    " | selectattr('attributes.server_url', 'defined')"
    " | selectattr('attributes.server_url', 'search', ':2812') | list %}"
)
J_CHECKS = (
    "{% set cs = states.sensor"
    " | selectattr('attributes.check_id', 'defined')"
    " | selectattr('attributes.server_url', 'defined')"
    " | selectattr('attributes.server_url', 'search', ':2812') | list %}"
)
# Only LED=0 (red) counts as failing; LED=1 (initializing/starting) is transient, not a failure.
J_FAILING = J_CHECKS + "{% set failing = cs | selectattr('attributes.led', 'eq', 0) | list %}"


def host_icon(name):
    lowered = name.lower()
    if any(hint in lowered for hint in AP_HINTS):
        return "mdi:router-wireless"
    return "mdi:server"


def host_hash(name):
    return "#" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def j_host_checks(url):
    """Jinja prelude: this host's check sensors + the failing/initializing subsets."""
    return (
        "{% set cs = states.sensor"
        " | selectattr('attributes.server_url', 'defined')"
        " | selectattr('attributes.server_url', 'eq', '" + url + "')"
        " | selectattr('attributes.check_id', 'defined') | list %}"
        # led=0 → failed; led=1 → initializing/starting (transient, not a failure)
        "{% set failing = cs | selectattr('attributes.led', 'eq', 0) | list %}"
        "{% set starting = cs | selectattr('attributes.led', 'eq', 1) | list %}"
    )


def check_hash(entity_id):
    return "#check-" + entity_id


def check_popup(entity_id, check_name, host_name):
    """Bubble-card pop-up showing details for one monit check."""
    eid = entity_id
    h = check_hash(eid)
    header = {
        "type": "custom:mushroom-template-card",
        "entity": eid,
        "primary": check_name,
        "secondary": (
            host_name + " · "
            "{{ states('" + eid + "') }}"
            "{% set m = state_attr('" + eid + "', 'status_message') %}"
            "{% if m and m != states('" + eid + "') %} — {{ m }}{% endif %}"
        ),
        "icon": (
            "{{ {0:'mdi:alert-circle',1:'mdi:clock-start',2:'mdi:check-circle',3:'mdi:pause-circle'}"
            ".get(state_attr('" + eid + "','led'),'mdi:help-circle') }}"
        ),
        "icon_color": (
            "{{ {0:'red',1:'amber',2:'green',3:'disabled'}"
            ".get(state_attr('" + eid + "','led'),'blue') }}"
        ),
    }
    # Metadata vars — always fetch, render conditionally
    mv = (
        "{% set _type    = state_attr('" + eid + "', 'check_type') %}"
        "{% set _every   = state_attr('" + eid + "', 'every') %}"
        "{% set _group   = state_attr('" + eid + "', 'check_group') %}"
        "{% set _path    = state_attr('" + eid + "', 'check_path') %}"
        "{% set _port_rt = state_attr('" + eid + "', 'port_response_time') %}"
        "{% set _pid     = state_attr('" + eid + "', 'pid') %}"
        "{% set _ppid    = state_attr('" + eid + "', 'ppid') %}"
        "{% set _proc_up = state_attr('" + eid + "', 'process_uptime') %}"
        "{% set _a_start = state_attr('" + eid + "', 'action_start') %}"
        "{% set _a_stop  = state_attr('" + eid + "', 'action_stop') %}"
        "{% set _a_rst   = state_attr('" + eid + "', 'action_restart') %}"
        "{% set _reboot  = state_attr('" + eid + "', 'on_reboot') %}"
        "{% set _pend    = state_attr('" + eid + "', 'pending_action') %}"
        "{% set _output  = state_attr('" + eid + "', 'last_output') %}"
        "{% set _exit    = state_attr('" + eid + "', 'last_exit_value') %}"
        "{% set _ts      = state_attr('" + eid + "', 'data_collected') %}"
        "{% set _events  = state_attr('" + eid + "', 'last_events') %}"
    )
    meta = (
        # type · group · interval
        "{% if _type %}**{{ _type }}**"
        "{% if _group %} · {{ _group }}{% endif %}"
        "{% if _every %} · every {{ _every }}{% endif %}"
        "\n\n{% endif %}"
        # script / program path
        "{% if _path %}`{{ _path }}`\n\n{% endif %}"
        # port response time
        "{% if _port_rt %}\U0001f4e1 {{ _port_rt }}\n\n{% endif %}"
        # process: pid / ppid / uptime
        "{% if _pid %}"
        "PID {{ _pid }}{% if _ppid %} · PPID {{ _ppid }}{% endif %}"
        "{% if _proc_up %} · up {{ _proc_up }}{% endif %}\n\n"
        "{% endif %}"
        # configured actions
        "{% if _a_start or _a_stop or _a_rst %}"
        "{% if _a_start %}▶ `{{ _a_start }}`\n{% endif %}"
        "{% if _a_stop  %}⏹ `{{ _a_stop }}`\n{% endif %}"
        "{% if _a_rst   %}\U0001f504 `{{ _a_rst }}`\n{% endif %}"
        "\n{% endif %}"
        "{% if _reboot and _reboot != 'noaction' %}On reboot: {{ _reboot }}\n\n{% endif %}"
        "{% if _pend and _pend != 'none' %}⏳ Pending: {{ _pend }}\n\n{% endif %}"
    )
    runtime = (
        "**Prog output:**"
        "{% if _output %}\n\n```\n{{ _output }}\n```{% else %} *no output*{% endif %}"
        "\n\n"
        "**Prog status:** "
        "{% if _exit is not none %}{{ _exit }}{% else %}—{% endif %}"
        "{% if _ts %} · *{{ _ts | as_timestamp | timestamp_custom('%H:%M:%S') }}*{% endif %}\n"
    )
    # Events use escaped double-quotes so the regex_replace arg works in JSON
    evt_line = (
        "{{ '\U0001f534' if e.state == 1 else '✅' }} "
        "*{{ e.time | as_timestamp | timestamp_custom('%m-%d %H:%M') }}* "
        + "{{ e.message | string | regex_replace(\"^monit: '[^']+' \", '') }}\n\n"
    )
    events_md = (
        "{% if _events %}\n\n"
        "#### 📅 Events\n\n"
        "{% for e in _events %}"
        + evt_line
        + "{% endfor %}"
        "{% endif %}"
    )
    section_config = (
        "{% if _type or _path or _port_rt or _pid or _a_start or _a_stop or _a_rst %}"
        "#### ⚙️ Config\n\n"
        "{% endif %}"
    )
    detail_md = mv + section_config + meta + "#### 📊 Status\n\n" + runtime + events_md
    return {
        "type": "custom:bubble-card",
        "card_type": "pop-up",
        "popup_style": "classic",
        "hash": h,
        "name": check_name,
        "icon": "mdi:console-line",
        "cards": [
            header,
            check_action_buttons(eid),
            {"type": "markdown", "content": detail_md},
        ],
    }


def check_action_buttons(entity_id: str) -> dict:
    """Row of start/stop/restart/monitor/unmonitor buttons for a check popup."""
    buttons = [
        ("Start",     "mdi:play",    "green", "start_service"),
        ("Stop",      "mdi:stop",    "red",   "stop_service"),
        ("Restart",   "mdi:restart", "amber", "restart_service"),
        ("Monitor",   "mdi:eye",     "blue",  "monitor_service"),
        ("Unmonitor", "mdi:eye-off", "grey",  "unmonitor_service"),
    ]
    return {
        "type": "grid",
        "columns": 5,
        "square": False,
        "cards": [
            {
                "type": "custom:mushroom-template-card",
                "entity": entity_id,
                "primary": label,
                "icon": icon,
                "icon_color": color,
                "tap_action": {
                    "action": "perform-action",
                    "perform_action": f"mmonit.{service}",
                    "target": {"entity_id": entity_id},
                },
            }
            for label, icon, color, service in buttons
        ],
    }


def check_popups_section(hosts):
    """Grid of per-check popups for all known checks across all hosts."""
    popups = [
        check_popup(c["entity_id"], c["name"], host["name"])
        for host in hosts
        for c in host.get("check_sensors", [])
    ]
    return {"type": "grid", "cards": popups} if popups else None


def host_popup(host):
    """Classic bubble-card pop-up summarizing one host's health."""
    name, status, url = host["name"], host["status"], host["url"] or ""
    metrics = host["metrics"]
    prelude = j_host_checks(url)

    secondary = "{{ state_attr('%s', 'host_summary') }}" % status
    if "uptime" in metrics:
        secondary += (
            "{% set up = states('" + metrics["uptime"] + "') %}"
            "{% if up not in ('unknown', 'unavailable') %} · up {{ up }}{% endif %}"
        )
    header = {
        "type": "custom:mushroom-template-card",
        "entity": status,
        "primary": prelude
        + "{{ 'All systems operational' if failing | count == 0"
        " else failing | count ~ ' failing check' ~ ('s' if failing | count != 1) }}",
        "secondary": secondary,
        "icon": prelude + "{{ 'mdi:check-decagram' if failing | count == 0 else 'mdi:alert-decagram' }}",
        "icon_color": prelude + "{{ 'green' if failing | count == 0 else 'red' }}",
        "tap_action": {"action": "more-info"},
        "grid_options": {"columns": 12, "rows": 1},
    }

    failed_md = (
        prelude
        + "{% if failing | count == 0 %}"
        "✅ All **{{ cs | count }}** checks passing"
        "{% if starting | count > 0 %}\n\n"
        "⏳ {{ starting | count }} starting: "
        "{{ starting | map(attribute='name') | join(', ') }}{% endif %}"
        "{% else %}"
        "{% for c in failing %}"
        "{% set _msg = state_attr(c.entity_id, 'status_message') %}"
        "{% set _out = state_attr(c.entity_id, 'last_output') %}"
        "{% set _ex  = state_attr(c.entity_id, 'last_exit_value') %}"
        "{% set _ts  = state_attr(c.entity_id, 'data_collected') %}"
        "### 🔴 {{ c.name | regex_replace('^" + re.escape(name) + " ', '') }}\n"
        "**{{ c.state }}**"
        "{% if _msg and _msg != c.state %} — {{ _msg }}{% endif %}\n"
        "{% if _out %}"
        "```text\n{{ _out }}\n```\n"
        "{% endif %}"
        "{% if _ex is not none %}*exit code {{ _ex }}*{% if _ts %} · {% endif %}{% endif %}"
        "{% if _ts %}"
        "*collected {{ _ts | as_timestamp | timestamp_custom('%H:%M:%S') }}*\n"
        "{% endif %}"
        "{% endfor %}"
        "{% endif %}"
    )

    metric_tiles = [
        tile(metrics[key], color, columns=6, features=[{"type": "trend-graph"}])
        for key, color in (("cpu_usage", "amber"), ("memory_usage", "purple"))
        if key in metrics
    ]
    cards = []
    if metric_tiles:
        cards.append({"type": "grid", "columns": 2, "square": False, "cards": metric_tiles})
    cards += [header, {"type": "markdown", "content": failed_md}]

    _check_opts = {
        "primary": "{{ state_attr('this.entity_id', 'check_id') }}",
        "secondary": (
            "{{ states('this.entity_id') }}"
            "{% set m = state_attr('this.entity_id', 'status_message') %}"
            "{% if m and m != states('this.entity_id') %} — {{ m }}{% endif %}"
        ),
        "icon": (
            "{{ {0:'mdi:alert-circle',1:'mdi:clock-start',2:'mdi:check-circle',3:'mdi:pause-circle'}"
            ".get(state_attr('this.entity_id','led'),'mdi:help-circle') }}"
        ),
        "icon_color": (
            "{{ {0:'red',1:'amber',2:'green',3:'disabled'}"
            ".get(state_attr('this.entity_id','led'),'blue') }}"
        ),
        "tap_action": {"action": "navigate", "navigation_path": "#check-this.entity_id"},
    }
    for _led in (0, 1, 2, 3):
        cards.append(
            auto_mushroom_cards(
                {
                    "domain": "sensor",
                    "attributes": {"server_url": url or DIRECT, "check_id": "*", "led": _led},
                },
                _check_opts,
                sort={"method": "friendly_name", "ignore_case": True},
            )
        )

    return {
        "type": "custom:bubble-card",
        "card_type": "pop-up",
        "popup_style": "classic",
        "hash": host_hash(name),
        "name": name,
        "icon": host_icon(name),
        "cards": cards,
    }


def popups_section(hosts):
    return {"type": "grid", "cards": [host_popup(h) for h in hosts]}


def heading(text, icon=None, style="title"):
    card = {"type": "heading", "heading": text, "heading_style": style}
    if icon:
        card["icon"] = icon
    return card


def template_chip(icon, icon_color, content):
    return {
        "type": "template",
        "icon": icon,
        "icon_color": icon_color,
        "content": content,
    }


def auto_mushroom_cards(include_filter, card_options, columns=1, sort=None):
    """auto-entities rendering each match as a mushroom template card."""
    return {
        "type": "custom:auto-entities",
        "card": {"type": "grid", "columns": columns, "square": False},
        "card_param": "cards",
        "filter": {
            "include": [
                dict(
                    include_filter,
                    options=dict(
                        {
                            "type": "custom:mushroom-template-card",
                            "entity": "this.entity_id",
                            "tap_action": {"action": "more-info"},
                        },
                        **card_options,
                    ),
                )
            ]
        },
        "sort": sort if sort is not None else {"method": "friendly_name"},
        "show_empty": False,
    }


def global_failing_popup():
    """Fleet-wide bubble-card popup: header + auto-entities list of failing checks."""
    header = {
        "type": "custom:mushroom-template-card",
        "primary": (
            J_FAILING
            + "{{ 'All systems operational' if failing | count == 0"
            " else failing | count ~ ' failing check' ~ ('s' if failing | count != 1) }}"
        ),
        "secondary": (
            J_FAILING
            + "{% if failing | count > 0 %}"
            "{{ failing | map(attribute='name') | join(', ') }}"
            "{% else %}{{ cs | count }} checks green{% endif %}"
        ),
        "icon": J_FAILING + "{{ 'mdi:check-decagram' if failing | count == 0 else 'mdi:alert-decagram' }}",
        "icon_color": J_FAILING + "{{ 'green' if failing | count == 0 else 'red' }}",
        "multiline_secondary": True,
    }
    # Only show LED=0 (failed) checks here — LED=1 (starting/initializing) are not failures.
    failing_list = auto_mushroom_cards(
        {
            "domain": "sensor",
            "attributes": {"server_url": DIRECT, "led": 0},
        },
        {
            "primary": (
                "{{ state_attr('this.entity_id', 'server_name') }}"
                " / {{ state_attr('this.entity_id', 'check_id') }}"
            ),
            "secondary": (
                "{{ states('this.entity_id') }}"
                "{% set m = state_attr('this.entity_id', 'status_message') %}"
                "{% if m and m != states('this.entity_id') %} — {{ m }}{% endif %}"
                "{% set out = state_attr('this.entity_id', 'last_output') %}"
                "{% if out %}\n{{ out | truncate(200) }}{% endif %}"
            ),
            "icon": "mdi:alert-circle",
            "icon_color": "red",
            "multiline_secondary": True,
            "tap_action": {"action": "navigate", "navigation_path": "#check-this.entity_id"},
        },
    )
    return {
        "type": "custom:bubble-card",
        "card_type": "pop-up",
        "popup_style": "classic",
        "hash": "#monit-failing",
        "name": "Failing Checks",
        "icon": "mdi:alert-decagram",
        "cards": [header, failing_list],
    }


def _host_color_template(status_entity):
    """Jinja for host card color: red=failed, amber=starting, green=ok."""
    s = status_entity
    return (
        "{{ 'red' if is_state('" + s + "', 'on')"
        " else 'amber' if state_attr('" + s + "', 'led') == 1"
        " else 'green' }}"
    )


def _host_badge_template(status_entity):
    """Jinja for host card badge icon: shown only when there's a problem (led=0 or led=1)."""
    s = status_entity
    return (
        "{{ 'mdi:alert' if is_state('" + s + "', 'on')"
        " else 'mdi:clock-start' if state_attr('" + s + "', 'led') == 1 }}"
    )


def overview_view(hosts):
    health_summary = {
        "type": "custom:mushroom-template-card",
        "primary": J_FAILING
        + "{{ 'All systems operational' if failing | count == 0 else failing | count ~ ' failing check' ~ ('s' if failing | count != 1) }}",
        "icon": J_FAILING + "{{ 'mdi:check-decagram' if failing | count == 0 else 'mdi:alert-decagram' }}",
        "icon_color": J_FAILING + "{{ 'green' if failing | count == 0 else 'red' }}",
        "tap_action": {"action": "navigate", "navigation_path": "#monit-failing"},
        "grid_options": {"columns": 12, "rows": 1},
    }

    # Only LED=0 (failed) checks appear here — starting/initializing (led=1) are not failures.
    failing_checks = auto_mushroom_cards(
        {
            "domain": "sensor",
            "attributes": {"server_url": DIRECT, "led": 0},
        },
        {
            "primary": "{{ state_attr('this.entity_id', 'friendly_name') }}",
            "secondary": "{{ states('this.entity_id') }}"
            "{% set m = state_attr('this.entity_id', 'status_message') %}"
            "{% if m %} — {{ m }}{% endif %}",
            "icon": "mdi:alert-circle",
            "icon_color": "red",
            "multiline_secondary": True,
            "tap_action": {"action": "navigate", "navigation_path": "#check-this.entity_id"},
        },
    )

    fleet = {
        "type": "grid",
        "columns": 2,
        "square": False,
        "cards": [
            {
                "type": "custom:mushroom-template-card",
                "entity": h["status"],
                "primary": h["name"],
                "secondary": "{{ state_attr('%s', 'host_summary') }}" % h["status"],
                "icon": host_icon(h["name"]),
                # red=failed, amber=starting/initializing, green=ok
                "icon_color": _host_color_template(h["status"]),
                "badge_icon": _host_badge_template(h["status"]),
                "badge_color": (
                    "{{ 'red' if is_state('%s', 'on') else 'amber' }}" % h["status"]
                ),
                "tap_action": {
                    "action": "navigate",
                    "navigation_path": host_hash(h["name"]),
                },
                "hold_action": {"action": "more-info"},
            }
            for h in hosts
        ],
    }

    def graph(name, icon, metric, color_thresholds=None):
        card = {
            "type": "custom:mini-graph-card",
            "name": name,
            "icon": icon,
            "hours_to_show": 24,
            "points_per_hour": 4,
            "line_width": 2,
            "lower_bound": 0,
            "entities": [
                {"entity": h["metrics"][metric], "name": h["name"]}
                for h in hosts
                if metric in h["metrics"]
            ],
        }
        if color_thresholds:
            card["color_thresholds"] = color_thresholds
        return card

    activity = {
        "type": "logbook",
        "target": {"entity_id": [h["status"] for h in hosts]},
        "hours_to_show": 48,
    }

    return {
        "type": "sections",
        "title": "Overview",
        "path": "overview",
        "icon": "mdi:monitor-eye",
        "max_columns": 2,
        "sections": [
            {
                "type": "grid",
                "cards": [
                    heading("Monit", "mdi:monitor-eye"),
                    health_summary,
                ],
            },
            {
                "type": "grid",
                "cards": [heading("Failing checks", "mdi:alert-circle"), failing_checks],
            },
            {
                "type": "grid",
                "cards": [heading("Fleet", "mdi:server-network"), fleet],
            },
            {
                "type": "grid",
                "cards": [
                    heading("Trends", "mdi:chart-line"),
                    graph("CPU usage", "mdi:cpu-64-bit", "cpu_usage"),
                    graph("Memory usage", "mdi:memory", "memory_usage"),
                ],
            },
            {
                "type": "grid",
                "cards": [heading("Activity", "mdi:history"), activity],
            },
            popups_section(hosts),
            *(([cps] if (cps := check_popups_section(hosts)) else [])),
            {"type": "grid", "cards": [global_failing_popup()]},
        ],
    }


def tile(entity, color, columns=6, **extra):
    return dict(
        {
            "type": "tile",
            "entity": entity,
            "color": color,
            "grid_options": {"columns": columns},
        },
        **extra,
    )


def host_section(host):
    name, status = host["name"], host["status"]
    metrics = host["metrics"]

    header = {
        "type": "custom:mushroom-template-card",
        "entity": status,
        "primary": name,
        "secondary": "{{ state_attr('%s', 'host_summary') }}" % status,
        "icon": host_icon(name),
        # red=failed, amber=starting/initializing, green=ok
        "icon_color": _host_color_template(status),
        "badge_icon": _host_badge_template(status),
        "badge_color": "{{ 'red' if is_state('%s', 'on') else 'amber' }}" % status,
        "tap_action": {"action": "navigate", "navigation_path": host_hash(name)},
    }
    if host["url"]:
        header["hold_action"] = {"action": "url", "url_path": host["url"]}

    cards = [heading(name, host_icon(name)), header]

    for key, color in (
        ("cpu_usage", "amber"),
        ("memory_usage", "purple"),
        ("uptime", "green"),
        ("platform", "blue"),
    ):
        if key in metrics:
            cards.append(tile(metrics[key], color))

    cards.append(
        {
            "type": "custom:collapsable-cards",
            "title": "Checks",
            "cards": [
                {
                    "type": "custom:auto-entities",
                    "card": {"type": "entities"},
                    "filter": {
                        "include": [
                            {
                                "domain": "sensor",
                                "attributes": {
                                    "server_url": host["url"] or DIRECT,
                                    "check_id": "*",
                                },
                            }
                        ]
                    },
                    "sort": {"method": "friendly_name"},
                }
            ],
        }
    )

    return {"type": "grid", "cards": cards}


def hosts_view(hosts):
    return {
        "type": "sections",
        "title": "Hosts",
        "path": "hosts",
        "icon": "mdi:server-network",
        "max_columns": 3,
        "sections": [host_section(h) for h in hosts] + [popups_section(hosts)] + ([cps] if (cps := check_popups_section(hosts)) else []),
    }


def build(s):
    hosts = discover(s)
    if not hosts:
        raise SystemExit("No direct-monit devices found (manufacturer 'Monit')")
    print(f"Discovered {len(hosts)} monit hosts: {', '.join(h['name'] for h in hosts)}")
    return {"views": [overview_view(hosts)]}


# ======================================================================= push
def ensure_dashboard(s):
    dashboards = _call(s, {"type": "lovelace/dashboards/list"})["result"]
    if any(d.get("url_path") == URL_PATH for d in dashboards):
        return False
    res = _call(
        s,
        {
            "type": "lovelace/dashboards/create",
            "url_path": URL_PATH,
            "title": TITLE,
            "icon": ICON,
            "mode": "storage",
            "show_in_sidebar": True,
            "require_admin": False,
        },
    )
    if not res.get("success"):
        raise SystemExit(f"dashboard create failed: {res.get('error')}")
    return True


def push(s, cfg):
    res = _call(s, {"type": "lovelace/config/save", "url_path": URL_PATH, "config": cfg})
    if not res.get("success"):
        raise SystemExit(f"save failed: {res.get('error')}")
    return len(json.dumps(cfg))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--push", action="store_true", help="push the config to HA")
    parser.add_argument("--print", dest="print_", action="store_true", help="print the config")
    args = parser.parse_args()

    url, token = get_creds()
    s = _connect(url, token)
    try:
        cfg = build(s)
        SNAPSHOT.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
        print(f"Wrote snapshot: {SNAPSHOT}")
        if args.print_:
            json.dump(cfg, sys.stdout, indent=2, ensure_ascii=False)
            print()
        if args.push:
            created = ensure_dashboard(s)
            if created:
                print(f"Created dashboard {URL_PATH}")
            size = push(s, cfg)
            print(f"Pushed {size} bytes to {URL_PATH}")
    finally:
        s.close()


if __name__ == "__main__":
    main()
