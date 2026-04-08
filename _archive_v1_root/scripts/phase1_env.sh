#!/usr/bin/env bash
# Phase1 default runtime environment
# Usage:
#   source scripts/phase1_env.sh
#   PHASE1_ENV_QUIET=1 source scripts/phase1_env.sh

set -euo pipefail

# Current project DB (can be overridden by external env).
: "${PHASE1_DB_DSN:=postgresql://postgres:123456@192.168.200.217:5432/ip_loc2?sslmode=disable}"
: "${PHASE1_API_HOST:=127.0.0.1}"
: "${PHASE1_API_PORT:=8508}"
: "${PHASE1_PAGE_SIZE:=100}"
: "${PHASE1_MAX_PAGE_SIZE:=500}"

export PHASE1_DB_DSN
export PHASE1_API_HOST
export PHASE1_API_PORT
export PHASE1_PAGE_SIZE
export PHASE1_MAX_PAGE_SIZE

if [[ "${PHASE1_ENV_QUIET:-0}" != "1" ]]; then
  echo "[phase1_env] DB=ip_loc2 HOST=192.168.200.217:5432 USER=postgres"
  echo "[phase1_env] API=${PHASE1_API_HOST}:${PHASE1_API_PORT}"
fi

