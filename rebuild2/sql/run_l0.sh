#!/bin/bash
cd /Users/yangcongan/cursor/WangYou_Data/rebuild2/sql/

echo "[$(date)] Starting GPS runbook..."
PGPASSWORD=123456 psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2 -f exec_l0_gps.sql > gps_run.log 2>&1
echo "[$(date)] GPS runbook complete. Output logged to gps_run.log"

echo "[$(date)] Starting LAC runbook..."
PGPASSWORD=123456 psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2 -f exec_l0_lac.sql > lac_run.log 2>&1
echo "[$(date)] LAC runbook complete. Output logged to lac_run.log"

echo "[$(date)] Starting Stats runbook..."
PGPASSWORD=123456 psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2 -f exec_l0_stats.sql > stats_run.log 2>&1
echo "[$(date)] Stats runbook complete. Output logged to stats_run.log"

echo "[$(date)] All tasks completed!"
