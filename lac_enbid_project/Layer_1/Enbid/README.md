# Layer_1 / Enbid：L1-ENBID / 基站研究根目录

> 作用：在 L1-LAC / L1-CELL 合规数据的基础上，研究 ENBID / 基站（站级）层面的结构与碰撞问题，并给出可复用的规则与视图定义。  
> 约定：**以后所有 ENBID / 基站相关的正式规则、视图定义和结论，都必须写在本目录中**（一次性 SQL 仍放在 `Agent_Workspace/sql`）。

---

## 1. 输入与前置条件

L1-ENBID 研究不直接面向原始表，而是以合规视图为输入：

- 原始表：`public."网优cell项目_清洗补齐库_v1"`
- L1-LAC 视图：`public.v_lac_L1_stage1`
- L1-CELL 视图：`public.v_cell_L1_stage1`

前置规则见：

- `Layer_1/Lac/Lac_Filter_Rules_v1.md`
- `Layer_1/Cell/Cell_Filter_Rules_v1.md`

所有 ENBID / 基站相关的统计，默认只在上述 L1 视图范围内进行。

---

## 2. 统一主键与 ENBID 派生逻辑

### 2.1 Cell 级统一主键

在本项目中，**不再使用单独的 `cell_id` 或 ENBID 作为全网唯一键**。  
站在“逻辑 Cell”的角度，一个 Cell 的基础键统一约定为：

- `(运营商id, 原始lac, cell_id)`

原因：

- `cell_id` 在不同运营商之间存在数值碰撞（甚至在 4G 中跨 3 个 PLMN 复用同一个值）；  
- `ENBID` / 基站 ID 本质上是从 `cell_id` 推导出来的聚合字段，不能增加区分能力；  
- `LAC` 仍然是重要的空间/寻址维度，后续所有桶和补数都建议先按 LAC 分桶。

### 2.2 ENBID / 基站 ID 的派生

- 4G：
  - `enbid (bs_id)` = `cell_id::bigint / 256`
  - `cell_local_id` = `cell_id::bigint % 256`
- 5G：
  - `gNB_id (bs_id)` = `cell_id::bigint / 4096`
  - `cell_local_id` = `cell_id::bigint % 4096`

统一命名：

- 站级字段统一记为：`bs_id_dec` / `bs_id_hex`；  
- 小区号统一记为：`cell_local_id`。

**ENBID / 基站 ID 只作为“站级聚合字段”，不作为唯一键使用。**

---

## 3. 基于 4G TOP10 Cell 的实证发现（碰撞模式）

在视图 `public.v_cell_L1_stage1` 上统计全网 4G `cell_id` TOP10（五个 PLMN 合并），并基于脚本：

- `Agent_Workspace/sql/enbid_top10_cell_expand_v1.sql`

生成了结果表：

- `public.enbid_top10_cell_detail`

该表按 ENBID / 基站维度展开了 TOP10 `cell_id` 对应站点的所有 cell（含 4G/5G，但当前脚本只使用了 4G）。  
在这组样本上的关键结论：

1. **ENBID 规模正常，并不存在“超大站”**
   - 所有 ENBID / 基站下的 `bs_cell_cnt` 都在 1–6 之间，远小于 4G 理论上限 256。  
   - TOP10 的高访问量主要来自少数 cell 本身访问量高，而不是“一个 ENBID 下挂了成百上千个 cell”。

2. **`cell_id` 在多个运营商之间存在数值碰撞 / 共建**
   - 典型模式：同一个 `cell_id` 出现在多个 PLMN 下，并且 LAC 和 ENBID 在不同运营商之间高度一致。  
   - 例如：
     - `23160598` 同时出现在 `46001` 与 `46011`，`LAC=5665`，ENBID 相同；  
     - `240275833`、`240275835` 在联通/电信中共享 ENBID，`bs_cell_cnt=6`，典型联通+电信共建站；  
     - `174906498`、`217351505`、`110400897` 在移动+广电家族中复用同一 ENBID。
   - 这类场景应视为“跨运营商的共建/复用”，但在数据层面仍然要保留为两条记录：
     - `(46001, LAC, cell_id)`  
     - `(46011, LAC, cell_id)`  
     分别代表联通和电信侧的逻辑 Cell。

3. **同一运营商内，`cell_id` 偶尔跨 LAC（应视为异常）**
   - 在 `cell_id = 5918736` 的检查中：
     - 在 `46001` 下只出现在 `LAC=29024`；  
     - 在 `46011` 下出现在 `LAC=9853` 和 `LAC=29024` 两个 LAC。  
   - 这类“同一运营商 + 同一 `cell_id` + 多个 LAC”情况，应标记为异常：
     - 可能是编码错误、迁移残留、或统计时范围未限定导致的全局拼接；
     - 需要在 ENBID/Cell 可信库中单独记录，并在下游使用时谨慎处理。

4. **非中国 PLMN 的“污染数据”存在于原始表，但被 L1 规则挡住了**
   - 在 `cell_id = 5918736` 的临时检查表中，发现 `运营商id = 405871`、`28601` 等明显非中国 PLMN 的记录；  
   - 这些记录在 L1-LAC / L1-CELL 规则下全部为 `is_lac_L1_valid = false`、`is_cell_L1_valid = false`，不会出现在 `v_lac_L1_stage1` / `v_cell_L1_stage1` 中；  
   - 推测为原始“全球补数”阶段缺少 PLMN 限定引入的噪声，但在 L1 层已被隔离。

综合来看，本项目中 ENBID 研究的首要问题不是“ENBID 下挂载规模异常”，而是：

- `cell_id` 在不同运营商之间的共建 / 数值碰撞；  
- 个别 `cell_id` 在同一运营商内跨多个 LAC 的异常使用。

---

## 4. 对后续 ENBID / 基站研究的硬约束

为了避免目录和规则再次混乱，后续 ENBID 研究统一遵守以下约定：

1. **根目录固定**
   - 所有 ENBID / 基站相关的正式文档、规则说明、视图定义，统一放在：  
     - `Layer_1/Enbid/`  （或在重命名后统一使用 `Layer_1/基站/`，二选一）
   - 不再在根目录、`restart_v1/`、`Agent_Workspace/` 中新增 ENBID 规则。

2. **主键统一**
   - Cell 级基础键：`(运营商id, 原始lac, cell_id)`；  
   - 站级聚合键：`(运营商id, bs_id_dec)`，仅用于聚合统计，不作为全局唯一键。

3. **共建与独立的判断**
   - 对联通 / 电信：  
     - 同一 `cell_id` 在 `46001` 与 `46011` 下，且 `原始lac` 相同 → 视为共建站点；  
     - 若 LAC 不同 → 视为各自独立的站点/小区，不能合并。  
   - 对移动及其家族（46000 / 46015 / 46020）：  
     - 同一 `cell_id` 在不同 PLMN 出现且 LAC 相同，多数为共建/共用编码；  
     - 仍保持按 `(运营商id, 原始lac, cell_id)` 区分。

4. **跨 LAC 的 `cell_id`**
   - 同一 `运营商id + cell_id` 出现在多个 LAC 时：  
     - 默认视为异常模式，不作为“正常共建”处理；  
     - 建议单独在“碰撞/异常视图”中记录，用于质量监控。

5. **补数与 Join 规则**
   - 从 LAC / ENBID / Cell 可信库回填数据到业务表时，Join 条件必须包含：  
     - `运营商id`  
     - `原始lac`  
     - `cell_id`  
   - 禁止使用“只靠 cell_id”或“只靠 ENBID + local_id”进行回填，以防跨运营商或跨 LAC 的错配。

---

## 5. 本目录下的规划文件

后续将补充以下文件（名称示例）：

- `Enbid_Filter_Rules_v1.md`  
  - 记录 ENBID / 基站层面的具体规则与视图 SQL（L1-ENBID 合规）。  
- `Enbid_Top_Cell_Analysis_v1.md`  
  - 总结基于 TOP Cell 的 ENBID 结构与碰撞分析结果（可引用 `enbid_top10_cell_detail` 的统计）。  
- `Enbid_Trusted_Set_v1.md`（可选）  
  - 定义 ENBID 可信库构建思路（结合 GPS / 时间稳定性等）。  

等你下次提出具体 ENBID 研究目标时，将在本目录下新增相应 v1 文档和 SQL 视图定义。

