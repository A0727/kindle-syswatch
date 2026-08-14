#!/bin/sh

. /mnt/us/extensions/kindle-monitor/bin/common.sh

if [ -f "$PID_FILE" ]; then
    old_pid="$(cat "$PID_FILE" 2>/dev/null)"
    if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
        show_message "SYSWATCH: already running"
        exit 0
    fi
fi

rm -f "$STOP_FILE"
show_message "SYSWATCH: starting"
nohup sh "$APP_DIR/bin/run.sh" >>"$LOG_FILE" 2>&1 </dev/null &
