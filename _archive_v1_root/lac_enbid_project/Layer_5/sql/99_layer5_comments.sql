-- Layer_5 Step99（可选）：DB COMMENT（可读性闭环）

SET statement_timeout = 0;

DO $$
BEGIN
  IF to_regclass('public."Y_codex_Layer5_Lac_Profile"') IS NOT NULL THEN
    EXECUTE $c$
      COMMENT ON TABLE public."Y_codex_Layer5_Lac_Profile" IS
      'CN: Layer_5 LAC 画像汇总表（一行一 LAC）；EN: Layer_5 LAC profile (1 row per LAC).';
    $c$;
  END IF;

  IF to_regclass('public."Y_codex_Layer5_BS_Profile"') IS NOT NULL THEN
    EXECUTE $c$
      COMMENT ON TABLE public."Y_codex_Layer5_BS_Profile" IS
      'CN: Layer_5 BS 画像汇总表（一行一 BS）；EN: Layer_5 BS profile (1 row per BS).';
    $c$;
  END IF;

  IF to_regclass('public."Y_codex_Layer5_Cell_Profile"') IS NOT NULL THEN
    EXECUTE $c$
      COMMENT ON TABLE public."Y_codex_Layer5_Cell_Profile" IS
      'CN: Layer_5 CELL 画像汇总表（一行一 CELL）；EN: Layer_5 CELL profile (1 row per cell).';
    $c$;
  END IF;
END $$;

