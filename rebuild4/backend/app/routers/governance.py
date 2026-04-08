"""API-11: governance/* (12 endpoints)."""
from fastapi import APIRouter, Query, Path
from fastapi.responses import JSONResponse
from ..core.database import fetchall, fetchone
from ..core.envelope import envelope, error_response
from ..core.context import base_context, CONTRACT_VERSION

router = APIRouter(prefix="/api/governance", tags=["governance"])


def _gov_ctx():
    ctx = base_context()
    return ctx


@router.get("/overview")
def governance_overview():
    ctx = _gov_ctx()
    field_count = fetchone("SELECT COUNT(*) as cnt FROM rebuild4_meta.asset_field_catalog")
    table_count = fetchone("SELECT COUNT(*) as cnt FROM rebuild4_meta.asset_table_catalog")
    usage_count = fetchone("SELECT COUNT(*) as cnt FROM rebuild4_meta.asset_usage_map")
    migration_count = fetchone("SELECT COUNT(*) as cnt FROM rebuild4_meta.asset_migration_decision")
    rule_count = fetchone("SELECT COUNT(*) as cnt FROM rebuild4_meta.parse_rule WHERE is_active = true")
    comp_count = fetchone("SELECT COUNT(*) as cnt FROM rebuild4_meta.compliance_rule WHERE is_active = true")

    return envelope({
        "field_count": int(field_count["cnt"]) if field_count else 0,
        "table_count": int(table_count["cnt"]) if table_count else 0,
        "usage_registrations": int(usage_count["cnt"]) if usage_count else 0,
        "migration_decisions": int(migration_count["cnt"]) if migration_count else 0,
        "active_parse_rules": int(rule_count["cnt"]) if rule_count else 0,
        "active_compliance_rules": int(comp_count["cnt"]) if comp_count else 0,
        "field_audit_total": 27,
        "target_field_total": 55,
        "ods_rule_total": 26,
        "ods_execution_total": 24,
    }, subject_scope="governance", context=ctx)


@router.get("/fields")
def governance_fields(
    tier: str = Query(None), type: str = Query(None),
    core: str = Query(None), migration: str = Query(None),
    q: str = Query(None), page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
):
    ctx = _gov_ctx()
    conditions = ["1=1"]
    params: list = []
    if q:
        conditions.append("(field_name ILIKE %s OR table_name ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
    where = " AND ".join(conditions)
    offset = (page - 1) * size
    rows = fetchall(f"""
        SELECT * FROM rebuild4_meta.asset_field_catalog WHERE {where}
        ORDER BY schema_name, table_name, field_name LIMIT %s OFFSET %s
    """, (*params, size, offset))
    total = fetchone(f"SELECT COUNT(*) as cnt FROM rebuild4_meta.asset_field_catalog WHERE {where}", params)
    return envelope(rows, subject_scope="governance", context={**ctx, "total": total["cnt"] if total else 0})


@router.get("/tables")
def governance_tables(
    table_type: str = Query(None), migration: str = Query(None),
    q: str = Query(None), page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
):
    ctx = _gov_ctx()
    conditions = ["1=1"]
    params: list = []
    if q:
        conditions.append("table_name ILIKE %s")
        params.append(f"%{q}%")
    where = " AND ".join(conditions)
    offset = (page - 1) * size
    rows = fetchall(f"""
        SELECT * FROM rebuild4_meta.asset_table_catalog WHERE {where}
        ORDER BY schema_name, table_name LIMIT %s OFFSET %s
    """, (*params, size, offset))
    total = fetchone(f"SELECT COUNT(*) as cnt FROM rebuild4_meta.asset_table_catalog WHERE {where}", params)
    return envelope(rows, subject_scope="governance", context={**ctx, "total": total["cnt"] if total else 0})


@router.get("/usage/{table_name}")
def governance_usage(table_name: str = Path(...)):
    ctx = _gov_ctx()
    rows = fetchall("""
        SELECT * FROM rebuild4_meta.asset_usage_map WHERE source_table = %s
        ORDER BY target_capability
    """, (table_name,))
    if not rows:
        return JSONResponse(status_code=404, content=error_response(
            "resource_not_found", f"table_name={table_name} not found",
            f"/api/governance/usage/{table_name}", CONTRACT_VERSION))
    return envelope(rows, subject_scope="governance", context=ctx)


@router.get("/migration")
def governance_migration(
    decision: str = Query(None), page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
):
    ctx = _gov_ctx()
    conditions = ["1=1"]
    params: list = []
    if decision:
        conditions.append("decision = %s")
        params.append(decision)
    where = " AND ".join(conditions)
    offset = (page - 1) * size
    rows = fetchall(f"""
        SELECT * FROM rebuild4_meta.asset_migration_decision WHERE {where}
        ORDER BY source_table LIMIT %s OFFSET %s
    """, (*params, size, offset))
    total = fetchone(f"SELECT COUNT(*) as cnt FROM rebuild4_meta.asset_migration_decision WHERE {where}", params)
    return envelope(rows, subject_scope="governance", context={**ctx, "total": total["cnt"] if total else 0})


@router.get("/field_audit")
def governance_field_audit(
    decision: str = Query(None), q: str = Query(None),
    page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
):
    ctx = _gov_ctx()
    conditions = ["1=1"]
    params: list = []
    if decision:
        conditions.append("decision = %s")
        params.append(decision)
    if q:
        conditions.append("field_name ILIKE %s")
        params.append(f"%{q}%")
    where = " AND ".join(conditions)
    offset = (page - 1) * size
    rows = fetchall(f"""
        SELECT * FROM rebuild4_meta.field_audit_snapshot WHERE {where}
        ORDER BY field_name LIMIT %s OFFSET %s
    """, (*params, size, offset))
    return envelope(rows, subject_scope="governance", context=ctx)


@router.get("/target_fields")
def governance_target_fields(
    category: str = Query(None), source_type: str = Query(None),
    q: str = Query(None), page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
):
    ctx = _gov_ctx()
    conditions = ["1=1"]
    params: list = []
    if category:
        conditions.append("category = %s")
        params.append(category)
    if source_type:
        conditions.append("source_type = %s")
        params.append(source_type)
    if q:
        conditions.append("target_field ILIKE %s")
        params.append(f"%{q}%")
    where = " AND ".join(conditions)
    offset = (page - 1) * size
    rows = fetchall(f"""
        SELECT * FROM rebuild4_meta.target_field_snapshot WHERE {where}
        ORDER BY target_field LIMIT %s OFFSET %s
    """, (*params, size, offset))
    return envelope(rows, subject_scope="governance", context=ctx)


@router.get("/ods_rules")
def governance_ods_rules(
    is_active: str = Query(None), severity: str = Query(None),
    q: str = Query(None), page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
):
    ctx = _gov_ctx()
    conditions = ["1=1"]
    params: list = []
    if is_active is not None:
        conditions.append("is_active = %s")
        params.append(is_active == "true")
    if severity:
        conditions.append("severity = %s")
        params.append(severity)
    if q:
        conditions.append("rule_code ILIKE %s")
        params.append(f"%{q}%")
    where = " AND ".join(conditions)
    offset = (page - 1) * size
    rows = fetchall(f"""
        SELECT * FROM rebuild4_meta.ods_rule_snapshot WHERE {where}
        ORDER BY rule_code LIMIT %s OFFSET %s
    """, (*params, size, offset))
    return envelope(rows, subject_scope="governance", context=ctx)


@router.get("/ods_executions")
def governance_ods_executions(
    rule_code: str = Query(None), page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
):
    ctx = _gov_ctx()
    conditions = ["1=1"]
    params: list = []
    if rule_code:
        conditions.append("rule_code = %s")
        params.append(rule_code)
    where = " AND ".join(conditions)
    offset = (page - 1) * size
    rows = fetchall(f"""
        SELECT * FROM rebuild4_meta.ods_execution_snapshot WHERE {where}
        ORDER BY rule_code LIMIT %s OFFSET %s
    """, (*params, size, offset))
    return envelope(rows, subject_scope="governance", context=ctx)


@router.get("/parse_rules")
def governance_parse_rules(
    target_field: str = Query(None), is_active: str = Query(None),
    q: str = Query(None), page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
):
    ctx = _gov_ctx()
    conditions = ["1=1"]
    params: list = []
    if target_field:
        conditions.append("%s = ANY(target_fields)")
        params.append(target_field)
    if is_active is not None:
        conditions.append("is_active = %s")
        params.append(is_active == "true")
    if q:
        conditions.append("rule_code ILIKE %s")
        params.append(f"%{q}%")
    where = " AND ".join(conditions)
    offset = (page - 1) * size
    rows = fetchall(f"""
        SELECT rule_id, rule_code, source_field, target_fields, parse_logic,
               fail_action, severity, source_reference, seed_manifest_id, is_active
        FROM rebuild4_meta.parse_rule WHERE {where}
        ORDER BY rule_code LIMIT %s OFFSET %s
    """, (*params, size, offset))
    return envelope(rows, subject_scope="governance", context=ctx)


@router.get("/compliance_rules")
def governance_compliance_rules(
    target_field: str = Query(None), severity: str = Query(None),
    is_active: str = Query(None), q: str = Query(None),
    page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
):
    ctx = _gov_ctx()
    conditions = ["1=1"]
    params: list = []
    if target_field:
        conditions.append("target_field = %s")
        params.append(target_field)
    if severity:
        conditions.append("severity = %s")
        params.append(severity)
    if is_active is not None:
        conditions.append("is_active = %s")
        params.append(is_active == "true")
    if q:
        conditions.append("rule_code ILIKE %s")
        params.append(f"%{q}%")
    where = " AND ".join(conditions)
    offset = (page - 1) * size
    rows = fetchall(f"""
        SELECT rule_id, rule_code, source_field, target_field, check_field,
               check_condition, fail_action, severity, source_reference, seed_manifest_id, is_active
        FROM rebuild4_meta.compliance_rule WHERE {where}
        ORDER BY rule_code LIMIT %s OFFSET %s
    """, (*params, size, offset))
    return envelope(rows, subject_scope="governance", context=ctx)


@router.get("/trusted_loss")
def governance_trusted_loss(breakdown_type: str = Query("overview")):
    ctx = _gov_ctx()

    if breakdown_type == "overview":
        row = fetchone("""
            SELECT total_rows, trusted_rows, filtered_rows, filtered_pct,
                   filtered_with_rsrp, filtered_with_lon_lat
            FROM rebuild4_meta.trusted_loss_summary ORDER BY created_at DESC LIMIT 1
        """)
        return envelope(row or {}, subject_scope="governance", context=ctx)

    rows = fetchall("""
        SELECT breakdown_key, filtered_rows, filtered_pct
        FROM rebuild4_meta.trusted_loss_breakdown
        WHERE breakdown_type = %s
        ORDER BY filtered_rows DESC
    """, (breakdown_type,))
    return envelope(rows, subject_scope="governance", context=ctx)
