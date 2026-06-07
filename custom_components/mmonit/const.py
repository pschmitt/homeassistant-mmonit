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

HOST_SENSOR_CPU_COUNT = "host_cpu_count"
HOST_SENSOR_CPU_USAGE = "host_cpu_usage"
HOST_SENSOR_MEMORY_TOTAL = "host_memory_total"
HOST_SENSOR_MEMORY_USAGE = "host_memory_usage"
HOST_SENSOR_PLATFORM = "host_platform"
HOST_SENSOR_SWAP_TOTAL = "host_swap_total"
HOST_SENSOR_UPTIME = "host_uptime"
HOST_SENSOR_KEYS: tuple[str, ...] = (
    HOST_SENSOR_CPU_USAGE,
    HOST_SENSOR_MEMORY_USAGE,
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
