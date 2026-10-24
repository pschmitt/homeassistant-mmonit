/**
 * Monit Lovelace view strategy.
 *
 * Registers as `ll-strategy-view-monit`.  Use in any dashboard:
 *
 *   views:
 *     - strategy:
 *         type: custom:monit
 *       title: Monit
 *       icon: mdi:monitor-eye
 *       type: sections
 *
 * Options:
 *   source: device manufacturer of the hosts to show: "Monit" (default,
 *           direct Monit), "Monarch" or "M/Monit".
 *
 * Requires: bubble-card, mushroom, auto-entities (HACS) and the mmonit
 * custom integration.
 */

const AP_HINTS = ["wax", "wrt", "turris", "ap"];

const DOWN_STATES = ["unavailable", "unknown"];

// ─── tiny helpers ────────────────────────────────────────────────────────────

function hostIcon(name) {
  const lower = name.toLowerCase();
  return AP_HINTS.some((h) => lower.includes(h))
    ? "mdi:router-wireless"
    : "mdi:server";
}

function hostHash(name) {
  return "#" + name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function checkHash(entityId) {
  return "#check-" + entityId;
}

function heading(text, icon, style = "title") {
  const card = { type: "heading", heading: text, heading_style: style };
  if (icon) card.icon = icon;
  return card;
}

function tile(entity, color, extra = {}) {
  return { type: "tile", entity, color, ...extra };
}

// Template fragment surfacing live system readings (load/CPU/mem/swap).
// Monit never says *which* resource limit tripped, so for system checks we
// show the readings and let the abnormal one stand out. `eid` may be a real
// entity id or the auto-entities placeholder "this.entity_id".
function resSummaryFrag(eid) {
  return (
    `{% set rs = state_attr('${eid}', 'resource_summary') %}` +
    `{% if rs %}\n📈 {{ rs }}{% endif %}`
  );
}

// Icon and colour of a check, by its LED (0 failed, 1 starting, 2 ok, 3 not
// monitored).
function ledIcon(eid) {
  return (
    `{{ {0:'mdi:alert-circle',1:'mdi:alert',2:'mdi:check-circle',3:'mdi:pause-circle'}` +
    `.get(state_attr('${eid}','led'),'mdi:help-circle') }}`
  );
}

function ledColor(eid) {
  return (
    `{{ {0:'red',1:'amber',2:'green',3:'disabled'}` +
    `.get(state_attr('${eid}','led'),'disabled') }}`
  );
}

// "Status failed — reason", with the system readings when there are any.
function checkStateFrag(eid) {
  return (
    `{{ states('${eid}') }}` +
    `{% set m = state_attr('${eid}', 'status_message') %}` +
    `{% if m and m != states('${eid}') %} — {{ m }}{% endif %}` +
    resSummaryFrag(eid)
  );
}

// ─── auto-entities helper ────────────────────────────────────────────────────

// Cards for the matching entities, kept current as states change: auto-entities
// substitutes "this.entity_id" anywhere in the card options.
function autoMushroomCards(filter, cardOptions, sort = null) {
  return {
    type: "custom:auto-entities",
    card: { type: "grid", columns: 1, square: false },
    card_param: "cards",
    filter: {
      include: [
        {
          ...filter,
          options: {
            type: "custom:mushroom-template-card",
            entity: "this.entity_id",
            tap_action: { action: "more-info" },
            ...cardOptions,
          },
        },
      ],
    },
    sort: sort ?? { method: "friendly_name" },
    show_empty: false,
  };
}

// ─── check cards ─────────────────────────────────────────────────────────────

function checkActionButtons(entityId) {
  const eid = entityId;

  function btn(label, icon, color, service) {
    return {
      type: "custom:mushroom-template-card",
      entity: eid,
      primary: label,
      icon,
      icon_color: color,
      tap_action: {
        action: "perform-action",
        perform_action: `mmonit.${service}`,
        target: { entity_id: eid },
      },
    };
  }

  // Start / Stop / Restart row — always rendered; pressing on a check that has
  // no start/stop actions (e.g. filesystem, network) is a harmless no-op.
  const controlRow = {
    type: "grid",
    columns: 3,
    square: false,
    cards: [
      btn("Start",   "mdi:play",    "green", "start_service"),
      btn("Stop",    "mdi:stop",    "red",   "stop_service"),
      btn("Restart", "mdi:restart", "amber", "restart_service"),
    ],
  };

  // Monitor / Unmonitor toggle — exactly one is shown at a time.
  // Uses state-based conditions (no `condition: template` needed): the entity
  // state is "Not monitored" when monitor_state == 0, anything else otherwise.
  const monitorRow = {
    type: "grid",
    columns: 1,
    square: false,
    cards: [
      {
        type: "conditional",
        conditions: [{ entity: eid, state: "Not monitored" }],
        card: btn("Monitor", "mdi:eye", "blue", "monitor_service"),
      },
      {
        type: "conditional",
        conditions: [{ entity: eid, state_not: "Not monitored" }],
        card: btn("Unmonitor", "mdi:eye-off", "grey", "unmonitor_service"),
      },
    ],
  };

  return { type: "vertical-stack", cards: [controlRow, monitorRow] };
}

// Detailed clickable card for a failing check: reason, program output, exit
// code and when Monit last looked. `eid` may be "this.entity_id" (auto-entities).
function failingCheckDetailCard(eid, primary, prefix = "") {
  return {
    type: "custom:mushroom-template-card",
    entity: eid,
    primary,
    secondary:
      prefix +
      checkStateFrag(eid) +
      `{% set out = state_attr('${eid}', 'last_output') %}` +
      `{% if out %}\n{{ out | truncate(500) }}{% endif %}` +
      `{% set ex = state_attr('${eid}', 'last_exit_value') %}` +
      `{% if ex is not none %}\nexit code {{ ex }}{% endif %}` +
      `{% set ts = state_attr('${eid}', 'data_collected') %}` +
      `{% if ts %}\n{{ ts | as_timestamp | timestamp_custom('%Y-%m-%d %H:%M:%S') }}{% endif %}`,
    multiline_secondary: true,
    icon: ledIcon(eid),
    icon_color: ledColor(eid),
    tap_action: { action: "navigate", navigation_path: checkHash(eid) },
  };
}

// Compact check row card used inside the host popup's sorted check list.
function checkRowCard(eid, checkName) {
  return {
    type: "custom:mushroom-template-card",
    entity: eid,
    primary: checkName,
    secondary: checkStateFrag(eid),
    multiline_secondary: true,
    icon: ledIcon(eid),
    icon_color: ledColor(eid),
    tap_action: { action: "navigate", navigation_path: checkHash(eid) },
  };
}

// Full check detail popup (bubble-card pop-up).
function checkPopup(eid, checkName, hostName) {
  const header = {
    type: "custom:mushroom-template-card",
    entity: eid,
    primary: checkName,
    secondary: `${hostName} · ` + checkStateFrag(eid),
    multiline_secondary: true,
    icon: ledIcon(eid),
    icon_color: ledColor(eid),
  };

  const vars = [
    `{%- set _type    = state_attr('${eid}', 'check_type') -%}`,
    `{%- set _every   = state_attr('${eid}', 'every') -%}`,
    `{%- set _group   = state_attr('${eid}', 'check_group') -%}`,
    `{%- set _path    = state_attr('${eid}', 'check_path') -%}`,
    `{%- set _port_rt = state_attr('${eid}', 'port_response_time') -%}`,
    `{%- set _pid     = state_attr('${eid}', 'pid') -%}`,
    `{%- set _ppid    = state_attr('${eid}', 'ppid') -%}`,
    `{%- set _proc_up = state_attr('${eid}', 'process_uptime') -%}`,
    `{%- set _a_start = state_attr('${eid}', 'action_start') -%}`,
    `{%- set _a_stop  = state_attr('${eid}', 'action_stop') -%}`,
    `{%- set _a_rst   = state_attr('${eid}', 'action_restart') -%}`,
    `{%- set _reboot  = state_attr('${eid}', 'on_reboot') -%}`,
    `{%- set _pend    = state_attr('${eid}', 'pending_action') -%}`,
    `{%- set _output  = state_attr('${eid}', 'last_output') -%}`,
    `{%- set _exit    = state_attr('${eid}', 'last_exit_value') -%}`,
    `{%- set _ts      = state_attr('${eid}', 'data_collected') -%}`,
    `{%- set _res     = state_attr('${eid}', 'resource_summary') -%}`,
    `{%- set _load1   = state_attr('${eid}', 'system_load_1m') -%}`,
    `{%- set _load5   = state_attr('${eid}', 'system_load_5m') -%}`,
    `{%- set _load15  = state_attr('${eid}', 'system_load_15m') -%}`,
    `{%- set _lpc     = state_attr('${eid}', 'system_load_per_core') -%}`,
  ].join("\n");

  const cfgSection =
    "{% if _type or _path or _port_rt or _pid or _a_start or _a_stop or _a_rst %}" +
    "#### ⚙️ Config\n\n{% endif %}";

  const meta = [
    "{% if _type %}**{{ _type }}**{% if _group %} · {{ _group }}{% endif %}{% if _every %} · every {{ _every }}{% endif %}\n\n{% endif %}",
    "{% if _path %}`{{ _path }}`\n\n{% endif %}",
    "{% if _port_rt %}📡 {{ _port_rt }}\n\n{% endif %}",
    "{% if _pid %}PID {{ _pid }}{% if _ppid %} · PPID {{ _ppid }}{% endif %}{% if _proc_up %} · up {{ _proc_up }}{% endif %}\n\n{% endif %}",
    "{% if _a_start or _a_stop or _a_rst %}{% if _a_start %}▶ `{{ _a_start }}`\n{% endif %}{% if _a_stop %}⏹ `{{ _a_stop }}`\n{% endif %}{% if _a_rst %}🔄 `{{ _a_rst }}`\n{% endif %}\n{% endif %}",
    "{% if _reboot and _reboot != 'noaction' %}On reboot: {{ _reboot }}\n\n{% endif %}",
    "{% if _pend and _pend != 'none' %}⏳ Pending: {{ _pend }}\n\n{% endif %}",
  ].join("");

  const runtime =
    "**Prog output:**" +
    "{% if _output %}\n\n```\n{{ _output }}\n```{% else %} *no output*{% endif %}" +
    "\n\n**Prog status:** {% if _exit is not none %}{{ _exit }}{% else %}—{% endif %}\n" +
    "{% if _ts %}\n*Last check: {{ _ts | as_timestamp | timestamp_custom('%Y-%m-%d %H:%M:%S') }}*\n{% endif %}";

  // System checks fail with an opaque "Resource limit matched" — surface the
  // live readings so the offending resource (load / CPU / memory / swap) shows.
  const resources =
    "{% if _res %}\n\n#### 📈 Resource readings\n\n" +
    "{{ _res }}\n" +
    "{% if _load1 is not none %}\n\n**Load avg:** {{ _load1 }} · {{ _load5 }} · {{ _load15 }} (1m · 5m · 15m)" +
    "{% if _lpc is not none %} → **{{ _lpc }} / core**{% endif %}\n{% endif %}" +
    "{% endif %}";

  const content =
    vars + "\n" + cfgSection + meta + "#### 📊 Status\n\n" + runtime + resources;

  return {
    type: "custom:bubble-card",
    card_type: "pop-up",
    popup_style: "classic",
    hash: checkHash(eid),
    name: checkName,
    icon: "mdi:console-line",
    cards: [header, checkActionButtons(eid), { type: "markdown", content }],
  };
}

// ─── host popup ──────────────────────────────────────────────────────────────

function hostPopup(host, manufacturer) {
  const { name, status, metrics, checks } = host;

  // Live from the host's status sensor: failed_checks lists the LED 0 checks
  // (LED 1, starting, is not a failure); unavailable when Monit is unreachable.
  const prelude =
    `{%- set down = states('${status}') in ${JSON.stringify(DOWN_STATES)} -%}` +
    `{%- set n = (state_attr('${status}', 'failed_checks') or []) | count -%}`;

  const header = {
    type: "custom:mushroom-template-card",
    entity: status,
    primary:
      prelude +
      "{{ 'Monit unreachable' if down else 'All systems operational' if n == 0" +
      " else n ~ ' failing check' ~ ('s' if n != 1 else '') }}",
    secondary:
      prelude +
      `{{ 'No data from this host' if down else state_attr('${status}', 'host_summary') }}` +
      (metrics.uptime
        ? `{% set up = states('${metrics.uptime}') %}{% if up not in ${JSON.stringify(DOWN_STATES)} %} · up {{ up }}{% endif %}`
        : ""),
    icon:
      prelude +
      "{{ 'mdi:lan-disconnect' if down else 'mdi:check-decagram' if n == 0 else 'mdi:alert-decagram' }}",
    icon_color:
      prelude + "{{ 'disabled' if down else 'green' if n == 0 else 'red' }}",
    tap_action: { action: "more-info" },
    grid_options: { columns: 12, rows: 1 },
  };

  const metricTiles = [];
  if (metrics.cpu_usage) {
    metricTiles.push(tile(metrics.cpu_usage, "amber", { grid_options: { columns: 6 }, features: [{ type: "trend-graph" }] }));
  }
  if (metrics.memory_usage) {
    metricTiles.push(tile(metrics.memory_usage, "purple", { grid_options: { columns: 6 }, features: [{ type: "trend-graph" }] }));
  }
  if (metrics.load_15m) {
    metricTiles.push(tile(metrics.load_15m, "blue", { grid_options: { columns: 6 }, features: [{ type: "trend-graph" }] }));
  }
  if (metrics.swap_usage) {
    metricTiles.push(tile(metrics.swap_usage, "teal", { grid_options: { columns: 6 }, features: [{ type: "trend-graph" }] }));
  }

  const cards = [];
  if (metricTiles.length) {
    cards.push({ type: "grid", columns: 2, square: false, cards: metricTiles });
  }
  cards.push(header);

  // Failing checks in detail, live (also those failing only after the page
  // loaded), then every check alphabetically with its live LED.
  cards.push(
    autoMushroomCards(
      {
        domain: "sensor",
        device: host.device_id,
        device_manufacturer: manufacturer,
        attributes: { led: 0 },
      },
      failingCheckDetailCard(
        "this.entity_id",
        "{{ state_attr('this.entity_id', 'check_id') }}",
      ),
    ),
  );
  cards.push({
    type: "grid",
    columns: 1,
    square: false,
    cards: [...checks]
      .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }))
      .map((c) => checkRowCard(c.entity_id, c.name)),
  });

  return {
    type: "custom:bubble-card",
    card_type: "pop-up",
    popup_style: "classic",
    hash: hostHash(name),
    name,
    icon: hostIcon(name),
    cards,
  };
}

// ─── fleet summary card ──────────────────────────────────────────────────────

class MonitFleetSummaryCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.categories = [
      { key: "healthy", label: "Healthy", color: "#39d98a" },
      { key: "failed", label: "Needs attention", color: "#ff657a" },
      { key: "starting", label: "Starting", color: "#ffc857" },
      { key: "unreachable", label: "Unreachable", color: "#9aa6b2" },
      { key: "unmonitored", label: "Unmonitored", color: "#6f83ff" },
    ];
  }

  setConfig(config) {
    this.config = config;
    if (this._hass) this.render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._rendered) this.render();
    else this.update();
  }

  getCardSize() {
    return 3;
  }

  render() {
    if (!this.config || !this._hass) return;

    const circumference = 2 * Math.PI * 48;
    const rings = this.categories
      .map(
        ({ key, color, label }) =>
          `<circle class="segment" data-key="${key}" cx="64" cy="64" r="48" fill="none" stroke="${color}" stroke-width="14" stroke-dasharray="0 ${circumference}" stroke-dashoffset="0" transform="rotate(-90 64 64)" style="display:none"><title>${label}</title></circle>`,
      )
      .join("");
    const legend = this.categories
      .map(
        ({ key, label, color }) =>
          `<div class="legend-row" data-key="${key}" tabindex="0"><span class="dot" style="--accent:${color}"></span><span class="label">${label}</span><strong class="count">0</strong><span class="host-tooltip" role="tooltip"></span></div>`,
      )
      .join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; }
        .card {
          --surface: var(--ha-card-background, var(--card-background-color, #1d2026));
          --muted: var(--secondary-text-color, #a8b0bc);
          background: linear-gradient(145deg, color-mix(in srgb, var(--surface) 94%, #52617a), var(--surface));
          border: 1px solid color-mix(in srgb, var(--primary-text-color, #fff) 9%, transparent);
          border-radius: 18px; box-shadow: 0 8px 24px #0002; color: var(--primary-text-color);
          padding: 18px 20px; transition: box-shadow 180ms ease, border-color 180ms ease;
        }
        .card:hover { box-shadow: 0 9px 26px #0003; border-color: color-mix(in srgb, #79a9ff 35%, transparent); }
        .layout { display:grid; grid-template-columns:132px minmax(0,1fr); align-items:center; gap:18px; }
        .chart { width:132px; height:132px; overflow:visible; }
        .track { stroke:color-mix(in srgb, var(--primary-text-color,#fff) 8%,transparent); }
        .segment { cursor:help; transition:stroke-width 160ms ease, filter 160ms ease, opacity 160ms ease; }
        .segment:hover { stroke-width:20px; filter:drop-shadow(0 0 5px #fff8); }
        .center-count { fill:var(--primary-text-color); font-size:25px; font-weight:700; text-anchor:middle; dominant-baseline:central; }
        .center-label { fill:var(--muted); font-size:9px; letter-spacing:1.2px; text-anchor:middle; }
        .content { min-width:0; }
        .headline { font-size:17px; font-weight:650; line-height:1.25; margin:0 0 4px; }
        .subhead { color:var(--muted); font-size:12px; margin:0 0 13px; }
        .legend { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:7px 14px; }
        .legend-row { align-items:center; border-radius:8px; display:flex; gap:7px; min-width:0; padding:3px 5px; transition:background 150ms ease; }
        .legend-row:hover,.legend-row:focus-visible { background:color-mix(in srgb,var(--primary-text-color,#fff) 7%,transparent); outline:none; z-index:20; }
        .host-tooltip { background:var(--card-background-color,#202329); border:1px solid color-mix(in srgb,var(--primary-text-color,#fff) 12%,transparent); border-radius:8px; box-shadow:0 6px 18px #0005; color:var(--primary-text-color); display:none; font-size:12px; left:0; line-height:1.45; max-height:180px; max-width:min(260px,calc(100vw - 48px)); overflow:auto; padding:8px 10px; pointer-events:auto; position:absolute; top:calc(100% + 3px); white-space:pre-line; width:max-content; z-index:10; }
        .legend-row { position:relative; }
        .legend-row:hover .host-tooltip,.legend-row:focus-visible .host-tooltip { display:block; }
        .dot { background:var(--accent); border-radius:50%; flex:none; height:8px; width:8px; box-shadow:0 0 10px color-mix(in srgb,var(--accent) 50%,transparent); }
        .label { color:var(--muted); font-size:12px; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .count { font-size:12px; }
        @media(max-width:500px) { .card{padding:15px}.layout{grid-template-columns:100px minmax(0,1fr);gap:12px}.chart{width:100px;height:100px}.legend{grid-template-columns:1fr;gap:3px}.headline{font-size:15px} }
      </style>
      <ha-card class="card"><div class="layout">
        <svg class="chart" viewBox="0 0 128 128" role="img">
          <circle class="track" cx="64" cy="64" r="48" fill="none" stroke-width="14"></circle>
          ${rings}<text class="center-count" x="64" y="61">0</text>
          <text class="center-label" x="64" y="80">NODES</text>
        </svg>
        <div class="content"><p class="headline"></p>
          <p class="subhead"></p>
          <div class="legend">${legend}</div>
        </div>
      </div></ha-card>`;

    this._rendered = true;
    this._lastSnapshot = null;
    this.shadowRoot.querySelectorAll(".legend-row").forEach((item) => {
      const key = item.getAttribute("data-key");
      item.addEventListener("mouseenter", () => this.highlight(key));
      item.addEventListener("mouseleave", () => this.highlight(null));
      item.addEventListener("focus", () => this.highlight(key));
      item.addEventListener("blur", () => this.highlight(null));
    });
    this.update();
  }

  update() {
    if (!this.config || !this._hass || !this._rendered) return;

    const counts = Object.fromEntries(this.categories.map(({ key }) => [key, 0]));
    const hostsByCategory = Object.fromEntries(
      this.categories.map(({ key }) => [key, []]),
    );
    const hosts = this.config.hosts || (this.config.entities || []).map((entity) => ({ entity }));
    for (const host of hosts) {
      const entityId = host.entity;
      const state = this._hass.states[entityId];
      let key;
      if (!state || ["unknown", "unavailable"].includes(state.state)) {
        key = "unreachable";
      } else if (state.state === "on") {
        key = "failed";
      } else if (state.attributes?.led === 1) {
        key = "starting";
      } else if (state.attributes?.led === 3) {
        key = "unmonitored";
      } else {
        key = "healthy";
      }
      counts[key] += 1;
      const fallbackName = (state?.attributes?.friendly_name || entityId).replace(
        /\s+status$/i,
        "",
      );
      hostsByCategory[key].push(host.name || fallbackName);
    }

    const snapshot = JSON.stringify({ counts, hostsByCategory });
    if (snapshot === this._lastSnapshot) return;
    this._lastSnapshot = snapshot;

    const total = Object.values(counts).reduce((sum, count) => sum + count, 0);
    const issues = counts.failed + counts.unreachable;
    const headline = total === 0
      ? "No monitored nodes"
      : issues
        ? `${issues} node${issues === 1 ? "" : "s"} need attention`
        : counts.starting
          ? "Fleet is coming online"
          : "All systems operational";
    const circumference = 2 * Math.PI * 48;
    let offset = 0;
    for (const { key, label } of this.categories) {
      const segment = this.shadowRoot.querySelector(`.segment[data-key="${key}"]`);
      const count = counts[key];
      const length = (count / Math.max(total, 1)) * circumference;
      segment.style.display = count > 0 ? "" : "none";
      segment.setAttribute("stroke-dasharray", `${length} ${circumference - length}`);
      segment.setAttribute("stroke-dashoffset", `${-offset}`);
      const names = hostsByCategory[key];
      segment.querySelector("title").textContent =
        `${label}: ${count}\n${names.join("\n")}`;
      offset += length;

      const row = this.shadowRoot.querySelector(`.legend-row[data-key="${key}"]`);
      row.querySelector(".count").textContent = count;
      row.querySelector(".host-tooltip").textContent =
        `${count} host${count === 1 ? "" : "s"}\n${names.join("\n")}`;
      row.setAttribute("aria-label", `${label}: ${count}; ${names.join(", ")}`);
    }

    this.shadowRoot.querySelector(".center-count").textContent = total;
    this.shadowRoot.querySelector(".chart").setAttribute("aria-label", headline);
    this.shadowRoot.querySelector(".headline").textContent = headline;
    this.shadowRoot.querySelector(".subhead").textContent =
      `${total} monitored node${total === 1 ? "" : "s"} · live status`;
  }

  highlight(key) {
    this.shadowRoot.querySelectorAll(".segment").forEach((segment) => {
      segment.style.opacity = !key || segment.dataset.key === key ? "1" : "0.32";
    });
  }
}

if (!customElements.get("monit-fleet-summary-card")) {
  customElements.define("monit-fleet-summary-card", MonitFleetSummaryCard);
  window.customCards ||= [];
  window.customCards.push({
    type: "monit-fleet-summary-card",
    name: "Monit Fleet Summary",
    description: "Live status summary for Monit or Monarch hosts.",
  });
}

// ─── discovery ───────────────────────────────────────────────────────────────

async function discoverHosts(hass, manufacturer) {
  const [devices, entities] = await Promise.all([
    hass.callWS({ type: "config/device_registry/list" }),
    hass.callWS({ type: "config/entity_registry/list" }),
  ]);

  // Index entities by device_id, filtered to mmonit platform
  const byDevice = {};
  for (const ent of entities) {
    if (ent.platform === "mmonit" && ent.device_id && !ent.disabled_by) {
      (byDevice[ent.device_id] ||= []).push(ent);
    }
  }

  const hosts = [];
  for (const dev of devices) {
    if (dev.manufacturer !== manufacturer) continue;

    const name = dev.name_by_user || dev.name;
    const host = {
      name,
      device_id: dev.id,
      status: null,
      metrics: {},
      checks: [],
    };

    for (const ent of byDevice[dev.id] || []) {
      const uid = ent.unique_id || "";

      if (uid.startsWith("host_status_")) {
        host.status = ent.entity_id;
      } else if (uid.startsWith("host_metric_")) {
        // Format: host_metric_{entry_id}_{host_id}_host_{metric_key}
        // rsplit on "_host_" gives: [..., metric_key]
        const parts = uid.split("_host_");
        const key = parts[parts.length - 1]; // "cpu_usage", "memory_usage", ...
        host.metrics[key] = ent.entity_id;
      } else if (ent.entity_id.startsWith("sensor.")) {
        // A check. While its host is unreachable it has no attributes: fall
        // back to the registry name so the check is still listed.
        const state = hass.states[ent.entity_id];
        const prefix = `${name} `;
        let fallback = ent.name || ent.original_name || ent.entity_id;
        if (fallback.startsWith(prefix)) fallback = fallback.slice(prefix.length);
        host.checks.push({
          entity_id: ent.entity_id,
          name: state?.attributes?.check_id ?? fallback,
        });
      }
    }

    if (host.status) hosts.push(host);
  }

  return hosts.sort((a, b) => a.name.localeCompare(b.name));
}

// ─── strategy ────────────────────────────────────────────────────────────────

class MonitViewStrategy {
  static async generate(config, hass) {
    const manufacturer = config?.source || "Monit";
    const hosts = await discoverHosts(hass, manufacturer);

    if (!hosts.length) {
      return {
        cards: [{
          type: "markdown",
          content: `No ${manufacturer} hosts found. Add a Monit integration entry (manufacturer: ${manufacturer}).`,
        }],
      };
    }

    const statusIds = hosts.map((h) => h.status);
    // ── top section: live summary, then whatever needs attention ──
    const summary = {
      type: "custom:monit-fleet-summary-card",
      hosts: hosts.map(({ name, status }) => ({ name, entity: status })),
    };

    // Failing checks of every host, kept current without a page reload.
    const failing = autoMushroomCards(
      {
        domain: "sensor",
        device_manufacturer: manufacturer,
        attributes: { led: 0 },
      },
      failingCheckDetailCard(
        "this.entity_id",
        "{{ state_attr('this.entity_id', 'check_id') }}",
        "{{ state_attr('this.entity_id', 'server_name') }} · ",
      ),
    );

    // Hosts whose Monit does not answer: their checks can't fail, so they
    // would otherwise just vanish from the failing list.
    const unreachable = hosts.map((h) => ({
      type: "conditional",
      conditions: [{ condition: "state", entity: h.status, state: DOWN_STATES }],
      card: {
        type: "custom:mushroom-template-card",
        entity: h.status,
        primary: h.name,
        secondary: "Monit unreachable: no data from this host",
        icon: "mdi:lan-disconnect",
        icon_color: "amber",
        tap_action: { action: "navigate", navigation_path: hostHash(h.name) },
        hold_action: { action: "more-info" },
      },
    }));

    const topSection = {
      type: "grid",
      cards: [heading("Monit", "mdi:monitor-eye"), summary, failing, ...unreachable],
    };

    // ── fleet grid ──
    const fleet = {
      type: "grid",
      columns: 2,
      square: false,
      cards: hosts.map((h) => {
        const s = `{%- set s = states('${h.status}') -%}{%- set down = s in ${JSON.stringify(DOWN_STATES)} -%}`;
        return {
          type: "custom:mushroom-template-card",
          entity: h.status,
          primary: h.name,
          secondary: s + `{{ 'Unreachable' if down else state_attr('${h.status}', 'host_summary') }}`,
          icon: hostIcon(h.name),
          // red=failed (led=0), amber=starting/initializing (led=1), grey=unreachable
          icon_color:
            s +
            `{{ 'disabled' if down else 'red' if s == 'on' else 'amber' if state_attr('${h.status}', 'led') == 1 else 'green' }}`,
          badge_icon:
            s +
            `{{ 'mdi:lan-disconnect' if down else 'mdi:alert' if s == 'on' else 'mdi:clock-start' if state_attr('${h.status}', 'led') == 1 else '' }}`,
          badge_color: s + "{{ 'grey' if down else 'red' if s == 'on' else 'amber' }}",
          tap_action: { action: "navigate", navigation_path: hostHash(h.name) },
          hold_action: { action: "more-info" },
        };
      }),
    };

    // ── trend graphs ──
    // Native statistics graphs (the metric sensors have state_class
    // measurement): long-term statistics load quickly for every host at once.
    function graph(label, metricKey) {
      const ents = hosts
        .filter((h) => h.metrics[metricKey])
        .map((h) => ({ entity: h.metrics[metricKey], name: h.name }));
      if (!ents.length) return null;
      return {
        type: "statistics-graph",
        title: label,
        entities: ents,
        days_to_show: 1,
        period: "5minute",
        chart_type: "line",
        stat_types: ["mean"],
      };
    }

    const trendCards = [
      heading("Trends", "mdi:chart-line"),
      graph("CPU usage", "cpu_usage"),
      graph("Memory usage", "memory_usage"),
      graph("Load average (15m)", "load_15m"),
      graph("Swap usage", "swap_usage"),
    ].filter(Boolean);

    // ── activity logbook ──
    const activity = {
      type: "logbook",
      target: { entity_id: statusIds },
      hours_to_show: 48,
    };

    // ── assemble sections ──
    const sections = [
      topSection,
      { type: "grid", cards: [heading("Fleet", "mdi:server-network"), fleet] },
      ...(trendCards.length > 1 ? [{ type: "grid", cards: trendCards }] : []),
      { type: "grid", cards: [heading("Activity", "mdi:history"), activity] },
      // Host popups (invisible unless triggered by hash navigation)
      { type: "grid", cards: hosts.map((h) => hostPopup(h, manufacturer)) },
      // Per-check popups — generated at runtime so new checks appear automatically
      {
        type: "grid",
        cards: hosts.flatMap((h) =>
          h.checks.map((c) => checkPopup(c.entity_id, c.name, h.name))
        ),
      },
    ];

    return { sections, max_columns: 2 };
  }
}

customElements.define("ll-strategy-view-monit", MonitViewStrategy);
