"""兼容 facade：保持 `from app.services.workbench import xxx` 正常工作。

所有公开函数从子模块重新导出，现有 router 无需任何改动。
"""

# catalog
from app.services.workbench.catalog import (
    build_run_summary,
    ensure_field_registry,
    ensure_reference_data,
    get_version_context,
    get_version_change_log,
    get_version_history,
    latest_completed_run_id,
    latest_run_id,
    previous_completed_run_id,
    resolve_run_parameters,
)

# snapshots
from app.services.workbench.snapshots import (
    ensure_snapshot_bundle,
    list_anomaly_summary,
    list_gps_status_distribution,
    list_layer_snapshot,
    list_operator_tech_distribution,
    list_signal_fill_distribution,
    list_step_summary,
    refresh_all,
)

# steps
from app.services.workbench.steps import (
    get_step_diff,
    get_step_metrics,
    get_step_object_diff,
    get_step_parameter_diff,
    get_step_rules,
    get_step_sql,
)

# fields
from app.services.workbench.fields import get_field_detail, list_fields
from app.services.workbench.source_fields import (
    compile_compliance_sql,
    get_source_field_detail,
    list_source_field_trend,
    list_source_fields,
    refresh_source_field_snapshots,
)

# samples
from app.services.workbench.samples import (
    get_sample_object_detail,
    get_sample_set_detail,
    get_step_samples,
    list_sample_sets,
)

__all__ = [
    # catalog
    "build_run_summary",
    "ensure_field_registry",
    "ensure_reference_data",
    "get_version_context",
    "get_version_change_log",
    "get_version_history",
    "latest_completed_run_id",
    "latest_run_id",
    "previous_completed_run_id",
    "resolve_run_parameters",
    # snapshots
    "ensure_snapshot_bundle",
    "list_anomaly_summary",
    "list_gps_status_distribution",
    "list_layer_snapshot",
    "list_operator_tech_distribution",
    "list_signal_fill_distribution",
    "list_step_summary",
    "refresh_all",
    # steps
    "get_step_diff",
    "get_step_metrics",
    "get_step_object_diff",
    "get_step_parameter_diff",
    "get_step_rules",
    "get_step_sql",
    # fields
    "compile_compliance_sql",
    "get_field_detail",
    "get_source_field_detail",
    "list_fields",
    "list_source_field_trend",
    "list_source_fields",
    "refresh_source_field_snapshots",
    # samples
    "get_sample_object_detail",
    "get_sample_set_detail",
    "get_step_samples",
    "list_sample_sets",
]
