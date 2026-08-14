#!/bin/sh

. /mnt/us/extensions/kindle-monitor/bin/common.sh

touch "$STOP_FILE"
if [ -f "$PID_FILE" ]; then
    monitor_pid="$(cat "$PID_FILE" 2>/dev/null)"
    if [ -n "$monitor_pid" ]; then
        kill "$monitor_pid" 2>/dev/null
    fi
fi
lipc-set-prop com.lab126.powerd preventScreenSaver 0 >/dev/null 2>&1
restore_system_chrome
rm -f "$PID_FILE" "$TEMP_FILE"
show_message "SYSWATCH: stopped"
sleep 1
lipc-set-prop com.lab126.appmgrd start app://com.lab126.booklet.home >/dev/null 2>&1
