#!/bin/bash
# Step30 分片执行监控脚本

DB_CONN="postgres://postgres:123456@192.168.200.217:5432/ip_loc2?sslmode=disable"

echo "=== Step30 分片执行监控 ==="
echo "时间: $(date)"
echo ""

# 1. 活跃会话数量
echo "【活跃分片数量】"
psql "$DB_CONN" -c "SELECT COUNT(*) as active_shards FROM pg_stat_activity WHERE application_name LIKE 'codex_step30%';" -t

# 2. 运行时长
echo ""
echo "【各分片运行时长 (Top 5)】"
psql "$DB_CONN" -c "
SELECT 
    application_name,
    state,
    ROUND(EXTRACT(EPOCH FROM (now() - query_start))) as seconds,
    ROUND(EXTRACT(EPOCH FROM (now() - query_start)) / 60.0, 1) as minutes
FROM pg_stat_activity 
WHERE application_name LIKE 'codex_step30%' 
ORDER BY seconds DESC 
LIMIT 5;
"

# 3. 检查分片表是否已生成
echo ""
echo "【已完成的分片表】"
psql "$DB_CONN" -c "
SELECT 
    schemaname, 
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables 
WHERE tablename LIKE 'Y_codex_Layer3_Step30_Master_BS_Library__shard_%' 
ORDER BY tablename;
"

# 4. 系统负载
echo ""
echo "【数据库连接与负载】"
psql "$DB_CONN" -c "
SELECT 
    count(*) FILTER (WHERE state = 'active') as active_conns,
    count(*) FILTER (WHERE state = 'idle') as idle_conns,
    count(*) as total_conns
FROM pg_stat_activity;
"

echo ""
echo "=== 监控完成 ==="
