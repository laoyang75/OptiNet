#!/usr/bin/env bash
set -euo pipefail
"$(dirname "$0")/start_backend.sh"
"$(dirname "$0")/start_frontend.sh"
"$(dirname "$0")/status.sh"
