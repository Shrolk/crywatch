"""Constants for the Crywatch integration."""

DOMAIN = "crywatch"

CONF_CAMERAS = "cameras"

# Supervisor-internal hostname for the companion add-on. For a repository
# (non-official) add-on, Supervisor prefixes the config.yaml slug with a hash
# of the repository URL — confirmed via `ha apps list` against
# https://github.com/Shrolk/crywatch (repository: aff0293d). Editable in the
# config flow; if you added this repo under a different URL/fork, that hash
# will differ — find yours the same way (`ha apps list`, look for the
# "slug:" field) rather than trusting this default.
DEFAULT_HOST = "aff0293d_crywatch_cry_detector"
DEFAULT_PORT = 8091

SCAN_INTERVAL_SECONDS = 5
