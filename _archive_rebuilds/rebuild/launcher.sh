#!/usr/bin/env bash
# ============================================================
# WangYou Data Governance Workbench — Interactive Launcher
# ============================================================

set -uo pipefail

# ── Config ───────────────────────────────────────────────────
APP_NAME="WangYou Workbench"
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$BASE_DIR/backend"
VENV_DIR="$BACKEND_DIR/.venv"
PID_FILE="$BACKEND_DIR/.uvicorn.pid"
LOG_FILE="$BACKEND_DIR/logs/uvicorn.log"
HOST="0.0.0.0"
PORT=8000
WORKERS=1

# ── Colors ───────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ── Helpers ──────────────────────────────────────────────────
log_info()  { echo -e "  ${BLUE}[INFO]${NC}  $1"; }
log_ok()    { echo -e "  ${GREEN}[ OK ]${NC}  $1"; }
log_warn()  { echo -e "  ${YELLOW}[WARN]${NC}  $1"; }
log_err()   { echo -e "  ${RED}[ERR ]${NC}  $1"; }

get_pid() {
    if [[ -f "$PID_FILE" ]]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
        rm -f "$PID_FILE"
    fi
    local pid
    pid=$(lsof -ti :"$PORT" 2>/dev/null | head -1) || true
    if [[ -n "$pid" ]]; then
        echo "$pid"
        return 0
    fi
    return 1
}

is_running() {
    get_pid >/dev/null 2>&1
}

ensure_venv() {
    if [[ ! -d "$VENV_DIR" ]]; then
        log_info "Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
        source "$VENV_DIR/bin/activate"
        pip install -q -r "$BACKEND_DIR/requirements.txt"
        log_ok "Virtual environment created"
    fi
}

status_badge() {
    if is_running; then
        local pid
        pid=$(get_pid)
        local uptime
        uptime=$(ps -o etime= -p "$pid" 2>/dev/null | xargs) || uptime="?"
        echo -e "${GREEN}${BOLD}RUNNING${NC} ${DIM}PID:$pid  Up:$uptime${NC}"
    else
        echo -e "${RED}${BOLD}STOPPED${NC}"
    fi
}

# ── Commands ─────────────────────────────────────────────────

cmd_start() {
    if is_running; then
        local pid
        pid=$(get_pid)
        log_warn "Already running (PID: $pid)"
        return 1
    fi

    ensure_venv
    mkdir -p "$(dirname "$LOG_FILE")"

    log_info "Starting on $HOST:$PORT ..."
    cd "$BACKEND_DIR"
    source "$VENV_DIR/bin/activate"

    nohup python -m uvicorn app.main:app \
        --host "$HOST" \
        --port "$PORT" \
        --workers "$WORKERS" \
        --log-level info \
        >> "$LOG_FILE" 2>&1 &

    local pid=$!
    echo "$pid" > "$PID_FILE"

    local retries=0
    while [[ $retries -lt 15 ]]; do
        sleep 1
        if curl -sf "http://127.0.0.1:$PORT/api/v1/health" >/dev/null 2>&1; then
            log_ok "Started (PID: $pid)"
            echo ""
            log_info "Frontend:  ${BOLD}http://localhost:$PORT/${NC}"
            log_info "API Docs:  ${BOLD}http://localhost:$PORT/docs${NC}"
            return 0
        fi
        retries=$((retries + 1))
    done

    log_err "Failed to start. Recent logs:"
    tail -15 "$LOG_FILE" 2>/dev/null
    return 1
}

cmd_stop() {
    if ! is_running; then
        log_warn "Not running"
        rm -f "$PID_FILE"
        return 0
    fi

    local pid
    pid=$(get_pid)
    log_info "Stopping (PID: $pid) ..."

    kill "$pid" 2>/dev/null || true
    local retries=0
    while kill -0 "$pid" 2>/dev/null && [[ $retries -lt 10 ]]; do
        sleep 1
        retries=$((retries + 1))
    done

    if kill -0 "$pid" 2>/dev/null; then
        log_warn "Force killing..."
        kill -9 "$pid" 2>/dev/null || true
    fi

    rm -f "$PID_FILE"
    log_ok "Stopped"
}

cmd_restart() {
    log_info "Restarting ..."
    cmd_stop
    sleep 1
    cmd_start
}

cmd_killport() {
    local pids
    pids=$(lsof -ti :"$PORT" 2>/dev/null) || true
    if [[ -z "$pids" ]]; then
        log_ok "Port $PORT is already free"
        return 0
    fi

    echo ""
    log_info "Processes on port $PORT:"
    lsof -i :"$PORT" 2>/dev/null | head -10
    echo ""

    for pid in $pids; do
        log_info "Killing PID $pid ..."
        kill -9 "$pid" 2>/dev/null || true
    done
    rm -f "$PID_FILE"
    sleep 1
    log_ok "Port $PORT cleared"
}

cmd_status_detail() {
    echo ""
    if is_running; then
        local pid
        pid=$(get_pid)
        local uptime
        uptime=$(ps -o etime= -p "$pid" 2>/dev/null | xargs) || uptime="unknown"

        echo -e "  Status:    ${GREEN}${BOLD}RUNNING${NC}"
        echo -e "  PID:       $pid"
        echo -e "  Port:      $PORT"
        echo -e "  Uptime:    $uptime"

        local health
        if health=$(curl -sf "http://127.0.0.1:$PORT/api/v1/health" 2>/dev/null); then
            echo -e "  Health:    ${GREEN}OK${NC}"
        else
            echo -e "  Health:    ${YELLOW}UNREACHABLE${NC}"
        fi
    else
        echo -e "  Status:    ${RED}${BOLD}STOPPED${NC}"
    fi

    echo -e "  Frontend:  http://localhost:$PORT/"
    echo -e "  API Docs:  http://localhost:$PORT/docs"
    echo ""

    if [[ -f "$LOG_FILE" ]]; then
        local log_size
        log_size=$(wc -c < "$LOG_FILE" | xargs)
        echo -e "  Log File:  $LOG_FILE ($log_size bytes)"
        echo ""
        echo -e "  ${CYAN}── Recent Logs (last 15 lines) ──${NC}"
        echo ""
        tail -15 "$LOG_FILE" 2>/dev/null | sed 's/^/  /'
    else
        echo -e "  ${DIM}No log file yet${NC}"
    fi
    echo ""
}

cmd_logs() {
    if [[ ! -f "$LOG_FILE" ]]; then
        log_warn "No log file yet"
        return 0
    fi
    echo ""
    echo -e "  ${CYAN}── Logs (last 50 lines) ──${NC}"
    echo ""
    tail -50 "$LOG_FILE" | sed 's/^/  /'
    echo ""
}

# ── Interactive Menu ─────────────────────────────────────────

show_menu() {
    clear
    echo ""
    echo -e "  ${BOLD}╔═══════════════════════════════════════════════╗${NC}"
    echo -e "  ${BOLD}║       WangYou Data Governance Workbench       ║${NC}"
    echo -e "  ${BOLD}╚═══════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  Status: $(status_badge)"
    echo ""
    echo -e "  ${BOLD}────────── Commands ──────────${NC}"
    echo ""
    echo -e "  ${GREEN}1${NC}  Start          启动服务"
    echo -e "  ${RED}2${NC}  Stop           停止服务"
    echo -e "  ${YELLOW}3${NC}  Restart        重启服务"
    echo -e "  ${BLUE}4${NC}  Kill Port      清除端口 $PORT"
    echo -e "  ${CYAN}5${NC}  Status         详细状态 + 日志"
    echo -e "  ${CYAN}6${NC}  Logs           查看最近日志"
    echo ""
    echo -e "  ${DIM}0  Exit           退出启动器${NC}"
    echo ""
    echo -e "  ${BOLD}──────────────────────────────${NC}"
    echo ""
}

interactive_loop() {
    while true; do
        show_menu
        echo -ne "  Select [0-6]: "
        read -r choice

        echo ""
        case "$choice" in
            1)
                cmd_start
                ;;
            2)
                cmd_stop
                ;;
            3)
                cmd_restart
                ;;
            4)
                cmd_killport
                ;;
            5)
                cmd_status_detail
                ;;
            6)
                cmd_logs
                ;;
            0|q|Q|exit)
                echo -e "  ${DIM}Bye.${NC}"
                echo ""
                exit 0
                ;;
            *)
                log_warn "Invalid option: $choice"
                ;;
        esac

        echo ""
        echo -ne "  ${DIM}Press Enter to continue...${NC}"
        read -r
    done
}

# ── Main ─────────────────────────────────────────────────────

# Support both modes: interactive (no args) and CLI (with args)
case "${1:-}" in
    start)    cmd_start ;;
    stop)     cmd_stop ;;
    restart)  cmd_restart ;;
    status)   cmd_status_detail ;;
    killport) cmd_killport ;;
    logs)     cmd_logs ;;
    "")       interactive_loop ;;
    *)
        echo ""
        echo -e "  ${BOLD}Usage:${NC} $0 [command]"
        echo ""
        echo "  No args    Interactive menu"
        echo "  start      Start the service"
        echo "  stop       Stop the service"
        echo "  restart    Restart the service"
        echo "  status     Show detailed status"
        echo "  killport   Force kill port $PORT"
        echo "  logs       Show recent logs"
        echo ""
        ;;
esac
