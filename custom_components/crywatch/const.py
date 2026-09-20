"""Constants for the Crywatch integration."""

DOMAIN = "crywatch"

CONF_CAMERAS = "cameras"

# Supervisor-internal hostname for the companion add-on. For a repository
# (non-official) add-on, Supervisor prefixes the config.yaml slug with a hash
# of the repository URL, AND turns underscores into hyphens for the actual
# DNS hostname (the slug itself keeps underscores — they're not the same
# string). Confirmed against https://github.com/Shrolk/crywatch via
# `ha apps info aff0293d_crywatch_cry_detector` → `hostname:
# aff0293d-crywatch-cry-detector`. Editable in the config flow; a different
# repo URL/fork will have a different hash — find yours the same way
# (`ha apps list` for the slug, then `ha apps info <slug>` for `hostname:`).
DEFAULT_HOST = "aff0293d-crywatch-cry-detector"
DEFAULT_PORT = 8091

SCAN_INTERVAL_SECONDS = 5
