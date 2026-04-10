"""Frozen ETL field definitions for rebuild5 Step 1."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable


RAW_FIELD_DEFINITIONS: list[dict[str, str]] = [
    {"name": "记录数唯一标识", "type": "varchar", "decision": "keep", "category": "标识"},
    {"name": "数据来源dna或daa", "type": "varchar", "decision": "keep", "category": "元数据"},
    {"name": "did", "type": "varchar", "decision": "keep", "category": "标识"},
    {"name": "ts", "type": "varchar", "decision": "keep", "category": "时间"},
    {"name": "ip", "type": "varchar", "decision": "keep", "category": "网络"},
    {"name": "pkg_name", "type": "varchar", "decision": "keep", "category": "元数据"},
    {"name": "wifi_name", "type": "varchar", "decision": "keep", "category": "网络"},
    {"name": "wifi_mac", "type": "varchar", "decision": "keep", "category": "网络"},
    {"name": "sdk_ver", "type": "varchar", "decision": "keep", "category": "元数据"},
    {"name": "gps上报时间", "type": "varchar", "decision": "keep", "category": "时间"},
    {"name": "主卡运营商id", "type": "varchar", "decision": "keep", "category": "网络"},
    {"name": "品牌", "type": "varchar", "decision": "keep", "category": "元数据"},
    {"name": "机型", "type": "varchar", "decision": "keep", "category": "元数据"},
    {"name": "gps_info_type", "type": "varchar", "decision": "parse", "category": "位置"},
    {"name": "原始上报gps", "type": "varchar", "decision": "keep", "category": "位置"},
    {"name": "cell_infos", "type": "text", "decision": "parse", "category": "核心"},
    {"name": "ss1", "type": "text", "decision": "parse", "category": "核心"},
    {"name": "当前数据最终经度", "type": "float8", "decision": "drop", "category": "位置"},
    {"name": "当前数据最终纬度", "type": "float8", "decision": "drop", "category": "位置"},
    {"name": "android_ver", "type": "varchar", "decision": "drop", "category": "元数据"},
    {"name": "cpu_info", "type": "varchar", "decision": "keep", "category": "元数据"},
    {"name": "基带版本信息", "type": "varchar", "decision": "drop", "category": "元数据"},
    {"name": "arp_list", "type": "text", "decision": "drop", "category": "网络"},
    {"name": "压力", "type": "varchar", "decision": "keep", "category": "元数据"},
    {"name": "imei", "type": "varchar", "decision": "drop", "category": "标识"},
    {"name": "oaid", "type": "varchar", "decision": "keep", "category": "标识"},
    {"name": "来源标记列", "type": "varchar", "decision": "drop", "category": "元数据"},
]

# 55 target fields after parsing — grouped by category, matching rebuild4
L0_FIELD_DEFINITIONS: list[dict[str, str]] = [
    # ── 标识 (2) ──
    {"name": "record_id", "name_cn": "原始记录ID", "type": "varchar", "source": "直接映射", "category": "标识", "desc": "原始表的记录数唯一标识，拆分后多行共享"},
    {"name": "dataset_key", "name_cn": "数据集", "type": "varchar", "source": "标签", "category": "标识", "desc": "数据集标识（如 sample_6lac）"},
    # ── 来源 (2) ──
    {"name": "data_source", "name_cn": "数据来源", "type": "varchar", "source": "直接映射", "category": "来源", "desc": "SDK/其他来源（当前全部为 sdk）"},
    {"name": "data_source_detail", "name_cn": "来源明细", "type": "varchar", "source": "直接映射", "category": "来源", "desc": "原始表的 数据来源dna或daa"},
    # ── 解析 (1) ──
    {"name": "cell_origin", "name_cn": "Cell来源", "type": "varchar", "source": "标签", "category": "解析", "desc": "cell_infos / ss1（该 cell_id 来自哪个字段）"},
    # ── 补齐 (5) ──
    {"name": "gps_filled_from", "name_cn": "GPS补齐来源", "type": "varchar", "source": "标签", "category": "补齐", "desc": "raw_gps / ss1_own / same_cell / none"},
    {"name": "gps_fill_source", "name_cn": "GPS来源链路", "type": "varchar", "source": "标签", "category": "补齐", "desc": "补齐后最终 GPS 来源标记"},
    {"name": "rsrp_fill_source", "name_cn": "RSRP补齐来源", "type": "varchar", "source": "标签", "category": "补齐", "desc": "original / same_cell / none"},
    {"name": "operator_fill_source", "name_cn": "运营商补齐来源", "type": "varchar", "source": "标签", "category": "补齐", "desc": "original / same_cell / none"},
    {"name": "has_cell_id", "name_cn": "有cell_id", "type": "boolean", "source": "计算派生", "category": "补齐", "desc": "是否有有效 cell_id"},
    # ── 网络 (11) ──
    {"name": "tech_raw", "name_cn": "原始制式", "type": "varchar", "source": "解析提取", "category": "网络", "desc": "lte / nr / gsm / wcdma（原始值）"},
    {"name": "tech_norm", "name_cn": "标准制式", "type": "varchar", "source": "计算派生", "category": "网络", "desc": "2G / 3G / 4G / 5G"},
    {"name": "operator_code", "name_cn": "运营商编码", "type": "varchar", "source": "解析提取", "category": "网络", "desc": "PLMN 原始值（如 46000）"},
    {"name": "operator_cn", "name_cn": "运营商中文", "type": "varchar", "source": "计算派生", "category": "网络", "desc": "移动/联通/电信/广电/铁路"},
    {"name": "lac", "name_cn": "LAC", "type": "bigint", "source": "解析提取", "category": "网络", "desc": "cell_infos: Tac/tac/lac / ss1: 第3值"},
    {"name": "cell_id", "name_cn": "CellID", "type": "bigint", "source": "解析提取", "category": "网络", "desc": "cell_infos: Ci/Nci/nci/cid / ss1: 第2值"},
    {"name": "bs_id", "name_cn": "基站ID", "type": "bigint", "source": "计算派生", "category": "网络", "desc": "4G: cell_id/256, 5G: cell_id/4096"},
    {"name": "sector_id", "name_cn": "扇区ID", "type": "bigint", "source": "计算派生", "category": "网络", "desc": "4G: cell_id%256, 5G: cell_id%4096"},
    {"name": "pci", "name_cn": "PCI", "type": "int", "source": "解析提取", "category": "网络", "desc": "物理小区标识"},
    {"name": "freq_channel", "name_cn": "频点号", "type": "int", "source": "解析提取", "category": "网络", "desc": "频率通道号"},
    {"name": "bandwidth", "name_cn": "带宽", "type": "int", "source": "解析提取", "category": "网络", "desc": "带宽(kHz)，仅 LTE 主服务区"},
    # ── 信号 (13) ──
    {"name": "rsrp", "name_cn": "RSRP", "type": "int", "source": "解析提取", "category": "信号", "desc": "LTE:rsrp / NR:SsRsrp (dBm)"},
    {"name": "rsrq", "name_cn": "RSRQ", "type": "int", "source": "解析提取", "category": "信号", "desc": "LTE:rsrq / NR:SsRsrq (dB)"},
    {"name": "sinr", "name_cn": "SINR", "type": "int", "source": "解析提取", "category": "信号", "desc": "LTE:rssnr / NR:SsSinr (dB)"},
    {"name": "rssi", "name_cn": "RSSI", "type": "int", "source": "解析提取", "category": "信号", "desc": "仅 LTE (dBm)"},
    {"name": "dbm", "name_cn": "Dbm", "type": "int", "source": "解析提取", "category": "信号", "desc": "通用信号强度 (dBm)"},
    {"name": "asu_level", "name_cn": "ASU等级", "type": "int", "source": "解析提取", "category": "信号", "desc": "0~99"},
    {"name": "sig_level", "name_cn": "信号等级", "type": "int", "source": "解析提取", "category": "信号", "desc": "0~4"},
    {"name": "sig_ss", "name_cn": "SS原始值", "type": "int", "source": "解析提取", "category": "信号", "desc": "ss1 原始信号强度"},
    {"name": "timing_advance", "name_cn": "时间提前量", "type": "int", "source": "解析提取", "category": "信号", "desc": "仅主服务区少量有"},
    {"name": "csi_rsrp", "name_cn": "CSI-RSRP", "type": "int", "source": "解析提取", "category": "信号", "desc": "仅少量 NR"},
    {"name": "csi_rsrq", "name_cn": "CSI-RSRQ", "type": "int", "source": "解析提取", "category": "信号", "desc": "仅少量 NR"},
    {"name": "csi_sinr", "name_cn": "CSI-SINR", "type": "int", "source": "解析提取", "category": "信号", "desc": "仅少量 NR"},
    {"name": "cqi", "name_cn": "CQI", "type": "int", "source": "解析提取", "category": "信号", "desc": "仅少量 LTE"},
    # ── 时间 (5) ──
    {"name": "ts_raw", "name_cn": "上报时间原始", "type": "varchar", "source": "直接映射", "category": "时间", "desc": "原始 ts 文本"},
    {"name": "report_ts", "name_cn": "上报时间", "type": "timestamptz", "source": "计算派生", "category": "时间", "desc": "标准化后的上报时间"},
    {"name": "cell_ts_raw", "name_cn": "基站时间原始", "type": "varchar", "source": "解析提取", "category": "时间", "desc": "cell_infos.timeStamp 或 ss1 元素2"},
    {"name": "cell_ts_std", "name_cn": "基站时间", "type": "timestamptz", "source": "计算派生", "category": "时间", "desc": "标准化后的基站扫描时间"},
    {"name": "event_time_std", "name_cn": "事件时间", "type": "timestamptz", "source": "计算派生", "category": "时间", "desc": "COALESCE(cell_ts_std, report_ts, gps_ts)"},
    # ── 位置 (4) ──
    {"name": "gps_info_type", "name_cn": "GPS类型", "type": "varchar", "source": "解析提取", "category": "位置", "desc": "GPS 信息类型"},
    {"name": "lon_raw", "name_cn": "经度", "type": "float8", "source": "解析提取", "category": "位置", "desc": "cell_infos: 原始上报GPS / ss1: 本组GPS"},
    {"name": "lat_raw", "name_cn": "纬度", "type": "float8", "source": "解析提取", "category": "位置", "desc": "cell_infos: 原始上报GPS / ss1: 本组GPS"},
    {"name": "gps_valid", "name_cn": "GPS有效", "type": "boolean", "source": "计算派生", "category": "位置", "desc": "gps_info_type 为 gps/1 时 true"},
    # ── 元数据 (12) ──
    {"name": "dev_id", "name_cn": "设备标识", "type": "varchar", "source": "直接映射", "category": "元数据", "desc": "设备唯一标识"},
    {"name": "ip", "name_cn": "IP地址", "type": "varchar", "source": "直接映射", "category": "元数据", "desc": "上报 IP"},
    {"name": "plmn_main", "name_cn": "主卡运营商", "type": "varchar", "source": "直接映射", "category": "元数据", "desc": "主卡 PLMN"},
    {"name": "brand", "name_cn": "品牌", "type": "varchar", "source": "直接映射", "category": "元数据", "desc": "手机品牌"},
    {"name": "model", "name_cn": "机型", "type": "varchar", "source": "直接映射", "category": "元数据", "desc": "手机机型"},
    {"name": "sdk_ver", "name_cn": "SDK版本", "type": "varchar", "source": "直接映射", "category": "元数据", "desc": "SDK 版本"},
    {"name": "oaid", "name_cn": "OAID", "type": "varchar", "source": "直接映射", "category": "元数据", "desc": "匿名标识"},
    {"name": "pkg_name", "name_cn": "应用包名", "type": "varchar", "source": "直接映射", "category": "元数据", "desc": "上报应用包名"},
    {"name": "wifi_name", "name_cn": "WiFi名称", "type": "varchar", "source": "直接映射", "category": "元数据", "desc": "WiFi SSID"},
    {"name": "wifi_mac", "name_cn": "WiFi MAC", "type": "varchar", "source": "直接映射", "category": "元数据", "desc": "WiFi BSSID"},
    {"name": "cpu_info", "name_cn": "CPU信息", "type": "varchar", "source": "直接映射", "category": "元数据", "desc": "CPU 信息"},
    {"name": "pressure", "name_cn": "气压", "type": "varchar", "source": "直接映射", "category": "元数据", "desc": "气压传感器读数"},
]

CATEGORY_ORDER = ['标识', '来源', '解析', '补齐', '网络', '信号', '时间', '位置', '元数据']


def summarize_decisions(fields: Iterable[dict[str, str]]) -> dict[str, int]:
    counter = Counter(field["decision"] for field in fields)
    return {
        "keep": counter.get("keep", 0),
        "parse": counter.get("parse", 0),
        "drop": counter.get("drop", 0),
    }


def get_l0_field_groups() -> list[dict]:
    """Return L0 fields grouped by category with counts."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for f in L0_FIELD_DEFINITIONS:
        groups[f['category']].append(f)

    result = []
    for cat in CATEGORY_ORDER:
        fields = groups.get(cat, [])
        if fields:
            result.append({
                'category': cat,
                'count': len(fields),
                'fields': [
                    {'name': f['name'], 'name_cn': f['name_cn'], 'type': f['type'], 'source': f['source'], 'desc': f['desc']}
                    for f in fields
                ],
            })
    return result
