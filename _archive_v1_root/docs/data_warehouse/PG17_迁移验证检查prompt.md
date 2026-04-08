# PG17 数据迁移验证 Prompt

## 使用说明
把以下内容直接作为下一次对话的第一条消息，不需要额外补充。

---

## Prompt 内容

你好，我上次做了一个 PG15 → PG17 的数据迁移任务，现在需要你帮我验证结果并处理未完成的工作。

**背景**：
- PG15（生产库）：`192.168.200.217:5432`，库名 `ip_loc2`
- PG17（新库）：`192.168.200.217:5433`，库名 `ip_loc2`
- 根用户：`root`，密码 `111111`
- pg 密码：`123456`
- 应该迁移的表：前缀为 `Y_codex_` 和 `WY_codex_` 的所有表，共 57 张

**请你做以下事情：**

1. **检查服务器上的修复脚本是否还在运行**：
   - SSH 到服务器，运行 `ps aux | grep auto_fix_migration | grep -v grep`
   - 查看日志：`tail -30 /data/auto_fix_migration.log`
   - 查看修复进度是否已完成

2. **通过 MCP 对比两库实际行数**（用 DBHub=PG15，PG17=PG17）：
   - 分别查询两库所有 `Y_codex_*` 和 `WY_codex_*` 表的 `COUNT(*)`
   - 找出行数不一致的表（注意：空的 obs 统计表两边都是 0，属正常）

3. **如果还有未完成的表**：
   - 在服务器上重新运行 `/data/auto_fix_migration.sh`（它会自动跳过已一致的表，只补迁缺失的）
   - 命令：`sshpass -p '111111' ssh root@192.168.200.217 'nohup /data/auto_fix_migration.sh > /data/auto_fix_migration.log 2>&1 &'`

4. **全部一致后输出最终报告**：给我一张汇总表，确认 57/57 张表全部同步完成。

**注意**：两库都在同一台服务器，`auto_fix_migration.sh` 脚本已放在 `/data/` 目录下，可直接运行。
