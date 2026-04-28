# fix6_optim / 02B 重构报告

## 0. TL;DR + 对 02A 的修订

- 新增 `rebuild5/backend/app/core/citus_compat.py`(44 行)。
- 迁移 caller:6 个生产调用点 + 1 个 CTAS split params-DML 分支。
- 删除旧 helper:`publish_bs_lac._execute_with_session_settings`。
- 对 02A 报告全部采纳,无修订。实施时额外将 `publish_bs_centroid_detail` 的参数化 `WITH ... INSERT INTO rb5.bs_centroid_detail` 一并迁入统一入口,与本阶段 commit body 的 "publish_bs centroid" 范围一致。
- commit SHA:本报告随 02B commit 提交;最终 SHA 以 `git rev-parse HEAD` / 完工话术为准。
- push 状态:待本报告写入后执行 `git push origin main`。

## 1. core/citus_compat.py 设计

签名:

```python
def execute_distributed_insert(
    sql: str,
    *,
    params: tuple[Any, ...] | None = None,
    session_setup_sqls: list[str] | None = None,
) -> None:
```

实现:
- 使用 `psycopg.ClientCursor`。
- `params` 存在时执行 `cur.execute(cur.mogrify(sql, params))`,强制 client-side inline。
- `session_setup_sqls` 顺序执行,结束后逆序 `RESET` 形如 `SET ...` 的 session 设置。
- 只服务 Citus 高风险 DML / `INSERT...SELECT`,不替代普通 `fetchone` / `fetchall` / 元数据函数调用。

与 02A §2.2 草案差异:
- 未加入草案中的 `reset_session` 扩展参数,按 02B prompt §5.1 要求保持最小签名。

## 2. Caller 迁移逐项

| caller | 原 helper | 现入口 | 备注 |
| --- | --- | --- | --- |
| `publish_bs_lac.publish_cell_centroid_detail` | `_execute_with_session_settings` | `execute_distributed_insert` | `session_setup_sqls=['SET enable_nestloop = off']` 透传 |
| `publish_bs_lac.publish_bs_library` | `_execute_with_session_settings` | `execute_distributed_insert` | fix5 D hotfix 路径抽到统一入口 |
| `publish_bs_lac.publish_bs_centroid_detail` | `core.database.execute` | `execute_distributed_insert` | 参数化 `WITH ... INSERT INTO rb5.bs_centroid_detail` |
| `publish_bs_lac.publish_lac_library` | `core.database.execute` | `execute_distributed_insert` | 参数化 `WITH ... INSERT INTO rb5.trusted_lac_library` |
| `publish_cell.publish_cell_library` | `core.database.execute` | `execute_distributed_insert` | 参数化 `WITH merged AS ... INSERT INTO rb5.trusted_cell_library` |
| `profile.pipeline.persist_candidate_seed_history` | `core.database.execute` | `execute_distributed_insert` | 参数化 `INSERT INTO rb5.candidate_seed_history ... SELECT` |
| `enrichment.pipeline._insert_snapshot_seed_records` | `core.database.execute` | `execute_distributed_insert` | 参数化 `INSERT INTO rb5.snapshot_seed_records ... SELECT` |
| `core.database` CTAS split params 分支 | default cursor `cur.execute` | `execute_distributed_insert` | 函数体内 local import 防循环 |

Diff 节选:

```diff
-from psycopg import ClientCursor
-from ..core.database import execute, get_conn
+from ..core.citus_compat import execute_distributed_insert
+from ..core.database import execute
```

```diff
-    _execute_with_session_settings(
+    execute_distributed_insert(
         session_setup_sqls=['SET enable_nestloop = off'],
         sql=f"""
```

```diff
-    execute(
+    execute_distributed_insert(
         f"""
         INSERT INTO rb5.trusted_cell_library (
...
-        (
+        params=(
```

```diff
-    execute(
+    execute_distributed_insert(
         f"""
         INSERT INTO rb5.candidate_seed_history (
...
-        (batch_id, run_id, DATASET_KEY, run_id),
+        params=(batch_id, run_id, DATASET_KEY, run_id),
```

```diff
-    cur.execute(f"INSERT INTO {relation} {select_sql}", params)
+    insert_sql = f"INSERT INTO {relation} {select_sql}"
+    if params:
+        from .citus_compat import execute_distributed_insert
+        execute_distributed_insert(insert_sql, params=params)
+    else:
+        cur.execute(insert_sql)
```

## 3. 静态验证结果

语法检查:

```text
python3 -m py_compile rebuild5/backend/app/core/citus_compat.py rebuild5/backend/app/maintenance/publish_bs_lac.py rebuild5/backend/app/maintenance/publish_cell.py rebuild5/backend/app/profile/pipeline.py rebuild5/backend/app/enrichment/pipeline.py rebuild5/backend/app/core/database.py
# exit 0, no output
```

grep 守护:

```text
grep -n "execute([^)]*params" rebuild5/backend/app/maintenance/publish_bs_lac.py
# no output
grep -n "execute([^)]*params" rebuild5/backend/app/maintenance/publish_cell.py
# no output
grep -n "execute([^)]*params" rebuild5/backend/app/profile/pipeline.py | grep -v "execute_distributed_insert"
# no output
grep -n "execute([^)]*params" rebuild5/backend/app/enrichment/pipeline.py | grep -v "execute_distributed_insert"
# no output
grep -rn "_execute_with_session_settings" rebuild5/backend
# no output
```

接口守护:

```text
grep -n "def execute_distributed_insert" rebuild5/backend/app/core/citus_compat.py
19:def execute_distributed_insert(
```

## 4. 已知限制 / 未做

- session 管理统一入口(02A §5 应做 #3):未做。本阶段只对必要 caller 透传 `session_setup_sqls`,未重构所有 session SET。
- relation_exists 下沉(02A §5 应做 #2):未做。它是耦合整理,不属于 Citus parameterized DML 兼容范围。
- `label_engine.py` / `etl/fill.py ctid::text` / research and benchmark scripts:未做,按 02B prompt §5.3 保持 P2 / 非生产 surface 不动。
- 动态行为差异(连接池 / 事务边界 / autocommit):本阶段未连接数据库实测,留给 02C 测试 + 03 pipelined 验证。

## 5. 给 02C 的输入

- 静态 regression 可以以 `execute_distributed_insert` 为唯一允许入口,守护生产高风险参数化 `INSERT...SELECT` 不再走 `core.database.execute(..., params)`。
- smoke/unit 应 monkeypatch `psycopg.ClientCursor`,断言 params 分支调用 `mogrify`。
- CTAS split helper 的 params-DML 分支需要覆盖:输入 `CREATE ... TABLE ... AS SELECT ... %s`,断言 split 后 INSERT 分支走统一入口且 `database.py` 无顶层反向 import。
