#!/usr/bin/env bash
set -euo pipefail
DIR="$(dirname "$0")"
"$DIR/stop_frontend.sh"
sleep 1
"$DIR/start_frontend.sh"
