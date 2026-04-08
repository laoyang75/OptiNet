"""Shared labels and lightweight dictionaries for workbench APIs."""

from __future__ import annotations

TABLE_LABELS = {
    "raw_records": "原始记录表",
    "stats_base_raw": "基础统计表",
    "fact_filtered": "合规过滤明细",
    "stats_lac": "LAC统计表",
    "dim_lac_trusted": "可信LAC维表",
    "dim_cell_stats": "Cell统计维表",
    "dim_bs_trusted": "可信BS维表",
    "fact_gps_corrected": "GPS修正明细",
    "compare_gps": "GPS对比结果",
    "fact_signal_filled": "信号补齐明细",
    "compare_signal": "信号对比结果",
    "detect_anomaly_bs": "BS异常标记结果",
    "detect_collision": "碰撞样本不足结果",
    "map_cell_bs": "Cell-BS映射表",
    "fact_final": "最终回归明细",
    "profile_lac": "LAC画像",
    "profile_bs": "BS画像",
    "profile_cell": "Cell画像",
}

LAYER_LABELS = {
    "L0_raw": "L0 原始记录",
    "L2_filtered": "L2 合规过滤",
    "L2_lac_trusted": "L2 可信LAC",
    "L2_cell_stats": "L2 Cell统计",
    "L3_bs_trusted": "L3 可信BS",
    "L3_gps_corrected": "L3 GPS修正",
    "L3_signal_filled": "L3 信号补齐",
    "L3_cell_bs_map": "L3 Cell-BS映射",
    "L4_final": "L4 完整回归",
    "L5_lac_profile": "L5 LAC画像",
    "L5_bs_profile": "L5 BS画像",
    "L5_cell_profile": "L5 Cell画像",
}

ANOMALY_LABELS = {
    "collision_suspect": "碰撞疑似",
    "severe_collision": "严重碰撞",
    "gps_unstable": "GPS不稳定",
    "bs_id_lt_256": "BS_ID异常(<256)",
    "multi_operator_shared": "多运营商共建",
    "insufficient_sample": "样本不足",
    "dynamic_cell": "动态Cell",
    "gps_drift": "GPS漂移",
}

OBJECT_LEVEL_LABELS = {
    "BS": "基站",
    "CELL": "Cell",
    "Cell": "Cell",
    "LAC": "LAC",
}

RUN_MODE_LABELS = {
    "full_rerun": "全链路重跑",
    "partial_rerun": "局部重跑",
    "sample_rerun": "样本重跑",
    "pseudo_daily": "伪日更运行",
}

STATUS_LABELS = {
    "running": "运行中",
    "completed": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
}

STEP_PURPOSES = {
    "s0": "统一 Layer0 两路原始数据字段与运营商标识，为后续治理提供单一数据起点。",
    "s1": "产出原始数据的基础统计，作为全链路输入规模与质量基线。",
    "s2": "生成合规标记，为 LAC 纠偏与过滤提供辅助信息。",
    "s3": "对 LAC 粒度做聚合，形成可信 LAC 评估输入。",
    "s4": "从全量 LAC 中筛出结构可信、样本足够的 LAC 集合。",
    "s5": "在可信 LAC 范围内聚合 Cell 行为，用于 BS 主库和异常检测。",
    "s6": "把 LAC/Cell 纠偏结果回写到明细，产出合规过滤后的主事实表。",
    "s30": "按 BS 聚合空间锚点，识别高风险桶、碰撞桶和共建桶。",
    "s31": "用 BS 主库修正或回填 GPS，区分已验证、缺失和漂移记录。",
    "s32": "对比 GPS 修正前后效果，形成校验结果。",
    "s33": "用 Cell/BS 画像补齐缺失信号字段，并统计补齐来源。",
    "s34": "对比信号补齐前后效果，形成校验结果。",
    "s35": "识别动态 Cell，为画像和异常样本提供标签。",
    "s36": "识别 BS ID 异常模式，补充异常解释。",
    "s37": "标记样本不足但疑似碰撞的 BS，避免误判。",
    "s38": "产出 Cell-BS 映射交付表。",
    "s40": "在完整明细上回放 GPS 修正逻辑，形成最终回归结果。",
    "s41": "在完整明细上回放信号补齐逻辑，得到最终可消费事实表。",
    "s42": "对最终回归前后做结果对比。",
    "s50": "构建 LAC 画像与基线。",
    "s51": "构建 BS 画像与基线。",
    "s52": "构建 Cell 画像与基线。",
}

PRIMARY_STEP_METRICS = {
    "s0": ("total", "原始记录数"),
    "s4": ("trusted_lac_cnt", "可信LAC数"),
    "s6": ("output_rows", "合规输出行数"),
    "s30": ("total_bs", "可信BS数"),
    "s31": ("filled_from_bs", "GPS回填行数"),
    "s33": ("by_cell", "Cell补齐行数"),
    "s41": ("total", "最终明细行数"),
    "s50": ("lac_profiles", "LAC画像数"),
    "s51": ("bs_profiles", "BS画像数"),
    "s52": ("cell_profiles", "Cell画像数"),
}

FIELD_LABELS = {
    "record_id": "记录ID",
    "operator_id_cn": "运营商中文标识",
    "operator_id_raw": "运营商原始编码",
    "operator_group_hint": "运营商分组提示",
    "tech_norm": "标准制式",
    "lac_dec": "LAC",
    "lac_dec_final": "最终LAC",
    "lac_raw_text": "原始LAC文本",
    "bs_id": "基站ID",
    "cell_id_dec": "Cell ID",
    "wuli_fentong_bs_key": "物理分桶BS键",
    "record_count": "记录数",
    "valid_gps_count": "GPS有效行数",
    "gps_valid_count": "GPS有效行数",
    "gps_missing_count": "GPS缺失行数",
    "gps_valid_ratio": "GPS有效率",
    "gps_center_lon": "GPS中心经度",
    "gps_center_lat": "GPS中心纬度",
    "gps_dist_p50_m": "GPS距离P50(米)",
    "gps_dist_p90_m": "GPS距离P90(米)",
    "gps_dist_max_m": "GPS距离最大值(米)",
    "gps_p50_dist_m": "GPS距离P50(米)",
    "gps_p90_dist_m": "GPS距离P90(米)",
    "gps_max_dist_m": "GPS距离最大值(米)",
    "active_days": "活跃天数",
    "distinct_bs_count": "BS去重数",
    "distinct_cell_count": "Cell去重数",
    "distinct_cellid_count": "Cell去重数",
    "distinct_device_count": "设备去重数",
    "first_seen_ts": "最早时间",
    "last_seen_ts": "最晚时间",
    "report_date": "上报日期",
    "source_table": "来源表",
    "match_status": "匹配状态",
    "gps_status": "GPS状态",
    "gps_status_final": "最终GPS状态",
    "gps_source": "GPS来源",
    "gps_dist_to_bs_m": "到BS距离(米)",
    "signal_fill_source": "信号补齐来源",
    "signal_missing_before_cnt": "补齐前缺失字段数",
    "signal_missing_after_cnt": "补齐后缺失字段数",
    "is_collision_suspect": "碰撞疑似标记",
    "is_severe_collision": "严重碰撞标记",
    "collision_reason": "碰撞原因",
    "is_dynamic_cell": "动态Cell标记",
    "dynamic_reason": "动态原因",
    "half_major_dist_km": "半长轴距离(KM)",
    "is_gps_unstable": "GPS不稳定",
    "is_insufficient_sample": "样本不足",
    "is_bs_id_lt_256": "BS_ID异常(<256)",
    "is_multi_operator_shared": "多运营商共享",
    "shared_operator_cnt": "共享运营商数",
    "shared_operator_list": "共享运营商列表",
    "fill_needed_count": "需要补齐行数",
    "fill_success_count": "补齐成功行数",
    "fill_failed_count": "补齐失败行数",
    "missing_fields_before": "补齐前缺失字段数",
    "missing_fields_after": "补齐后缺失字段数",
    "filled_fields_total": "补齐字段总数",
    "rsrp_valid_ratio": "RSRP有效率",
    "rsrq_valid_ratio": "RSRQ有效率",
    "sinr_valid_ratio": "SINR有效率",
    "dbm_valid_ratio": "DBM有效率",
    # 原始信号字段
    "tech": "原始制式",
    "sig_rsrp": "RSRP",
    "sig_rsrq": "RSRQ",
    "sig_sinr": "SINR",
    "sig_rssi": "RSSI",
    "lon_raw": "原始经度",
    "lat_raw": "原始纬度",
    "lon_final": "最终经度",
    "lat_final": "最终纬度",
    "sig_rsrp_final": "最终RSRP",
    "sig_rsrq_final": "最终RSRQ",
    "sig_sinr_final": "最终SINR",
    "sig_rssi_final": "最终RSSI",
    # 合规相关
    "lac_enrich_status": "LAC纠偏状态",
    "src_record_id": "源记录ID",
    "gps_valid_level": "GPS有效级别",
}


def table_label(table_name: str) -> str:
    return TABLE_LABELS.get(table_name, table_name)


def layer_label(layer_id: str) -> str:
    return LAYER_LABELS.get(layer_id, layer_id)


def anomaly_label(code: str) -> str:
    return ANOMALY_LABELS.get(code, code)


def object_level_label(code: str) -> str:
    return OBJECT_LEVEL_LABELS.get(code, code)


def run_mode_label(code: str | None) -> str:
    if not code:
        return "—"
    return RUN_MODE_LABELS.get(code, code)


def status_label(code: str | None) -> str:
    if not code:
        return "—"
    return STATUS_LABELS.get(code, code)


def field_label(field_name: str) -> str:
    return FIELD_LABELS.get(field_name, field_name)
