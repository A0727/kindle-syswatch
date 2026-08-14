#!/bin/sh

APP_DIR="/mnt/us/extensions/kindle-monitor"
RUNTIME_DIR="$APP_DIR/runtime"
PID_FILE="$RUNTIME_DIR/monitor.pid"
STOP_FILE="$RUNTIME_DIR/stop"
IMAGE_FILE="$RUNTIME_DIR/dashboard.png"
TEMP_FILE="$RUNTIME_DIR/dashboard.tmp"
LOG_FILE="$RUNTIME_DIR/monitor.log"
FBINK="/mnt/us/libkh/bin/fbink"

if [ -f "$APP_DIR/config.sh" ]; then
    . "$APP_DIR/config.sh"
fi

mkdir -p "$RUNTIME_DIR"

show_message() {
    eips ''
    eips 2 4 "$1"
}
hide_system_chrome() {
    [ "${HIDE_SYSTEM_CHROME:-1}" = "1" ] || return 0
    lipc-set-prop com.lab126.pillow disableEnablePillow disable >/dev/null 2>&1
}

restore_system_chrome() {
    [ "${HIDE_SYSTEM_CHROME:-1}" = "1" ] || return 0
    lipc-set-prop com.lab126.pillow disableEnablePillow enable >/dev/null 2>&1
}

detect_server_host() {
    if [ -n "${SERVER_HOST:-}" ]; then
        printf '%s\n' "$SERVER_HOST"
        return 0
    fi

    if command -v ip >/dev/null 2>&1; then
        detected_host="$(ip route 2>/dev/null | awk '$1 == "default" && $2 == "via" { print $3; exit }')"
        if [ -n "$detected_host" ]; then
            printf '%s\n' "$detected_host"
            return 0
        fi
    fi

    if command -v route >/dev/null 2>&1; then
        detected_host="$(route -n 2>/dev/null | awk '$1 == "0.0.0.0" { print $2; exit }')"
        if [ -n "$detected_host" ]; then
            printf '%s\n' "$detected_host"
            return 0
        fi
    fi

    return 1
}

download_dashboard() {
    server_host="$(detect_server_host)" || {
        echo "No server host and no Wi-Fi default gateway" >>"$LOG_FILE"
        return 1
    }
    server_url="http://${server_host}:${SERVER_PORT:-8765}/dashboard.png?token=${AUTH_TOKEN}"
    cache_buster="$(date +%s)"
    request_url="${server_url}&t=${cache_buster}"

    rm -f "$TEMP_FILE"
    if command -v wget >/dev/null 2>&1; then
        wget -q -T 8 -O "$TEMP_FILE" "$request_url" >>"$LOG_FILE" 2>&1
    elif command -v curl >/dev/null 2>&1; then
        curl -fsS --max-time 8 -o "$TEMP_FILE" "$request_url" >>"$LOG_FILE" 2>&1
    else
        return 1
    fi

    [ -s "$TEMP_FILE" ] || return 1
    image_size="$(wc -c < "$TEMP_FILE" 2>/dev/null)"
    [ "${image_size:-0}" -gt 1024 ] || return 1
    mv -f "$TEMP_FILE" "$IMAGE_FILE"
}

display_dashboard() {
    flash_arg=""
    [ "${1:-0}" = "1" ] && flash_arg="-f"
    hide_system_chrome
    "$FBINK" -q -c $flash_arg -i "$IMAGE_FILE" >>"$LOG_FILE" 2>&1
}
