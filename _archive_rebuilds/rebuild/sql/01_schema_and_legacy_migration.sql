-- ============================================================================
-- 01_schema_and_legacy_migration.sql
-- Schema creation + Y_codex legacy table migration + junk table cleanup
-- Idempotent: safe to run multiple times
-- Generated: 2026-03-24
-- ============================================================================

BEGIN;

-- ============================================================================
-- PART 1: Create schemas
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS legacy;
CREATE SCHEMA IF NOT EXISTS pipeline;
CREATE SCHEMA IF NOT EXISTS workbench;
CREATE SCHEMA IF NOT EXISTS meta;

-- Set default search path
ALTER DATABASE ip_loc2 SET search_path TO pipeline, workbench, meta, legacy, public;

-- ============================================================================
-- PART 2: Move 28 Y_codex tables from public to legacy schema
-- Uses DO block to skip tables that have already been moved
-- ============================================================================
DO $$
DECLARE
    _tbl text;
BEGIN
    FOREACH _tbl IN ARRAY ARRAY[
        -- Layer 0 (2)
        'Y_codex_Layer0_Lac',
        'Y_codex_Layer0_Gps_base',
        -- Layer 2 (8)
        'Y_codex_Layer2_Step01_BaseStats_Raw',
        'Y_codex_Layer2_Step01_BaseStats_ValidCell',
        'Y_codex_Layer2_Step02_Compliance_Diff',
        'Y_codex_Layer2_Step03_Lac_Stats_DB',
        'Y_codex_Layer2_Step04_Master_Lac_Lib',
        'Y_codex_Layer2_Step05_CellId_Stats_DB',
        'Y_codex_Layer2_Step06_L0_Lac_Filtered',
        'Y_codex_Layer2_Step06_GpsVsLac_Compare',
        -- Layer 3 (13)
        'Y_codex_Layer3_Step30_Master_BS_Library',
        'Y_codex_Layer3_Step30_Gps_Level_Stats',
        'Y_codex_Layer3_Step31_Cell_Gps_Fixed',
        'Y_codex_Layer3_Step32_Compare',
        'Y_codex_Layer3_Step33_Signal_Fill_Simple',
        'Y_codex_Layer3_Step34_Signal_Compare',
        'Y_codex_Layer3_Step35_28D_Dynamic_Cell_Profile',
        'Y_codex_Layer3_Step36_BS_Id_Anomaly_Marked',
        'Y_codex_Layer3_Step37_Collision_Data_Insufficient_BS',
        'Y_codex_Layer3_BS_Profile',
        'Y_codex_Layer3_Final_BS_Profile',
        'Y_codex_Layer3_Final_Cell_BS_Map',
        'Y_codex_Layer3_Cell_BS_Map',
        -- Layer 4 (2)
        'Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill',
        'Y_codex_Layer4_Final_Cell_Library',
        -- Layer 5 (3)
        'Y_codex_Layer5_Lac_Profile',
        'Y_codex_Layer5_BS_Profile',
        'Y_codex_Layer5_Cell_Profile'
    ]
    LOOP
        -- Only move if the table still exists in public schema
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = _tbl
        ) THEN
            EXECUTE format('ALTER TABLE public.%I SET SCHEMA legacy', _tbl);
            RAISE NOTICE 'Moved public.% -> legacy.%', _tbl, _tbl;
        ELSE
            RAISE NOTICE 'Skipped % (not in public schema)', _tbl;
        END IF;
    END LOOP;
END
$$;

-- ============================================================================
-- PART 3: Drop 29 junk tables (SMOKE, obs, empty metrics, temp debug)
-- ============================================================================
DO $$
DECLARE
    _tbl text;
BEGIN
    FOREACH _tbl IN ARRAY ARRAY[
        -- SMOKE test tables (9)
        'Y_codex_Layer2_Step02_Gps_Compliance_Marked__L3_SMOKE',
        'Y_codex_Layer2_Step06_L0_Lac_Filtered__L3_SMOKE',
        'Y_codex_Layer4_Final_Cell_Library__MCP_SMOKE',
        'Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill__MCP_SMOKE',
        'Y_codex_Layer4_Step40_Gps_Metrics__MCP_SMOKE',
        'Y_codex_Layer4_Step41_Signal_Metrics__MCP_SMOKE',
        'Y_codex_Layer4_Step42_Compare_Summary__MCP_SMOKE',
        'Y_codex_Layer5_Smoke_BS_Profile',
        'Y_codex_Layer5_Smoke_Cell_Profile',
        -- obs observability tables (10)
        'Y_codex_obs_patch_log',
        'Y_codex_obs_issue_log',
        'Y_codex_obs_rule_hit',
        'Y_codex_obs_quality_metric',
        'Y_codex_obs_anomaly_stats',
        'Y_codex_obs_reconciliation',
        'Y_codex_obs_exposure_matrix',
        'Y_codex_obs_gate_result',
        'Y_codex_obs_layer_snapshot',
        'Y_codex_obs_run_registry',
        -- Empty metrics / temp debug tables (10)
        'Y_codex_Layer4_Step40_Gps_Metrics',
        'Y_codex_Layer4_Step41_Signal_Metrics',
        'Y_codex_Layer4_Step40_Gps_Metrics_All',
        'Y_codex_Layer4_Step41_Signal_Metrics_All',
        'Y_codex_Layer4_Step42_Compare_Summary',
        'Y_codex_Layer4_Step44_BsId_Lt_256_Summary',
        'Y_codex_Layer4_Step44_BsId_Lt_256_Detail',
        'Y_codex_Layer3_Step32_Compare_Raw',
        'Y_codex_Layer3_Step34_Signal_Compare_Raw',
        'WY_codex_Layer2_Step04_Master_Lac_Lib_mid_20260309'
    ]
    LOOP
        -- Try public first, then legacy (in case a previous partial run moved some)
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = _tbl
        ) THEN
            EXECUTE format('DROP TABLE public.%I CASCADE', _tbl);
            RAISE NOTICE 'Dropped public.%', _tbl;
        ELSIF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'legacy' AND table_name = _tbl
        ) THEN
            EXECUTE format('DROP TABLE legacy.%I CASCADE', _tbl);
            RAISE NOTICE 'Dropped legacy.%', _tbl;
        ELSE
            RAISE NOTICE 'Skipped % (not found)', _tbl;
        END IF;
    END LOOP;
END
$$;

COMMIT;

-- ============================================================================
-- Verification
-- ============================================================================
DO $$
DECLARE
    _cnt_legacy  integer;
    _cnt_pipeline integer;
BEGIN
    SELECT count(*) INTO _cnt_legacy
    FROM information_schema.tables WHERE table_schema = 'legacy';

    SELECT count(*) INTO _cnt_pipeline
    FROM information_schema.tables WHERE table_schema = 'pipeline';

    RAISE NOTICE '== Migration Summary ==';
    RAISE NOTICE 'legacy  schema tables: %', _cnt_legacy;
    RAISE NOTICE 'pipeline schema tables: %', _cnt_pipeline;
END
$$;
