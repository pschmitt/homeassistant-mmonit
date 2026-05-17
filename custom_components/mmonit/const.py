"""Constants for the M/Monit integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "mmonit"
PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]
CONF_VERIFY_SSL = "verify_ssl"

DEFAULT_SCAN_INTERVAL = 120
MIN_SCAN_INTERVAL = 30
DEFAULT_REQUEST_TIMEOUT = 20
DEFAULT_VERIFY_SSL = True

ATTR_CHECK_ID = "check_id"
ATTR_CHECK_TYPE = "check_type"
ATTR_EVENTS = "events"
ATTR_EVERY = "every"
ATTR_LED = "led"
ATTR_MONITOR_MODE = "monitor_mode"
ATTR_MONITOR_STATE = "monitor_state"
ATTR_FAILED_CHECKS = "failed_checks"
ATTR_HOST_COLOR = "host_color"
ATTR_HOST_SUMMARY = "host_summary"
ATTR_SERVER_NAME = "server_name"
ATTR_SERVER_URL = "server_url"
ATTR_STATUS_MESSAGE = "status_message"

API_ACCEPT = "application/json"
LOGIN_PATH = "z_security_check"
HOSTS_LIST_PATH = "api/2/status/hosts/list"
HOSTS_GET_PATH = "api/2/status/hosts/get"
