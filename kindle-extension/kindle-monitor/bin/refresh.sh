#!/bin/sh

. /mnt/us/extensions/kindle-monitor/bin/common.sh

if download_dashboard; then
    display_dashboard 1
else
    show_message "SYSWATCH: PC OFFLINE"
fi
