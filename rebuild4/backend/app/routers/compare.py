"""API-12: validation/compare."""
from fastapi import APIRouter, Query
from ..core.database import fetchall, fetchone
from ..core.envelope import envelope
from ..core.context import base_context, CONTRACT_VERSION

router = APIRouter(prefix="/api", tags=["compare"])


@router.get("/validation/compare")
def validation_compare(
    run_a: str = Query(None),
    run_b: str = Query(None),
):
    ctx = base_context()
    if run_a:
        ctx["run_a"] = run_a
    if run_b:
        ctx["run_b"] = run_b

    if not run_a or not run_b:
        return envelope(
            None,
            data_origin="fallback",
            subject_scope="compare",
            subject_note="不足两次可比运行，无法执行对照验证",
            context=ctx,
        )

    # check both runs exist
    ra = fetchone("SELECT run_id, run_type, status FROM rebuild4_meta.run WHERE run_id = %s", (run_a,))
    rb = fetchone("SELECT run_id, run_type, status FROM rebuild4_meta.run WHERE run_id = %s", (run_b,))

    if not ra or not rb:
        return envelope(
            None,
            data_origin="fallback",
            subject_scope="compare",
            subject_note="不足两次可比运行，无法执行对照验证",
            context=ctx,
        )

    # check for compare results
    job = fetchone("""
        SELECT * FROM rebuild4_meta.compare_job
        WHERE run_a = %s AND run_b = %s
        ORDER BY created_at DESC LIMIT 1
    """, (run_a, run_b))

    if not job:
        return envelope(
            None,
            data_origin="fallback",
            subject_scope="compare",
            subject_note="暂无对照验证结果",
            context=ctx,
        )

    results = fetchall("""
        SELECT compare_scope, metric_group, metric_name,
               value_a, value_b, diff_value, diff_ratio,
               severity, is_blocking, explanation
        FROM rebuild4_meta.compare_result
        WHERE compare_job_id = %s
        ORDER BY severity, metric_group, metric_name
    """, (job["compare_job_id"],))

    return envelope({
        "job": job,
        "results": results,
        "run_a": ra,
        "run_b": rb,
    }, data_origin="real", subject_scope="compare", context=ctx)
