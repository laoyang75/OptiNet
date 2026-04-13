from rebuild5.backend.app.service_query import queries as service_queries


def test_get_service_cell_payload_uses_context_filters(monkeypatch) -> None:
    calls = []

    def fake_fetchone(sql, params=None):
        calls.append((sql, params))
        return {'cell_id': 1001, 'operator_code': '46000', 'lac': 123, 'tech_norm': '5G'}

    monkeypatch.setattr(service_queries, '_safe_fetchone', fake_fetchone)

    payload = service_queries.get_service_cell_payload(
        1001,
        operator_code='46000',
        lac=123,
        tech_norm='5G',
    )

    assert payload['cell_id'] == 1001
    sql, params = calls[0]
    assert 'operator_code = %s' in sql
    assert 'lac = %s' in sql
    assert 'tech_norm IS NOT DISTINCT FROM %s' in sql
    assert params == (1001, '46000', 123, '5G')
