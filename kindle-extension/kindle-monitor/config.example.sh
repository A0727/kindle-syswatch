#!/bin/sh

# Leave SERVER_HOST empty when Kindle is connected to a Windows hotspot. The
# extension will use the Wi-Fi default gateway, i.e. the hotspot computer.
# Set an IPv4 address here only when the PC is reached through a normal router.
SERVER_HOST=""
SERVER_PORT=8765
AUTH_TOKEN="replace-with-the-same-random-token-as-config-toml"
REFRESH_SECONDS=10
# Full refresh after 180 successful 10-second updates: 30 minutes.
FULL_REFRESH_EVERY=180
HIDE_SYSTEM_CHROME=1
