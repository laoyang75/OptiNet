#!/usr/bin/env bash
set -euo pipefail
"$(dirname "$0")/stop_frontend.sh"
"$(dirname "$0")/start_frontend.sh"
