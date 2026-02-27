# Step35 动态 Cell 验证结果（28D / server table）

输入表：`public.cell_id_375_28d_data_20251225`

## 窗口与口径

- 28 天窗口（按输入表最大 `ts` 自动取末 28 天自然日）：`2025-11-27` ~ `2025-12-24`
- 粒度（scoped cell）：`(opt_id, dynamic_network_type, cell_id)`
- 每日主导质心：`round(lgt, 3) / round(ltt, 3)`（约 100m）
- 稳定日过滤：`day_major_share >= 0.30`
- 动态判定阈值：
  - `effective_days >= 7`
  - `half1_major_day_share >= 0.60` 且 `half2_major_day_share >= 0.60`
  - `half1_centroid != half2_centroid`
  - `half_major_dist_km >= 10`

## 总览

- 参与判定的 scoped cell 数：577
- 判为动态（is_dynamic_cell=1）：7

## 命中明细（按两半质心距离降序）

| opt_id | tech_norm | cell_id | effective_days | major_state_cnt | switch_cnt | half1_share | half2_share | half1(lon,lat) | half2(lon,lat) | dist_km |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| 46000 | 5G_SA | 5690290179 | 23 | 3 | 2 | 0.7692 | 1.0000 | (116.231, 40.083) | (112.608, 37.792) | 403.779 |
| 46000 | 5G_SA | 5747290115 | 8 | 3 | 4 | 0.6667 | 0.6000 | (116.363, 40.015) | (116.603, 40.344) | 41.881 |
| 46001 | 5G_SA | 1816752257 | 19 | 2 | 1 | 1.0000 | 1.0000 | (116.425, 39.893) | (116.164, 40.061) | 29.044 |
| 46000 | 5G_SA | 5708734466 | 12 | 3 | 2 | 1.0000 | 0.6000 | (116.313, 40.148) | (116.055, 40.302) | 27.803 |
| 46011 | 5G_SA | 1615007746 | 10 | 3 | 2 | 0.6000 | 0.6000 | (115.894, 40.376) | (116.105, 40.264) | 21.797 |
| 46000 | 5G_SA | 5700349955 | 18 | 4 | 3 | 0.6250 | 0.9000 | (116.607, 40.118) | (116.781, 40.040) | 17.158 |
| 46000 | 5G_SA | 5731385348 | 26 | 5 | 5 | 1.0000 | 0.6154 | (116.316, 39.782) | (116.147, 39.719) | 16.057 |

## 数据库存放

本次验证结果已落表：

- `public."Y_codex_Layer3_Step35_28D_Dynamic_Cell_Profile"`

如需导出 CSV（你本地 psql）：

```sql
\copy (select * from public."Y_codex_Layer3_Step35_28D_Dynamic_Cell_Profile" order by operator_id_raw, tech_norm, cell_id) to 'dynamic_cell_result_28d_20251225.csv' csv header;
```

