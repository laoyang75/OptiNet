#!/usr/bin/env bash
set -euo pipefail
"$(dirname "$0")/stop_launcher.sh" || true
"$(dirname "$0")/start_launcher.sh"
