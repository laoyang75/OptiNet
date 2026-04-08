CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_l0_gps_cellid ON rebuild2.l0_gps ("CellID") WHERE "CellID" IS NOT NULL;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_l0_gps_lac ON rebuild2.l0_gps ("LAC") WHERE "LAC" IS NOT NULL;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_l0_gps_operator_tech ON rebuild2.l0_gps ("运营商编码", "标准制式") WHERE "运营商编码" IS NOT NULL;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_l0_gps_bsid ON rebuild2.l0_gps ("基站ID") WHERE "基站ID" IS NOT NULL;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_l0_gps_record ON rebuild2.l0_gps ("原始记录ID");
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_l0_gps_ts ON rebuild2.l0_gps ("上报时间") WHERE "上报时间" IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_l0_lac_cellid ON rebuild2.l0_lac ("CellID") WHERE "CellID" IS NOT NULL;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_l0_lac_lac ON rebuild2.l0_lac ("LAC") WHERE "LAC" IS NOT NULL;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_l0_lac_operator_tech ON rebuild2.l0_lac ("运营商编码", "标准制式") WHERE "运营商编码" IS NOT NULL;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_l0_lac_bsid ON rebuild2.l0_lac ("基站ID") WHERE "基站ID" IS NOT NULL;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_l0_lac_record ON rebuild2.l0_lac ("原始记录ID");
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_l0_lac_ts ON rebuild2.l0_lac ("上报时间") WHERE "上报时间" IS NOT NULL;
