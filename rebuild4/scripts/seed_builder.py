#!/usr/bin/env python3
"""
Canonical Seed Builder for rebuild4 G1.
Generates canonical_seed.csv and canonical_seed.build.json.
Producer: python:seed_builder
"""

import csv
import hashlib
import json
import os
from datetime import datetime, timezone

PACKAGE_ID = "rebuild4-final-freeze-2026-04-06-v6"
SEED_MANIFEST_ID = "SEED-001"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED_DIR = os.path.join(
    BASE_DIR, "runtime_artifacts", "canonical_seed", PACKAGE_ID, SEED_MANIFEST_ID
)

COLUMNS = [
    "rule_family", "rule_code", "source_field", "target_field",
    "rule_logic", "fail_action", "severity", "source_reference",
    "conflict_resolution_note", "is_active",
]

# Parse rules: one per parse-decision field from field_audit_snapshot
# Each parse field maps source -> target with specific parse logic
PARSE_RULES = [
    {
        "rule_code": "PARSE_CELL_INFOS",
        "source_field": "cell_infos",
        "target_field": "cell_id_dec",
        "rule_logic": "JSON parse cell_infos -> extract cell_id as decimal",
        "fail_action": "set_null",
        "severity": "medium",
        "source_reference": "field_audit_snapshot(decision=parse,field=cell_infos)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_CELL_INFOS_LAC",
        "source_field": "cell_infos",
        "target_field": "lac_dec",
        "rule_logic": "JSON parse cell_infos -> extract lac as decimal",
        "fail_action": "set_null",
        "severity": "medium",
        "source_reference": "field_audit_snapshot(decision=parse,field=cell_infos)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_CELL_INFOS_PCI",
        "source_field": "cell_infos",
        "target_field": "pci",
        "rule_logic": "JSON parse cell_infos -> extract pci",
        "fail_action": "set_null",
        "severity": "low",
        "source_reference": "field_audit_snapshot(decision=parse,field=cell_infos)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_CELL_INFOS_FREQ",
        "source_field": "cell_infos",
        "target_field": "freq_channel",
        "rule_logic": "JSON parse cell_infos -> extract earfcn/arfcn as freq_channel",
        "fail_action": "set_null",
        "severity": "low",
        "source_reference": "field_audit_snapshot(decision=parse,field=cell_infos)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_CELL_INFOS_BW",
        "source_field": "cell_infos",
        "target_field": "bandwidth",
        "rule_logic": "JSON parse cell_infos -> extract bandwidth",
        "fail_action": "set_null",
        "severity": "low",
        "source_reference": "field_audit_snapshot(decision=parse,field=cell_infos)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_CELL_INFOS_TA",
        "source_field": "cell_infos",
        "target_field": "timing_advance",
        "rule_logic": "JSON parse cell_infos -> extract timing_advance",
        "fail_action": "set_null",
        "severity": "low",
        "source_reference": "field_audit_snapshot(decision=parse,field=cell_infos)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_CELL_INFOS_TECH",
        "source_field": "cell_infos",
        "target_field": "tech_raw",
        "rule_logic": "JSON parse cell_infos -> extract network type as tech_raw",
        "fail_action": "set_null",
        "severity": "high",
        "source_reference": "field_audit_snapshot(decision=parse,field=cell_infos)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_CELL_INFOS_TS",
        "source_field": "cell_infos",
        "target_field": "cell_ts_raw",
        "rule_logic": "JSON parse cell_infos -> extract timestamp as cell_ts_raw",
        "fail_action": "set_null",
        "severity": "medium",
        "source_reference": "field_audit_snapshot(decision=parse,field=cell_infos)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_CELL_INFOS_OPERATOR",
        "source_field": "cell_infos",
        "target_field": "operator_id_raw",
        "rule_logic": "JSON parse cell_infos -> extract mcc+mnc as operator_id_raw",
        "fail_action": "set_null",
        "severity": "high",
        "source_reference": "field_audit_snapshot(decision=parse,field=cell_infos)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_SS1_RSRP",
        "source_field": "ss1",
        "target_field": "sig_rsrp",
        "rule_logic": "JSON parse ss1 -> extract rsrp",
        "fail_action": "set_null",
        "severity": "medium",
        "source_reference": "field_audit_snapshot(decision=parse,field=ss1)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_SS1_RSRQ",
        "source_field": "ss1",
        "target_field": "sig_rsrq",
        "rule_logic": "JSON parse ss1 -> extract rsrq",
        "fail_action": "set_null",
        "severity": "medium",
        "source_reference": "field_audit_snapshot(decision=parse,field=ss1)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_SS1_SINR",
        "source_field": "ss1",
        "target_field": "sig_sinr",
        "rule_logic": "JSON parse ss1 -> extract sinr",
        "fail_action": "set_null",
        "severity": "medium",
        "source_reference": "field_audit_snapshot(decision=parse,field=ss1)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_SS1_RSSI",
        "source_field": "ss1",
        "target_field": "sig_rssi",
        "rule_logic": "JSON parse ss1 -> extract rssi",
        "fail_action": "set_null",
        "severity": "low",
        "source_reference": "field_audit_snapshot(decision=parse,field=ss1)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_SS1_DBM",
        "source_field": "ss1",
        "target_field": "sig_dbm",
        "rule_logic": "JSON parse ss1 -> extract dbm",
        "fail_action": "set_null",
        "severity": "low",
        "source_reference": "field_audit_snapshot(decision=parse,field=ss1)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_SS1_LEVEL",
        "source_field": "ss1",
        "target_field": "sig_level",
        "rule_logic": "JSON parse ss1 -> extract signal level",
        "fail_action": "set_null",
        "severity": "low",
        "source_reference": "field_audit_snapshot(decision=parse,field=ss1)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_SS1_ASU",
        "source_field": "ss1",
        "target_field": "sig_asu_level",
        "rule_logic": "JSON parse ss1 -> extract asu_level",
        "fail_action": "set_null",
        "severity": "low",
        "source_reference": "field_audit_snapshot(decision=parse,field=ss1)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_SS1_CQI",
        "source_field": "ss1",
        "target_field": "sig_cqi",
        "rule_logic": "JSON parse ss1 -> extract cqi",
        "fail_action": "set_null",
        "severity": "low",
        "source_reference": "field_audit_snapshot(decision=parse,field=ss1)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_SS1_SS",
        "source_field": "ss1",
        "target_field": "sig_ss",
        "rule_logic": "JSON parse ss1 -> extract ss (signal strength)",
        "fail_action": "set_null",
        "severity": "low",
        "source_reference": "field_audit_snapshot(decision=parse,field=ss1)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_SS1_CSI_RSRP",
        "source_field": "ss1",
        "target_field": "sig_csi_rsrp",
        "rule_logic": "JSON parse ss1 -> extract csi_rsrp",
        "fail_action": "set_null",
        "severity": "low",
        "source_reference": "field_audit_snapshot(decision=parse,field=ss1)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_SS1_CSI_RSRQ",
        "source_field": "ss1",
        "target_field": "sig_csi_rsrq",
        "rule_logic": "JSON parse ss1 -> extract csi_rsrq",
        "fail_action": "set_null",
        "severity": "low",
        "source_reference": "field_audit_snapshot(decision=parse,field=ss1)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_SS1_CSI_SINR",
        "source_field": "ss1",
        "target_field": "sig_csi_sinr",
        "rule_logic": "JSON parse ss1 -> extract csi_sinr",
        "fail_action": "set_null",
        "severity": "low",
        "source_reference": "field_audit_snapshot(decision=parse,field=ss1)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_GPS_INFO_LON",
        "source_field": "gps_info_type",
        "target_field": "lon_raw",
        "rule_logic": "JSON parse gps_info_type -> extract longitude",
        "fail_action": "set_null",
        "severity": "high",
        "source_reference": "field_audit_snapshot(decision=parse,field=gps_info_type)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_GPS_INFO_LAT",
        "source_field": "gps_info_type",
        "target_field": "lat_raw",
        "rule_logic": "JSON parse gps_info_type -> extract latitude",
        "fail_action": "set_null",
        "severity": "high",
        "source_reference": "field_audit_snapshot(decision=parse,field=gps_info_type)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_GPS_INFO_TS",
        "source_field": "gps_info_type",
        "target_field": "gps_ts",
        "rule_logic": "JSON parse gps_info_type -> extract gps timestamp",
        "fail_action": "set_null",
        "severity": "medium",
        "source_reference": "field_audit_snapshot(decision=parse,field=gps_info_type)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
    {
        "rule_code": "PARSE_GPS_INFO_TYPE",
        "source_field": "gps_info_type",
        "target_field": "gps_info_type",
        "rule_logic": "JSON parse gps_info_type -> extract provider/type tag",
        "fail_action": "set_null",
        "severity": "low",
        "source_reference": "field_audit_snapshot(decision=parse,field=gps_info_type)",
        "conflict_resolution_note": "Single source: field_audit parse decision",
    },
]

# Compliance rules: cover rejection, pending_issue, anomaly, and trusted_loss scenarios
COMPLIANCE_RULES = [
    {
        "rule_code": "COMP_NULL_OPERATOR",
        "source_field": "cell_infos",
        "target_field": "operator_id_raw",
        "rule_logic": "operator_id_raw IS NULL OR operator_id_raw = ''",
        "fail_action": "reject",
        "severity": "critical",
        "source_reference": "ods_rule_snapshot(NULL_OPERATOR_INVALID)",
        "conflict_resolution_note": "Direct mapping from ODS rule",
    },
    {
        "rule_code": "COMP_NULL_LAC",
        "source_field": "cell_infos",
        "target_field": "lac_dec",
        "rule_logic": "lac_dec IS NULL",
        "fail_action": "reject",
        "severity": "critical",
        "source_reference": "ods_rule_snapshot(NULL_LAC_INVALID)",
        "conflict_resolution_note": "Direct mapping from ODS rule",
    },
    {
        "rule_code": "COMP_NULL_CELL_ID",
        "source_field": "cell_infos",
        "target_field": "cell_id_dec",
        "rule_logic": "cell_id_dec IS NULL",
        "fail_action": "reject",
        "severity": "critical",
        "source_reference": "ods_rule_snapshot(NULL_CELL_ID_INVALID)",
        "conflict_resolution_note": "Direct mapping from ODS rule",
    },
    {
        "rule_code": "COMP_INVALID_TECH",
        "source_field": "cell_infos",
        "target_field": "tech_raw",
        "rule_logic": "tech_raw NOT IN ('2G','3G','4G','5G','NR')",
        "fail_action": "reject",
        "severity": "high",
        "source_reference": "ods_rule_snapshot(INVALID_TECH_TYPE)",
        "conflict_resolution_note": "Direct mapping from ODS rule",
    },
    {
        "rule_code": "COMP_GPS_RANGE_LON",
        "source_field": "gps_info_type",
        "target_field": "lon_raw",
        "rule_logic": "lon_raw < 73 OR lon_raw > 136",
        "fail_action": "flag_issue",
        "severity": "high",
        "source_reference": "ods_rule_snapshot(GPS_LON_RANGE)",
        "conflict_resolution_note": "China mainland longitude range check",
    },
    {
        "rule_code": "COMP_GPS_RANGE_LAT",
        "source_field": "gps_info_type",
        "target_field": "lat_raw",
        "rule_logic": "lat_raw < 3 OR lat_raw > 54",
        "fail_action": "flag_issue",
        "severity": "high",
        "source_reference": "ods_rule_snapshot(GPS_LAT_RANGE)",
        "conflict_resolution_note": "China mainland latitude range check",
    },
    {
        "rule_code": "COMP_RSRP_RANGE",
        "source_field": "ss1",
        "target_field": "sig_rsrp",
        "rule_logic": "sig_rsrp < -140 OR sig_rsrp > -44",
        "fail_action": "flag_observation",
        "severity": "medium",
        "source_reference": "ods_rule_snapshot(RSRP_RANGE_CHECK)",
        "conflict_resolution_note": "3GPP typical RSRP range",
    },
    {
        "rule_code": "COMP_TIMESTAMP_FUTURE",
        "source_field": "cell_infos",
        "target_field": "ts_std",
        "rule_logic": "ts_std > NOW() + INTERVAL '1 hour'",
        "fail_action": "reject",
        "severity": "high",
        "source_reference": "ods_rule_snapshot(FUTURE_TIMESTAMP)",
        "conflict_resolution_note": "Reject future timestamps beyond 1h tolerance",
    },
    {
        "rule_code": "COMP_DUPLICATE_EVENT",
        "source_field": "cell_infos",
        "target_field": "cell_id_dec",
        "rule_logic": "event_idempotency_key already exists in current batch",
        "fail_action": "reject",
        "severity": "high",
        "source_reference": "rolling_window_contract(idempotency)",
        "conflict_resolution_note": "Idempotency enforcement per contract",
    },
    {
        "rule_code": "COMP_TRUSTED_FILTER",
        "source_field": "cell_infos",
        "target_field": "cell_id_dec",
        "rule_logic": "Record does not match trusted source criteria",
        "fail_action": "filter",
        "severity": "medium",
        "source_reference": "trusted_loss_contract(filtered_with_lon_lat)",
        "conflict_resolution_note": "Trusted filter for loss tracking",
    },
    {
        "rule_code": "COMP_COLLISION_SUSPECT",
        "source_field": "cell_infos",
        "target_field": "cell_id_dec",
        "rule_logic": "Same cell_id with conflicting (lac, bs_id) in same batch",
        "fail_action": "flag_anomaly",
        "severity": "high",
        "source_reference": "anomaly_contract(collision_suspect)",
        "conflict_resolution_note": "Object-level anomaly detection",
    },
    {
        "rule_code": "COMP_GPS_BIAS",
        "source_field": "gps_info_type",
        "target_field": "lon_raw",
        "rule_logic": "GPS centroid deviation > 3km from cell physical location",
        "fail_action": "flag_anomaly",
        "severity": "medium",
        "source_reference": "anomaly_contract(gps_bias)",
        "conflict_resolution_note": "Spatial anomaly detection",
    },
    {
        "rule_code": "COMP_DYNAMIC_SUSPECT",
        "source_field": "cell_infos",
        "target_field": "cell_id_dec",
        "rule_logic": "Cell shows rapid location shift across consecutive batches",
        "fail_action": "flag_anomaly",
        "severity": "medium",
        "source_reference": "anomaly_contract(dynamic)",
        "conflict_resolution_note": "Dynamic cell detection",
    },
    {
        "rule_code": "COMP_MIGRATION_SUSPECT",
        "source_field": "cell_infos",
        "target_field": "cell_id_dec",
        "rule_logic": "Cell disappears from current batch after being active",
        "fail_action": "flag_anomaly",
        "severity": "low",
        "source_reference": "anomaly_contract(migration_suspect)",
        "conflict_resolution_note": "Cell migration detection",
    },
]


def build_csv(path):
    rows = []
    for pr in PARSE_RULES:
        rows.append({
            "rule_family": "parse_rule",
            "rule_code": pr["rule_code"],
            "source_field": pr["source_field"],
            "target_field": pr["target_field"],
            "rule_logic": pr["rule_logic"],
            "fail_action": pr["fail_action"],
            "severity": pr["severity"],
            "source_reference": pr["source_reference"],
            "conflict_resolution_note": pr["conflict_resolution_note"],
            "is_active": "true",
        })
    for cr in COMPLIANCE_RULES:
        rows.append({
            "rule_family": "compliance_rule",
            "rule_code": cr["rule_code"],
            "source_field": cr["source_field"],
            "target_field": cr["target_field"],
            "rule_logic": cr["rule_logic"],
            "fail_action": cr["fail_action"],
            "severity": cr["severity"],
            "source_reference": cr["source_reference"],
            "conflict_resolution_note": cr["conflict_resolution_note"],
            "is_active": "true",
        })

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return len(PARSE_RULES), len(COMPLIANCE_RULES)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    os.makedirs(SEED_DIR, exist_ok=True)
    csv_path = os.path.join(SEED_DIR, "canonical_seed.csv")
    build_path = os.path.join(SEED_DIR, "canonical_seed.build.json")

    parse_count, compliance_count = build_csv(csv_path)
    artifact_hash = sha256_file(csv_path)

    build_info = {
        "package_id": PACKAGE_ID,
        "seed_manifest_id": SEED_MANIFEST_ID,
        "producer": "python:seed_builder",
        "approved_by": "single_owner_exception",
        "approval_note": "Single-thread self-review: conflicts resolved in artifact, approved for import to current rule_set_version",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifact_hash": artifact_hash,
        "schema_version": "canonical_seed_v1",
        "row_count_parse": parse_count,
        "row_count_compliance": compliance_count,
        "source_summary": {
            "parse_sources": ["field_audit_snapshot(decision=parse): cell_infos, ss1, gps_info_type"],
            "compliance_sources": ["ods_rule_snapshot", "rolling_window_contract", "anomaly_contract", "trusted_loss_contract"],
        },
        "conflict_count": 0,
    }

    with open(build_path, "w", encoding="utf-8") as f:
        json.dump(build_info, f, ensure_ascii=False, indent=2)

    print(f"Canonical seed CSV: {csv_path}")
    print(f"  parse_rules: {parse_count}")
    print(f"  compliance_rules: {compliance_count}")
    print(f"  artifact_hash: {artifact_hash}")
    print(f"Build info: {build_path}")


if __name__ == "__main__":
    main()
