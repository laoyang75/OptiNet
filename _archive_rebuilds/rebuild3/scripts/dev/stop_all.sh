#!/usr/bin/env bash
set -euo pipefail
"$(dirname "$0")/stop_frontend.sh" || true
"$(dirname "$0")/stop_backend.sh" || true
"$(dirname "$0")/status.sh"
