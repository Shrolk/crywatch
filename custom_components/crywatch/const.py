"""Constants for the Crywatch integration."""

DOMAIN = "crywatch"

# Guessed Supervisor-internal hostname for the companion add-on
# (ha-addon/crywatch_cry_detector, slug "crywatch_cry_detector"). Editable in
# the config flow — NOT verified against a real Supervisor install (this was
# written without access to one); if it doesn't resolve, check the add-on's
# actual hostname (its container name on the `hassio` docker network) and
# enter that instead.
DEFAULT_HOST = "crywatch_cry_detector"
DEFAULT_PORT = 8091

SCAN_INTERVAL_SECONDS = 5
