#!/usr/bin/env bash
# Reports a running container's peak memory and fails if the kernel killed a process for lack of memory.
# Usage: deploy/memory.sh <container>
set -euo pipefail
c="$1"
peak=$(docker exec "$c" sh -c 'cat /sys/fs/cgroup/memory.peak 2>/dev/null || cat /sys/fs/cgroup/memory/memory.max_usage_in_bytes')
ooms=$(docker exec "$c" sh -c 'grep -s "^oom_kill " /sys/fs/cgroup/memory.events || grep -s "^oom_kill " /sys/fs/cgroup/memory/memory.oom_control || echo "oom_kill 0"')
echo "$c: peak memory $((peak / 1048576)) MiB, ${ooms}"
[ "${ooms##* }" = "0" ] || { echo "FAIL: a process in $c ran out of memory"; exit 1; }
