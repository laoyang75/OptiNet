-- Layer_4 Step99（可选）：DB COMMENT（可读性闭环）
--
-- 说明：本层 COMMENT 不是 Gate-0 硬阻断，但建议与 Layer_3 保持同样格式（CN/EN）。

SET statement_timeout = 0;

DO $$
BEGIN
  IF to_regclass('public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill"') IS NOT NULL THEN
    EXECUTE $c$
      COMMENT ON TABLE public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill" IS
      'CN: Layer_4 Step40 产物=对 Layer0 明细做 GPS 过滤与按 BS 回填后的明细表（城市阈值 + 严重碰撞止损）；EN: Layer_4 Step40 output=GPS filtered and BS-filled detail table derived from Layer0.';
    $c$;
  END IF;

  IF to_regclass('public."Y_codex_Layer4_Final_Cell_Library"') IS NOT NULL THEN
    EXECUTE $c$
      COMMENT ON TABLE public."Y_codex_Layer4_Final_Cell_Library" IS
      'CN: Layer_4 最终 cell_id 明细库=在 Step40 基础上完成信号二阶段补齐后的明细表；EN: Layer_4 final cell detail library after signal filling.';
    $c$;
  END IF;

  IF to_regclass('public."Y_codex_Layer4_Step42_Compare_Summary"') IS NOT NULL THEN
    EXECUTE $c$
      COMMENT ON TABLE public."Y_codex_Layer4_Step42_Compare_Summary" IS
      'CN: Layer_4 对比汇总=原始库 vs 最终库在条数/GPS/信号方面的对比统计；EN: Layer_4 comparison summary between raw and final datasets.';
    $c$;
  END IF;

  IF to_regclass('public."Y_codex_Layer4_Step40_Gps_Metrics_All"') IS NOT NULL THEN
    EXECUTE $c$
      COMMENT ON TABLE public."Y_codex_Layer4_Step40_Gps_Metrics_All" IS
      'CN: Layer_4 Step40 指标汇总（含 rollup 行 shard_id=-1）；EN: Layer_4 Step40 metrics unioned across shards with rollup.';
    $c$;
  END IF;

  IF to_regclass('public."Y_codex_Layer4_Step41_Signal_Metrics_All"') IS NOT NULL THEN
    EXECUTE $c$
      COMMENT ON TABLE public."Y_codex_Layer4_Step41_Signal_Metrics_All" IS
      'CN: Layer_4 Step41 指标汇总（含 rollup 行 shard_id=-1）；EN: Layer_4 Step41 metrics unioned across shards with rollup.';
    $c$;
  END IF;
END $$;
