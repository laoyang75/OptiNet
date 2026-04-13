from rebuild5.backend.app.profile.logic import classify_cell_state, classify_diff_kind


def _params() -> dict[str, float]:
    return {
        'waiting_min_obs': 1,
        'qualified_min_obs': 10,
        'excellent_min_obs': 30,
    }


def test_classify_cell_state_waiting_when_no_observation() -> None:
    assert classify_cell_state(
        independent_obs=0,
        distinct_dev_id=0,
        p90_radius_m=None,
        observed_span_hours=None,
        is_collision_id=False,
        params=_params(),
    ) == 'waiting'


def test_classify_cell_state_observing_when_observation_not_enough_for_qualified() -> None:
    assert classify_cell_state(
        independent_obs=4,
        distinct_dev_id=1,
        p90_radius_m=1700.0,
        observed_span_hours=1.0,
        is_collision_id=False,
        params=_params(),
    ) == 'observing'


def test_classify_cell_state_qualified_depends_only_on_observation_count() -> None:
    assert classify_cell_state(
        independent_obs=12,
        distinct_dev_id=1,
        p90_radius_m=99999.0,
        observed_span_hours=0.5,
        is_collision_id=False,
        params=_params(),
    ) == 'qualified'


def test_classify_cell_state_excellent_depends_only_on_observation_count() -> None:
    assert classify_cell_state(
        independent_obs=32,
        distinct_dev_id=1,
        p90_radius_m=99999.0,
        observed_span_hours=0.5,
        is_collision_id=False,
        params=_params(),
    ) == 'excellent'


def test_classify_cell_state_collision_no_longer_blocks_lifecycle() -> None:
    assert classify_cell_state(
        independent_obs=32,
        distinct_dev_id=1,
        p90_radius_m=99999.0,
        observed_span_hours=0.5,
        is_collision_id=True,
        params=_params(),
    ) == 'excellent'


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
