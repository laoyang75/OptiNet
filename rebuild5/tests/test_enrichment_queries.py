from rebuild5.backend.app.enrichment import queries as enrichment_queries


def test_get_enrichment_anomalies_payload_scopes_to_latest_batch(monkeypatch) -> None:
    calls = []

    def fake_fetchone(sql, params=None):
        calls.append((sql, params))
        if 'MAX(batch_id)' in sql:
            return {'batch_id': 7}
        return None

    def fake_paginate(sql, params=None, page=1, page_size=50):
        calls.append((sql, params))
        assert params == (7,)
        return {
            'items': [{'record_id': 'r1'}],
            'page': page,
            'page_size': page_size,
            'total_count': 1,
            'total_pages': 1,
        }

    monkeypatch.setattr(enrichment_queries, '_safe_fetchone', fake_fetchone)
    monkeypatch.setattr(enrichment_queries, 'paginate', fake_paginate)

    payload = enrichment_queries.get_enrichment_anomalies_payload(page=1, page_size=6)

    assert payload['items'] == [{'record_id': 'r1'}]
    anomaly_sql = next(
        sql for sql, _ in calls
        if 'FROM rebuild5.gps_anomaly_log' in sql and 'WHERE batch_id = %s' in sql
    )
    assert 'WHERE batch_id = %s' in anomaly_sql
