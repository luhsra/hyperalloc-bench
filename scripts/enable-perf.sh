#!/bin/bash
mount -o remount,mode=755 /sys/kernel/tracing/
chown -R root:srastaff /sys/kernel/tracing
chmod -R g+rwx /sys/kernel/tracing/events
