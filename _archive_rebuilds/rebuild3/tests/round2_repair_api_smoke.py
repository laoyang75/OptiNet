from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from typing import Any

BASE_URL = os.environ.get('REBUILD3_API_BASE', 'http://127.0.0.1:47121')


def get_json(path: str, query: dict[str, Any] | None = None) -> Any:
    url = f"{BASE_URL}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    with urllib.request.urlopen(url) as response:
        return json.load(response)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    flow_snapshot = get_json('/api/v1/runs/flow-snapshots')
    expect(flow_snapshot['data_origin'] in {'real', 'synthetic'}, 'flow-snapshots should expose either real data or an explicit synthetic evaluation mode')
    expect(flow_snapshot['run_options'], 'flow-snapshots should expose selectable run data for validation')
    expect(flow_snapshot['columns'][0]['available'], 'flow-snapshots should always include an init column once data is available')
    expect(flow_snapshot['groups'], 'flow-snapshots should return stage groups once evaluation data is available')
    if flow_snapshot['data_origin'] == 'synthetic':
        expect('评估' in flow_snapshot['subject_note'], 'synthetic flow-snapshots should declare evaluation mode')

    flow_overview = get_json('/api/v1/runs/flow-overview')
    expect(flow_overview['data_origin'] in {'real', 'synthetic'}, 'flow-overview should expose either real data or an explicit synthetic evaluation mode')
    expect(not flow_overview['empty_state'], 'flow-overview should expose data for validation')
    expect(flow_overview['batch_id'], 'flow-overview should point to a concrete batch id')
    expect(flow_overview['flow'], 'flow-overview should expose routing data')
    expect(flow_overview['compare_callout'] is not None, 'flow-overview should expose a compare callout once data is available')
    if flow_overview['data_origin'] == 'synthetic':
        expect('评估' in flow_overview['subject_note'], 'synthetic flow-overview should declare evaluation mode')

    batches = get_json('/api/v1/runs/batches')
    rows = batches.get('rows') or []
    expect(rows, 'runs/batches should list rebuild3_meta runs instead of sample/full pseudo rows')
    expect(all('RUN-SAMPLE' not in row['run_id'] for row in rows), 'runs/batches should not surface sample validation as the main run list')
    expect(all(row['data_origin'] in {'real', 'synthetic', 'fallback'} for row in rows), 'runs/batches rows should carry the unified origin contract')

    baseline = get_json('/api/v1/runs/baseline-profile')
    expect(baseline['data_origin'] == 'real', 'baseline-profile should answer with the formal baseline subject')
    expect(baseline['current_version']['baseline_version'] == 'BASELINE-FULL-V1', 'baseline-profile should point at the current real baseline version')
    expect(baseline['previous_version'] is None, 'baseline-profile should not fabricate a previous version from rebuild2')
    expect(baseline['diff_notice'] == '暂无上一版 baseline，无法比较版本差异。', 'baseline-profile should state that no previous version exists')

    initialization = get_json('/api/v1/runs/initialization')
    expect(initialization['run_id'] == 'RUN-FULL-20251201-20251207-V1', 'initialization should expose the real full initialization run id')
    expect(initialization['data_origin'] == 'synthetic', 'initialization snapshot summary should be marked synthetic when it is estimated')
    expect('RUN-SAMPLE' not in initialization['run_id'], 'initialization should not point to the sample run')

    compare = get_json('/api/v1/compare/overview')
    expect(compare['data_origin'] == 'fallback', 'compare overview should be marked fallback')
    expect(compare['subject_note'] == '当前为 fallback 对照结果，仅供参考，不代表实时比对结果', 'compare overview should expose the fallback warning')

    governance = get_json('/api/v1/governance/overview')
    expect(governance['data_origin'] == 'fallback', 'governance overview should be marked fallback')
    expect(governance['subject_note'] == '当前为 fallback 资产目录，仅供梳理，不代表已接入实时元数据注册表', 'governance overview should expose the fallback warning')

    lac = get_json('/api/v1/objects/profile-list', {'object_type': 'lac', 'page': 1, 'page_size': 10})
    lac_row = (lac['rows'] or [None])[0]
    expect(lac_row is not None, 'lac profile list should return rows')
    expect(lac_row['region_quality_label'] in {'存在问题', '覆盖不足'}, 'lac profile list should map technical quality codes to Chinese labels')
    expect(lac_row['region_quality_label'] != lac_row['region_quality_code'], 'lac profile list should not expose the raw code as the display label')

    bs = get_json('/api/v1/objects/profile-list', {'object_type': 'bs', 'page': 1, 'page_size': 10})
    bs_row = (bs['rows'] or [None])[0]
    expect(bs_row is not None, 'bs profile list should return rows')
    expect('gps_quality_reference' in bs_row, 'bs profile list should expose GPS quality as a reference field')
    expect('signal_confidence' not in bs_row, 'bs profile list should not fabricate signal_confidence')

    cell = get_json('/api/v1/objects/profile-list', {'object_type': 'cell', 'page': 1, 'page_size': 10})
    cell_row = (cell['rows'] or [None])[0]
    expect(cell_row is not None, 'cell profile list should return rows')
    expect('bs_gps_quality_reference' in cell_row, 'cell profile list should rename BS-side GPS quality explicitly')
    expect('gps_quality' not in cell_row, 'cell profile list should not expose BS-side GPS quality as a cell field')
    expect('coordinate_source_note' in cell_row, 'cell profile list should explain the coordinate source contract')
    expect('profile_center_lon' in cell_row and 'profile_center_lat' in cell_row, 'cell profile list should keep profile coordinates as explicit reference fields')

    print('round2 repair api smoke: ok')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f'round2 repair api smoke: FAILED: {exc}', file=sys.stderr)
        raise SystemExit(1)
