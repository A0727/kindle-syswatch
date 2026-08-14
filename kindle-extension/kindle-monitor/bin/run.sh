#!/bin/sh

. /mnt/us/extensions/kindle-monitor/bin/common.sh

cleanup() {
    lipc-set-prop com.lab126.powerd preventScreenSaver 0 >/dev/null 2>&1
    restore_system_chrome
    rm -f "$PID_FILE" "$STOP_FILE" "$TEMP_FILE"
}

trap cleanup EXIT INT TERM
echo "$$" > "$PID_FILE"
rm -f "$STOP_FILE"
lipc-set-prop com.lab126.powerd preventScreenSaver 1 >/dev/null 2>&1
hide_system_chrome

# KUAL returns to the Amazon UI asynchronously. Let that transition finish so
# the first dashboard paint is the final owner of the framebuffer.
sleep 3

successful_refreshes=0
while [ ! -f "$STOP_FILE" ]; do
    if download_dashboard; then
        successful_refreshes=$((successful_refreshes + 1))
        full_refresh=0
        if [ "$successful_refreshes" -eq 1 ] || [ $((successful_refreshes % FULL_REFRESH_EVERY)) -eq 0 ]; then
            full_refresh=1
        fi
        display_dashboard "$full_refresh"
    else
        show_message "SYSWATCH: PC OFFLINE // retrying"
    fi
    sleep "$REFRESH_SECONDS"
done
