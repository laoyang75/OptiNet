#!/bin/bash
# =============================================================================
# migrate_y_codex_to_pg17.sh
# 将 PG15 (port 5432) 中所有 Y_codex_* / WY_codex_* 表迁移到 PG17 (port 5433)
# 
# 两个数据库均在同一台服务器上，直接管道传输，无额外网络开销。
# 在服务器（192.168.200.217）上执行本脚本。
#
# 用法：bash migrate_y_codex_to_pg17.sh
# 日志：migrate_y_codex_to_pg17.log（自动生成在同目录）
# =============================================================================

set -euo pipefail

# ---- 连接参数 ----
SRC_HOST="127.0.0.1"
SRC_PORT="5432"
SRC_DB="ip_loc2"
SRC_USER="postgres"
PGPASSWORD="123456"
export PGPASSWORD

DST_HOST="127.0.0.1"
DST_PORT="5433"
DST_DB="ip_loc2"
DST_USER="postgres"

LOG_FILE="$(dirname "$0")/migrate_y_codex_to_pg17.log"

# ---- 待迁移表（按大小从小到大，方便先验证小表）----
TABLES=(
    # obs 观测表（空表/极小）
    "Y_codex_Layer4_Step40_Gps_Metrics"
    "Y_codex_Layer4_Step40_Gps_Metrics_All"
    "Y_codex_Layer4_Step40_Gps_Metrics__MCP_SMOKE"
    "Y_codex_Layer4_Step41_Signal_Metrics"
    "Y_codex_Layer4_Step41_Signal_Metrics_All"
    "Y_codex_Layer4_Step41_Signal_Metrics__MCP_SMOKE"
    "Y_codex_obs_patch_log"
    "Y_codex_obs_rule_hit"
    "Y_codex_obs_exposure_matrix"
    "Y_codex_obs_layer_snapshot"
    "Y_codex_obs_quality_metric"
    "Y_codex_obs_gate_result"
    "Y_codex_obs_run_registry"
    "Y_codex_obs_anomaly_stats"
    "Y_codex_obs_reconciliation"
    "Y_codex_obs_issue_log"
    "Y_codex_Layer4_Step42_Compare_Summary"
    "Y_codex_Layer4_Step42_Compare_Summary__MCP_SMOKE"
    "Y_codex_Layer4_Step44_BsId_Lt_256_Summary"
    # 小统计表（< 1 MB）
    "Y_codex_Layer2_Step01_BaseStats_ValidCell"
    "Y_codex_Layer3_Step30_Gps_Level_Stats"
    "Y_codex_Layer3_Step36_BS_Id_Anomaly_Marked"
    "Y_codex_Layer3_Step32_Compare_Raw"
    "Y_codex_Layer3_Step34_Signal_Compare_Raw"
    "Y_codex_Layer2_Step02_Compliance_Diff"
    "Y_codex_Layer3_Step32_Compare"
    "Y_codex_Layer2_Step01_BaseStats_Raw"
    "Y_codex_Layer3_Step34_Signal_Compare"
    "Y_codex_Layer3_Step35_28D_Dynamic_Cell_Profile"
    "Y_codex_Layer2_Step04_Master_Lac_Lib"
    "Y_codex_Layer2_Step06_GpsVsLac_Compare"
    "Y_codex_Layer2_Step02_Gps_Compliance_Marked__L3_SMOKE"
    "Y_codex_Layer2_Step06_L0_Lac_Filtered__L3_SMOKE"
    "Y_codex_Layer5_Lac_Profile"
    "WY_codex_Layer2_Step04_Master_Lac_Lib_mid_20260309"
    "Y_codex_Layer3_Step37_Collision_Data_Insufficient_BS"
    "Y_codex_Layer4_Step44_BsId_Lt_256_Detail"
    "Y_codex_Layer5_Smoke_Cell_Profile"
    "Y_codex_Layer5_Smoke_BS_Profile"
    # 中等表（1 MB ~ 100 MB）
    "Y_codex_Layer2_Step03_Lac_Stats_DB"
    "Y_codex_Layer3_Step30_Master_BS_Library"
    "Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill__MCP_SMOKE"
    "Y_codex_Layer3_BS_Profile"
    "Y_codex_Layer3_Final_BS_Profile"
    "Y_codex_Layer4_Final_Cell_Library__MCP_SMOKE"
    "Y_codex_Layer2_Step05_CellId_Stats_DB"
    "Y_codex_Layer3_Cell_BS_Map"
    "Y_codex_Layer3_Final_Cell_BS_Map"
    "Y_codex_Layer5_BS_Profile"
    "Y_codex_Layer5_Cell_Profile"
    # 大表（> 1 GB）
    "Y_codex_Layer3_Step33_Signal_Fill_Simple"
    "Y_codex_Layer3_Step31_Cell_Gps_Fixed"
    "Y_codex_Layer2_Step06_L0_Lac_Filtered"
    "Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill"
    "Y_codex_Layer4_Final_Cell_Library"
    "Y_codex_Layer0_Lac"
    "Y_codex_Layer0_Gps_base"
)

# ---- 工具函数 ----
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE"
}

count_rows() {
    local port=$1 table=$2
    psql -h "$SRC_HOST" -p "$port" -U "$SRC_USER" -d "$SRC_DB" -t -A \
        -c "SELECT COUNT(*) FROM public.\"${table}\";" 2>/dev/null || echo "ERR"
}

# ---- 主流程 ----
log "===== 开始迁移：PG15(${SRC_PORT}) → PG17(${DST_PORT}) ====="
log "待迁移表数量：${#TABLES[@]}"

TOTAL=${#TABLES[@]}
SUCCESS=0
FAIL=0
SKIP=0

for i in "${!TABLES[@]}"; do
    TABLE="${TABLES[$i]}"
    IDX=$((i + 1))

    log "[$IDX/$TOTAL] 开始处理表：${TABLE}"

    # 检查目标库是否已存在该表
    EXISTS=$(psql -h "$DST_HOST" -p "$DST_PORT" -U "$DST_USER" -d "$DST_DB" -t -A \
        -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='${TABLE}';" 2>/dev/null || echo "0")

    if [[ "$EXISTS" == "1" ]]; then
        DST_CNT=$(psql -h "$DST_HOST" -p "$DST_PORT" -U "$DST_USER" -d "$DST_DB" -t -A \
            -c "SELECT COUNT(*) FROM public.\"${TABLE}\";" 2>/dev/null || echo "0")
        if [[ "$DST_CNT" -gt "0" ]]; then
            log "  ⚠️  目标表已存在且有数据（$DST_CNT 行），跳过。如需重迁请先 DROP。"
            SKIP=$((SKIP + 1))
            continue
        fi
    fi

    # pg_dump 从 PG15 导出 → 直接 psql 导入 PG17
    if pg_dump \
        -h "$SRC_HOST" -p "$SRC_PORT" -U "$SRC_USER" -d "$SRC_DB" \
        --no-acl --no-owner \
        -t "public.\"${TABLE}\"" \
        | psql -h "$DST_HOST" -p "$DST_PORT" -U "$DST_USER" -d "$DST_DB" \
               -v ON_ERROR_STOP=1 \
               --quiet 2>>"$LOG_FILE"; then

        # 验证行数
        SRC_CNT=$(count_rows "$SRC_PORT" "$TABLE")
        DST_CNT=$(count_rows "$DST_PORT" "$TABLE")

        if [[ "$SRC_CNT" == "$DST_CNT" ]]; then
            log "  ✅ 成功：${TABLE}（${SRC_CNT} 行）"
            SUCCESS=$((SUCCESS + 1))
        else
            log "  ⚠️  行数不一致：源 ${SRC_CNT} 行 vs 目标 ${DST_CNT} 行，请核查！"
            FAIL=$((FAIL + 1))
        fi
    else
        log "  ❌ 失败：${TABLE}，请检查日志 ${LOG_FILE}"
        FAIL=$((FAIL + 1))
    fi
done

log "===== 迁移完成 ====="
log "成功：${SUCCESS} | 跳过（已有数据）：${SKIP} | 失败：${FAIL}"
log "日志已保存至：${LOG_FILE}"
