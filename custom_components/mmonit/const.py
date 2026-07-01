"""Constants for the M/Monit integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "mmonit"
PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]
CONF_VERIFY_SSL = "verify_ssl"
CONF_MODE = "mode"

MODE_MMONIT = "mmonit"
MODE_MONIT = "monit"

DEFAULT_SCAN_INTERVAL = 120
MIN_SCAN_INTERVAL = 30
DEFAULT_REQUEST_TIMEOUT = 20
DEFAULT_VERIFY_SSL = True

ATTR_CHECK_ID = "check_id"
ATTR_CHECK_TYPE = "check_type"
ATTR_DATA_COLLECTED = "data_collected"
ATTR_EVENTS_URL = "events_url"
ATTR_EVENTS = "events"
ATTR_EVERY = "every"
ATTR_LAST_EXIT_VALUE = "last_exit_value"
ATTR_LAST_EVENTS = "last_events"
ATTR_LAST_OUTPUT = "last_output"
ATTR_LED = "led"
ATTR_MONITOR_MODE = "monitor_mode"
ATTR_MONITOR_STATE = "monitor_state"
ATTR_HOST_URL = "host_url"
ATTR_PORT_RESPONSE_TIME = "port_response_time"
ATTR_FAILED_CHECKS = "failed_checks"
ATTR_HOST_COLOR = "host_color"
ATTR_HOST_SUMMARY = "host_summary"
ATTR_SERVER_NAME = "server_name"
ATTR_SERVER_URL = "server_url"
ATTR_STATUS_MESSAGE = "status_message"
ATTR_ACTION_RESTART = "action_restart"
ATTR_ACTION_START = "action_start"
ATTR_ACTION_STOP = "action_stop"
ATTR_CHECK_GROUP = "check_group"
ATTR_CHECK_PATH = "check_path"
ATTR_ON_REBOOT = "on_reboot"
ATTR_PENDING_ACTION = "pending_action"
ATTR_PID = "pid"
ATTR_PPID = "ppid"
ATTR_PROCESS_UPTIME = "process_uptime"
ATTR_SYSTEM_LOAD_1 = "system_load_1m"
ATTR_SYSTEM_LOAD_5 = "system_load_5m"
ATTR_SYSTEM_LOAD_15 = "system_load_15m"
ATTR_SYSTEM_LOAD_PER_CORE = "system_load_per_core"
ATTR_SYSTEM_CPU_PERCENT = "system_cpu_percent"
ATTR_SYSTEM_MEMORY_PERCENT = "system_memory_percent"
ATTR_SYSTEM_SWAP_PERCENT = "system_swap_percent"
ATTR_RESOURCE_SUMMARY = "resource_summary"

HOST_SENSOR_CPU_COUNT = "host_cpu_count"
HOST_SENSOR_CPU_USAGE = "host_cpu_usage"
HOST_SENSOR_LOAD_1 = "host_load_1m"
HOST_SENSOR_LOAD_5 = "host_load_5m"
HOST_SENSOR_LOAD_15 = "host_load_15m"
HOST_SENSOR_MEMORY_TOTAL = "host_memory_total"
HOST_SENSOR_MEMORY_USAGE = "host_memory_usage"
HOST_SENSOR_PLATFORM = "host_platform"
HOST_SENSOR_SWAP_TOTAL = "host_swap_total"
HOST_SENSOR_SWAP_USAGE = "host_swap_usage"
HOST_SENSOR_UPTIME = "host_uptime"
HOST_SENSOR_KEYS: tuple[str, ...] = (
    HOST_SENSOR_CPU_USAGE,
    HOST_SENSOR_LOAD_1,
    HOST_SENSOR_LOAD_5,
    HOST_SENSOR_LOAD_15,
    HOST_SENSOR_MEMORY_USAGE,
    HOST_SENSOR_SWAP_USAGE,
    HOST_SENSOR_UPTIME,
    HOST_SENSOR_CPU_COUNT,
    HOST_SENSOR_MEMORY_TOTAL,
    HOST_SENSOR_SWAP_TOTAL,
    HOST_SENSOR_PLATFORM,
)

API_ACCEPT = "application/json"
LOGIN_PATH = "z_security_check"
HOSTS_LIST_PATH = "api/2/status/hosts/list"
HOSTS_GET_PATH = "api/2/status/hosts/get"

MONIT_STATUS_PATH = "_status"
