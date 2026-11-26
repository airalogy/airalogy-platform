#!/usr/bin/env bash
# Recover a writer explicitly paused by a backup interrupted before its EXIT trap.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
lock_maintenance "$@"
pause_marker="$(deployment_state_dir)/backup-paused-api"
[[ -s "$pause_marker" ]] || exit 0
container="$(compose ps -a -q api-server)"
if [[ -n "$container" && "$container" == "$(cat "$pause_marker")" ]]; then
  if [[ "$(docker inspect --format '{{.State.Running}}' "$container")" != true ]]; then
    compose start api-server >/dev/null
  fi
  wait_for_service api-server 300
fi
rm -f -- "$pause_marker"
