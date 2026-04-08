#!/usr/bin/env bash
set -euo pipefail
"$(dirname "$0")/stop_backend.sh" || true
"$(dirname "$0")/start_backend.sh"
