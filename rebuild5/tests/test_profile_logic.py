from rebuild5.backend.app.profile.logic import classify_cell_state, classify_diff_kind


def test_classify_cell_state_waiting_when_obs_or_devs_insufficient() -> None:
    assert classify_cell_state(
        independent_obs=2,
        distinct_dev_id=2,
        p90_radius_m=120.0,
        observed_span_hours=36.0,
        is_collision_id=False,
        params={
            'waiting_min_obs': 3,
            'waiting_min_devs': 2,
            'qualified_min_obs': 3,
            'qualified_min_devs': 2,
            'qualified_max_p90': 1500,
            'qualified_min_span_hours': 24,
            'excellent_min_obs': 8,
            'excellent_min_devs': 3,
            'excellent_max_p90': 500,
            'excellent_min_span_hours': 24,
        },
    ) == 'waiting'


def test_classify_cell_state_observing_when_waiting_cleared_but_qualified_not_met() -> None:
    assert classify_cell_state(
        independent_obs=4,
        distinct_dev_id=2,
        p90_radius_m=1700.0,
        observed_span_hours=36.0,
        is_collision_id=False,
        params={
            'waiting_min_obs': 3,
            'waiting_min_devs': 2,
            'qualified_min_obs': 3,
            'qualified_min_devs': 2,
            'qualified_max_p90': 1500,
            'qualified_min_span_hours': 24,
            'excellent_min_obs': 8,
            'excellent_min_devs': 3,
            'excellent_max_p90': 500,
            'excellent_min_span_hours': 24,
        },
    ) == 'observing'


def test_classify_cell_state_qualified_when_all_qualified_thresholds_met() -> None:
    assert classify_cell_state(
        independent_obs=5,
        distinct_dev_id=2,
        p90_radius_m=640.0,
        observed_span_hours=30.0,
        is_collision_id=False,
        params={
            'waiting_min_obs': 3,
            'waiting_min_devs': 2,
            'qualified_min_obs': 3,
            'qualified_min_devs': 2,
            'qualified_max_p90': 1500,
            'qualified_min_span_hours': 24,
            'excellent_min_obs': 8,
            'excellent_min_devs': 3,
            'excellent_max_p90': 500,
            'excellent_min_span_hours': 24,
        },
    ) == 'qualified'


def test_classify_cell_state_excellent_when_all_excellent_thresholds_met() -> None:
    assert classify_cell_state(
        independent_obs=12,
        distinct_dev_id=4,
        p90_radius_m=280.0,
        observed_span_hours=60.0,
        is_collision_id=False,
        params={
            'waiting_min_obs': 3,
            'waiting_min_devs': 2,
            'qualified_min_obs': 3,
            'qualified_min_devs': 2,
            'qualified_max_p90': 1500,
            'qualified_min_span_hours': 24,
            'excellent_min_obs': 8,
            'excellent_min_devs': 3,
            'excellent_max_p90': 500,
            'excellent_min_span_hours': 24,
        },
    ) == 'excellent'


def test_classify_cell_state_collision_blocks_qualified() -> None:
    assert classify_cell_state(
        independent_obs=8,
        distinct_dev_id=3,
        p90_radius_m=300.0,
        observed_span_hours=60.0,
        is_collision_id=True,
        params={
            'waiting_min_obs': 3,
            'waiting_min_devs': 2,
            'qualified_min_obs': 3,
            'qualified_min_devs': 2,
            'qualified_max_p90': 1500,
            'qualified_min_span_hours': 24,
            'excellent_min_obs': 8,
            'excellent_min_devs': 3,
            'excellent_max_p90': 500,
            'excellent_min_span_hours': 24,
        },
    ) == 'observing'


def test_classify_diff_kind_returns_new_for_first_snapshot() -> None:
    assert classify_diff_kind(previous=None, current={'lifecycle_state': 'waiting'}) == 'new'


def test_classify_diff_kind_returns_promoted_for_state_upgrade() -> None:
    assert classify_diff_kind(
        previous={'lifecycle_state': 'observing', 'anchor_eligible': False, 'center_lon': 116.1, 'center_lat': 39.9},
        current={'lifecycle_state': 'qualified', 'anchor_eligible': False, 'center_lon': 116.1, 'center_lat': 39.9},
    ) == 'promoted'


def test_classify_diff_kind_returns_eligibility_changed_without_state_change() -> None:
    assert classify_diff_kind(
        previous={'lifecycle_state': 'qualified', 'anchor_eligible': False, 'center_lon': 116.1, 'center_lat': 39.9},
        current={'lifecycle_state': 'qualified', 'anchor_eligible': True, 'center_lon': 116.1, 'center_lat': 39.9},
    ) == 'eligibility_changed'
