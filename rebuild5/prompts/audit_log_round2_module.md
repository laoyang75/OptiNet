# rebuild5 二轮模块优化审计记录

> 本文件用于记录 `10b_模块优化审计.md` 的进度与结论。新会话开始时先读本文件确认进度。

## 审计进度

- M1 Step 1 数据接入：done
- M2 Step 2 基础画像：done
- M3 Step 3 流式评估：done
- M4 Step 4 知识补数：done
- M5 Step 5 画像维护：done
- M6 服务层：pending
- M7 运行控制：pending
- M8 通用基础层：pending

## 详细记录

## M1 Step 1 数据接入

- 状态：done
- 当前方案摘要：
  - 当前实现仍保留了清晰的 `parse -> clean -> fill` 主链，Step 1 与后续画像/知识补数逻辑解耦，这个大边界是合理的。
  - 实库证据显示全量 `beijing_7d` 已稳定跑通：`25,442,069` 原始记录 -> `45,406,191` 解析行 -> `45,314,465` 清洗/补齐后行，清洗通过率 `0.998`。
  - 同报文补齐确实有价值：GPS 从 `37,382,496` 行提升到 `39,469,757` 行，RSRP 从 `40,541,783` 行提升到 `42,788,777` 行。
  - 结合新约束“后续业务收敛为单数据源模式”，Step 1 的重点不再是多源注册扩展，而是把单源主链、数据库落盘策略和下游索引协作收敛干净。
- 保留项：
  - `parse.py`、`clean.py`、`fill.py` 的职责切分仍然值得保留，后续优化最好在这个三段式骨架内演进，而不是推翻重来。
  - `*_raw` 与 `*_filled` 并存的输出设计正确，既保留原始真相，也给后续步骤提供可用结果列。
  - Step 1 统计单独写入 `rebuild5_meta.step1_run_stats`，没有混入 Step 2-5 的 snapshot 语义，这个边界应继续保持。
  - ODS 规则集中定义在 `clean.py`，可读性和后续规则审查体验都不错。
- 可疑或可优化的点：
  - 目前真正的问题不是“变成单源”，而是**单源化还没收干净**：`source_prep` 已经把数据压成单表输入，但 `parse` / `queries` / 前端页面仍保留伪多源壳层。
  - “字段审计”页面当前更像静态字段字典：接口只返回 `definitions.py` 中冻结的字段定义，不读取真实源表 schema、覆盖率或样本值。
  - 同报文补齐现在按 `record_id + cell_id` 只选一个 donor 行，存在补齐遗漏。抽样 `22,445` 行里，发现 `117` 行“`cell_infos` 自己没有 GPS、同组 `ss1` 有有效 GPS，但最终 `lon_filled/lat_filled` 仍为空”；另有 `54` 行“同组存在 RSRP，但 `rsrp_filled` 仍为空”。这说明问题不是零星个案。
  - Step 1 运行统计的 `started_at` / `finished_at` 当前写成同一个时刻，数据库里时长恒为 `0`，不利于后续容量评估和回归比较。
  - Step 1 的存储足迹偏重：当前库里 `raw_gps` 约 `31 GB`、`etl_parsed` 约 `17 GB`、`etl_clean_stage` 约 `90 GB`、`etl_cleaned` 约 `29 GB`，并且 `etl_cleaned(record_id)` 还出现了重复索引。

### 建议卡：单源化要收彻底，不要保留伪多源壳层

- 等级：P1
- 当前方案：
  - `source_prep.py` 已经先把原始输入合并去重写入 `rebuild5.raw_gps`，再把 `raw_lac` 置空，运行时其实已经是单源入口。
  - 但 `parse.py` 还在固定跑 `raw_gps/raw_lac` 两条支路，`queries.py` 和前端页面也仍按多源口径组织展示。
- 问题：
  - 如果业务方向已经明确改成单数据源，这些伪多源壳层只会增加表数量、CTAS 步骤、统计口径和 UI 心智负担。
  - 现在的复杂度既拿不到真正的多源收益，也会干扰后续数据库重建和索引治理。
- 替代方案：
  - 直接承认并固化单源模式：准备阶段产出唯一输入表，例如 `raw_events` / `etl_input_records`。
  - `parse` 只对这个单表做两次展开：`cell_infos` 一次、`ss1` 一次；页面和统计也改成单源口径。
- 预期收益：
  - 主链更短，数据库重建时的表和索引治理更直接。
  - 后续 agent 只需要理解“单输入表 -> parse -> clean -> fill -> etl_cleaned”这一条链，不会被伪多源结构误导。
- 改造成本：中
- 建议动作：现在做，作为 Step 1 收口整理的一部分

### 建议卡：同报文补齐 donor 改成“按字段择优”，不要只选一行

- 等级：P1
- 当前方案：
  - `fill.py` 里先按 `record_id + cell_id` 选出一条 donor，再把 donor 上的 GPS/信号/WiFi/运营商/LAC 一次性用于补齐。
  - donor 排序优先 `cell_infos`，其次才看 donor 是否携带有效 GPS。
- 问题：
  - 一个 group 内不同字段往往分散在不同来源行上，单 donor 会天然漏补。
  - 已在实库里抓到反例：存在 `cell_infos` 行 GPS 为空、同组 `ss1` 行 GPS 有效，但最终仍未补上的样本；抽样也说明这个问题不是孤立现象。
- 替代方案：
  - 把 donor 拆成按字段择优的多个子集，例如 `best_gps_donor`、`best_signal_donor`、`best_basic_donor`。
  - GPS / WiFi / 信号保留现有时间窗约束；运营商 / LAC 继续允许无时间窗补齐。
- 预期收益：
  - 补齐率会继续提升，且逻辑与“结构性互补”的业务语义更一致。
  - SQL 语义也更清晰，后续更容易解释“为什么这个字段能补、那个字段不能补”。
- 改造成本：中
- 建议动作：现在做（收益明确，但本轮先记录，不直接改代码）

### 建议卡：把“字段审计”明确成真实审计，或降级成字段字典

- 等级：P2
- 当前方案：
  - `get_field_audit_payload()` 直接读取 `definitions.py` 的冻结定义，前端展示的是目标字段结构和分类统计。
- 问题：
  - 它没有检查真实源表字段、类型稳定性、覆盖率、样本值，也没有产出真正的 `keep / parse / drop` 审计结果。
  - 对当前单数据集 demo 影响不大，但会误导后续 agent 以为系统已经具备“接新源前自动审计”的能力。
- 替代方案：
  - 如果短期不做真实字段审计，就把页面/文案改名成“字段字典”。
  - 如果要保留“字段审计”定位，就应补充 `information_schema` + 覆盖率采样 + 决策结果落表。
- 预期收益：
  - 降低认知偏差，避免未来接新数据源时误判模块能力。
- 改造成本：低到中
- 建议动作：仅更新文档/页面文案，或在下一轮接新源前补齐真实审计

### 建议卡：把清洗主路径改成单次 CTAS，并让中间表保留可配置

- 等级：P2
- 当前方案：
  - `clean.py` 先复制出 `etl_clean_stage`，再执行多轮 `UPDATE` 置空/打标，之后 `fill.py` 再从 `etl_clean_stage` 生成 `etl_cleaned`。
  - 当前默认长期保留 `etl_parsed`、`etl_clean_stage`、`etl_cleaned` 三层大表。
- 问题：
  - 全量数据下 `etl_clean_stage` 约 `90 GB`，已经明显高于最终 `etl_cleaned`，说明主路径把调试成本固化成了常驻成本。
  - `etl_cleaned(record_id)` 还出现重复索引，暴露出 Step 1 与下游模块对索引所有权没有收敛。
- 替代方案：
  - 将多数 ODS 规则收敛到一次 `CREATE TABLE AS SELECT ... CASE WHEN ...` 的清洗投影里，减少宽表反复更新。
  - 为 `etl_parsed` / `etl_clean_stage` 增加 debug retain 开关，默认只保留最终产物和必要统计。
  - 收敛 `etl_cleaned` 索引定义，避免上下游重复建同列索引。
- 预期收益：
  - 降低磁盘占用和写放大，长期运行更稳。
  - 减少“为了排障方便，把所有中间状态永久留在线上库”的历史包袱。
- 改造成本：中
- 建议动作：先记账，等下一轮性能整理时一起处理

- 优先级结论：P1
- 是否已改代码：否
- 是否仅更新文档：是（本次仅写入审计记录）
- 下一步：进入 M2 Step 2 基础画像审计，优先复盘三层匹配、Path A/B/C 分流和基础画像是否还存在可收敛的复杂度

## M2 Step 2 基础画像

- 状态：done
- 当前方案摘要：
  - Step 2 作为“版本化分流节点”的总体定位仍然成立：先读上一轮已发布正式库，再做 Path A / B / C 分流，最后只对 Path B 生成 `profile_base`，这个模块边界是合理的。
  - 当前主链也有值得保留的约束：Path B 只使用原始有效 GPS 进入空间统计，不把 Step 1 结构性补齐 GPS 当作真实定位证据；分钟级去重 + 中位数质心 + P50/P90 半径的基础画像链条也仍然是清晰的。
  - 经确认，Step 2 里真正需要优先关注的是 **ID 碰撞回退** 和 **Cell 主键实现是否夹带 `bs_id`** 两件事；“真碰撞”属于 Step 5 维护问题，不应与 Step 2 的 `collision_id_list` 逻辑混为一类。
- 保留项：
  - `run_step2_pipeline -> path_a -> path_b -> profile_obs -> profile_base` 的单向流水线结构值得保留，见 `rebuild5/backend/app/profile/pipeline.py:483`。
  - Path B 只认原始 GPS 的原则应保留：`build_path_b_cells()` 用 `has_raw_gps` 作为准入，`build_profile_obs()` 也只用 `lon_raw/lat_raw/gps_valid` 做空间统计，见 `rebuild5/backend/app/profile/pipeline.py:651` 和 `rebuild5/backend/app/profile/pipeline.py:719`。
  - 分钟级独立观测和中位数质心实现仍然合理，后续如果优化，应优先优化路由边界与 SQL 组织，而不是先推翻这套空间统计口径，见 `rebuild5/backend/app/profile/pipeline.py:723` 和 `rebuild5/backend/app/profile/pipeline.py:754`。
- 可疑或可优化的点：
  - Step 2 的 `collision_id_list` 属于 **ID 碰撞防护**，不是 Step 5 的“真碰撞”判定；但当前 Layer 3 回退仍只按 `cell_id` 选一条正式库候选，削弱了 ID 碰撞校验的意义。
  - `bs_id` 不应进入 Step 2 的 Cell 业务主键；如果当前 Path B / `profile_base` 链路里还夹带 `bs_id` 参与主键聚合，应视为实现错误。
  - Path C 当前作为总量统计保留是可接受的，现阶段不必把它拆成复杂原因体系。
  - Step 2 几乎没有针对三层匹配 SQL 的测试护栏；当前测试主要覆盖纯函数和 router 包装，没有覆盖 Layer 1/2/3 命中语义和 `profile_base` 业务键一致性。

### 建议卡：重写 ID 碰撞 Layer 3，不要只按 `cell_id` 取一条正式库候选

- 等级：P0
- 当前方案：
  - Layer 3 消费的是 Step 5 产出的 `collision_id_list`（ID 碰撞表），再用 `SELECT DISTINCT ON (cell_id)` 从正式库里挑一条候选中心点，用 GPS 距离判断是否命中 Path A，见 `rebuild5/backend/app/profile/pipeline.py:593`。
- 问题：
  - 一旦同一个 `cell_id` 在正式库里对应多个 `(operator_code, lac)` 组合，`DISTINCT ON (cell_id)` 就会把 ID 碰撞问题粗暴压成“单候选问题”。
  - 这会导致本应做“更多校验”的记录，实际只拿去和一个任意 combo 比距离。
- 替代方案：
  - Layer 3 应基于同 `cell_id` 的全部可信候选做判定。
  - 若记录已带 `operator_code` 或 `lac`，先按可用键缩小候选；若两者都缺，再在候选集中按 GPS 距离择优，并明确“唯一命中 / 多候选冲突 / 无候选接近”三种结果。
- 预期收益：
  - 让 ID 碰撞防护真正按“碰撞对象集合”工作，而不是按“碰撞 cell_id 的代表行”工作。
  - 这是 Step 2 最关键的 correctness 修复，直接决定 Path A 是否可信。
- 改造成本：中
- 建议动作：现在做

### 建议卡：确认并清理 `bs_id` 参与 Step 2 主键的残留实现

- 等级：P1
- 当前方案：
  - `build_path_b_cells()` 和 `profile_base` 聚合当前仍把 `bs_id` 放进 GROUP BY / JOIN 主链，见 `rebuild5/backend/app/profile/pipeline.py:657`、`rebuild5/backend/app/profile/pipeline.py:776`。
- 问题：
  - 已确认 `bs_id` 不应进入 Step 2 的 Cell 主键；它和 Cell 本质上是派生关系，不应反过来参与 Cell 对象切分。
  - 如果实现里仍依赖 `bs_id` 做主链聚合，会把同一 Cell 误拆成多个 Step 2 对象，污染 `profile_base` 统计。
- 替代方案：
  - Step 2 主键统一使用 `(operator_code, lac, cell_id)`。
  - `bs_id` 保留为维度字段或派生属性，不再参与对象切分。
- 预期收益：
  - 让 Step 2 与全局实体模型重新一致，避免在进入 Step 3 前就人为分裂 Cell。
  - 后续 Step 3/5 的快照比较、晋级和维护也会更稳定。
- 改造成本：中
- 建议动作：现在做

### 建议卡：为三层匹配和 `profile_base` 主键补 SQL 级测试

- 等级：P2
- 当前方案：
  - 现有测试只覆盖 `classify_cell_state()` 等纯逻辑和 router 包装，没有覆盖 Layer 1/2/3 路由 SQL，也没有覆盖 `profile_base` 是否按正确业务键聚合。
- 问题：
  - Step 2 现在最关键的风险都在 SQL 路由层，而不是纯 Python 逻辑层。
  - 当前轻量测试里甚至已经出现与真实 router 签名不一致的失败，说明测试护栏本身也没有紧跟代码演化。
- 替代方案：
  - 新增最小 fixture 级 SQL 测试，覆盖：
    - 非碰撞 direct match
    - 非碰撞 relaxed match
    - 碰撞 cell_id 的 GPS 回退
    - `profile_base` 只按 `(operator_code, lac, cell_id)` 聚合
- 预期收益：
  - 让后续 Step 1 补齐修复、Step 2 路由修正后有稳定护栏，避免再次把核心路由改偏。
- 改造成本：中
- 建议动作：先记账

- 优先级结论：P0
- 是否已改代码：否
- 是否仅更新文档：是（本次仅写入审计记录）
- 下一步：进入 M3 Step 3 流式评估审计，优先复盘状态机、快照冻结边界以及 Cell/BS/LAC 三层上卷是否还有结构性问题

## M3 Step 3 流式评估

- 状态：done
- 当前方案摘要：
  - 经确认，Step 3 的核心角色不是“维护历史快照池”，而是：接收本次应升级的候选对象，完成本次评估，把结果快照下来供观察和 diff，再把晋级对象交给 Step 5。
  - `snapshot` 在这里应只是“本次处理结果的落表”，不是下一轮评估的主状态池；真正需要持续存在的是 new / waiting / observing 的候选对象库。
  - 当前实现的主要偏差不在状态机表面，而在结构分工：代码里只有 snapshot / published library，没有看到独立候选池；同时 Step 2 也没有显式把历史 waiting / observing 候选继续送入 Step 3。
- 保留项：
  - Step 3 与 Step 5 的职责分工值得保留：Step 3 负责准入和冻结，Step 5 负责维护和发布，这条边界是清楚的。
  - Cell / BS / LAC 分层 snapshot + diff 的数据组织方式仍然有价值，后续如果修，应优先修候选池与快照语义，不必先推翻展示表结构。
  - BS / LAC 完全由下层对象上卷派生，这个方向正确，避免了上层对象绕过 Cell 直接读原始事实。
- 可疑或可优化的点：
  - 当前系统里没有看到独立的 Step 3 候选池持久表；现有持久表只有 `trusted_snapshot_*`、`snapshot_diff_*` 和 Step 5 的 published library。这和“未晋级对象继续等待”这条业务逻辑不匹配。
  - 当前 `build_current_cell_snapshot()` 只读取本批 `profile_base`，再把 `trusted_cell_library` carry-forward 进本次 snapshot；这会把“本次评估结果”和“继承展示结果”混在一张表里。
  - 交叉检查 Step 2 后，`build_path_b_cells()` / `profile_base` 仍只围绕本批 `etl_cleaned` 生成当前批候选，没有显式并入历史 new / waiting / observing 候选。因此就算 Step 3 语义正确，候选对象也无法自然连续升级。
  - 生命周期判定、资格判定在 `evaluation/pipeline.py` 中以内联 SQL 重写了一遍，而不是复用 `profile.logic` 中已有的纯逻辑定义，存在规则漂移风险。
  - `baseline_eligible` 目前仍被硬编码为 `anchor_eligible AND lifecycle_state='excellent'`；这对后续成熟门槛外化不友好。
  - Step 3 的测试几乎没有覆盖候选池连续性、快照语义、diff 语义和三层上卷；现有 evaluation router 相关测试甚至已经和真实签名脱节。

### 建议卡：为 Step 3 建立独立候选池，`snapshot` 只保留本次结果

- 等级：P0
- 当前方案：
  - 当前 Step 3 只有本次 snapshot 和 Step 5 的 published library，没有看到独立候选池。
  - `build_current_cell_snapshot()` 直接把本批 `profile_base` 结果和 `trusted_cell_library` 的 carry-forward 混进本次 snapshot。
- 问题：
  - 这会让 `snapshot` 同时承担“本次结果展示”和“状态延续”的角色，语义混乱。
  - 更重要的是，没有独立候选池，就无法让 new / waiting / observing 对象在未晋级时继续保留、等待下批升级。
- 替代方案：
  - 明确拆成两层：
    - 候选池：保存 new / waiting / observing 的连续状态，用于下一轮继续评估
    - 快照：只保存本次处理结果，用于观察、对比和 UI 展示
  - 如果快照里需要展示继承信息，应明确标记来源，而不能代替候选池本身。
- 预期收益：
  - 重新对齐 Step 3 的核心职责，让“未晋级继续等待、晋级后交付 Step 5”这条主流程真正成立。
  - 这是 Step 3 当前最关键的结构性修复。
- 改造成本：高
- 建议动作：现在做

### 建议卡：回收 Step 2 的候选连续性责任，确保 waiting / observing 会再次进入 Step 3

- 等级：P1
- 当前方案：
  - 当前 Step 2 的 `build_path_b_cells()` / `profile_base` 只围绕本批 `etl_cleaned` 生成候选输入，没有看到历史 waiting / observing 候选的显式并入逻辑。
- 问题：
  - 按已确认设计，Step 3 不应自己靠 snapshot 养候选池；那 waiting / observing 能否继续升级，责任就必须前移到 Step 2。
  - 如果 Step 2 每次只送“本批新来的 Path B”，那未晋级对象无法在下轮自然重评估。
- 替代方案：
  - 明确 Step 2 / Step 3 交接契约：
    - Step 2 负责输出“本次全部待评估候选对象”
    - Step 3 负责对这批候选做一次评估
  - 若候选连续性不在 Step 2 完成，就必须由单独候选池承担，而不能靠 snapshot 假装完成。
- 预期收益：
  - 保证 Step 2 -> Step 3 -> Step 5 的主链是连续的，而不是每批只评一次新数据。
- 改造成本：中到高
- 建议动作：现在做

### 建议卡：把生命周期 / 资格规则收敛到单一规则源

- 等级：P1
- 当前方案：
  - `profile.logic` 里已经有 `classify_cell_state()` 等纯逻辑，但 Step 3 真正评估时又在 SQL 里重写了一套 waiting / qualified / excellent / anchor_eligible / position_grade 判定。
- 问题：
  - 规则有双份实现，后续阈值或业务口径一改，很容易一边更新、一边漏改。
  - 当前测试大多只覆盖纯逻辑函数，对 SQL 版本规则几乎没有约束。
- 替代方案：
  - 收敛成单一规则源：要么 SQL 生成自统一规则配置，要么把 Python 规则与 SQL 逻辑绑定到同一抽象层。
  - 至少要把 waiting / qualified / excellent / anchor / baseline 的规则映射整理成单点维护。
- 预期收益：
  - 降低 Step 3 最容易出现的“文档、纯逻辑、SQL 三套规则逐步漂移”风险。
- 改造成本：中
- 建议动作：现在做

### 建议卡：把 `baseline_eligible` 从当前硬编码里拆出来

- 等级：P2
- 当前方案：
  - 当前 Step 3 仍把 `baseline_eligible` 固定写成 `anchor_eligible AND lifecycle_state = 'excellent'`，并只对当前批候选对象重算。
- 问题：
  - 这让成熟门槛的外化和后续维护策略扩展都变得困难。
  - 该逻辑虽然目前可运行，但它把一个尚待收敛的业务规则提前固化到了主链实现里。
- 替代方案：
  - 将 `baseline_eligible` 的形成条件明确配置化，或至少集中到单一规则源中。
  - Step 3 只负责计算当前语义，不在 SQL 中硬散落。
- 预期收益：
  - 给后续 Step 5 维护和资格外化留出空间。
- 改造成本：中
- 建议动作：先记账

### 建议卡：补 Step 3 的候选连续性 / snapshot / diff SQL 级测试

- 等级：P2
- 当前方案：
  - 现有测试几乎不覆盖 Step 3 主流程，只覆盖纯函数和 router 包装；evaluation router 相关测试还存在和当前接口签名不一致的问题。
- 问题：
  - Step 3 最关键的问题已经不是单点阈值，而是：
    - 候选对象是否连续进入下一轮
    - snapshot 是否只是本次结果
    - diff 是否只对本次结果做比较
  - 这些目前都几乎没有测试护栏。
- 替代方案：
  - 新增最小 fixture 级测试，至少覆盖：
    - waiting / observing 对象跨批继续进入评估
    - 晋级对象正确交付 Step 5
    - snapshot 只记录本次结果
    - diff 的 `new/promoted/demoted/removed`
    - BS/LAC 上卷计数
- 预期收益：
  - 避免后续修 Step 3 时再次把“候选池”和“快照”混成一层。
- 改造成本：中
- 建议动作：先记账

- 优先级结论：P0
- 是否已改代码：否
- 是否仅更新文档：是（本次仅写入审计记录）
- 下一步：进入 M4 Step 4 知识补数审计，优先复盘 donor 选择、异常检测边界和 Step 2/3/5 之间的版本关系

## M4 Step 4 知识补数

- 状态：done
- 当前方案摘要：
  - Step 4 作为“Path A 命中记录的可信知识补数 + GPS 异常初筛”这一职责定位仍然是对的，主边界也比较清晰：只处理 `path_a_records`，只消费已发布 donor，不回写 Step 1 真相表。
  - 当前实现里 `path_a_records LEFT JOIN trusted_cell_library(anchor_eligible=true)` 的主干结构合理，说明模块方向没有跑偏。
  - 但这一步最关键的风险出在 **donor 版本冻结没有真正钉住**，以及 **donor 匹配条件被写得过窄**。这两点会直接影响 Step 4 是否还能被称为“上一轮可信知识补数”。
- 保留项：
  - Step 4 只处理 Path A、并以 `anchor_eligible=true` donor 作为补数来源，这个边界值得保留，见 `rebuild5/backend/app/enrichment/pipeline.py:103`。
  - GPS 异常初筛只比较原始 `lon_raw/lat_raw` 与 donor 质心，不拿 Step 4 补出来的 GPS 反向自证，这个方向是正确的。
  - Step 4 产出 `enriched_records` 和 `gps_anomaly_log` 两层结果，再交给 Step 5 消费，这个治理候选层设计也值得保留。
- 可疑或可优化的点：
  - 当前 Step 4 donor 版本来源是“最新 published library”，而不是“与本次 Step 2 命中所对应的上一轮版本”。一旦用户在 Step 5 已经跑过当前批后再重跑 Step 4，就会读到错误 donor 版本，违反冻结快照原则。
  - GPS 异常检测跳过碰撞 `cell_id` 时，同样直接读 `collision_id_list` 的最新 batch，而不是与 donor 版本同一批次的碰撞表，版本边界仍然不稳。
  - donor JOIN 现在把 `tech_norm` 也写进匹配条件，这会在记录缺少 `tech_norm` 时直接阻断 donor 命中，甚至让“tech 补数”本身无法发生；这和文档定义的 donor 业务键 `(operator_code, lac, cell_id)` 不一致。
  - Step 4 文档已经把 `pressure_avg` 作为可选 donor 字段写明，且 Step 5 schema 里已有 `pressure_avg`，但当前 Step 4 实现仍未真正使用 donor 的 `pressure_avg` 做补数。
  - Step 4 几乎没有主流程测试，现有测试只覆盖 enrichment stats router 的包装。

### 建议卡：把 donor 和 collision 版本钉死到 Step 2 所引用的上一轮版本

- 等级：P0
- 当前方案：
  - `run_enrichment_pipeline()` 先取最新 `step2_run_stats`，再独立取 `trusted_cell_library` 的最新版本作为 donor 来源；GPS 异常跳过碰撞时也直接读 `collision_id_list` 的最新 batch，见 `rebuild5/backend/app/enrichment/pipeline.py:21`、`rebuild5/backend/app/enrichment/pipeline.py:63`、`rebuild5/backend/app/enrichment/pipeline.py:212`。
- 问题：
  - 这会让 Step 4 在重跑或部分重跑场景下读到“当前最新正式库”，而不是“本次 Step 2 命中时所依据的上一轮正式库”。
  - 一旦 Step 5 已经发布了本批结果，再重跑 Step 4，就会发生本批读取本批 donor 的自我强化，直接破坏冻结快照原则。
- 替代方案：
  - Step 4 必须显式绑定到 Step 2 当前 run/batch 的 `trusted_snapshot_version` / 上一轮 published batch。
  - donor library 和 `collision_id_list` 都应按同一 donor 版本读取，而不是各自取 `MAX(batch_id)`。
- 预期收益：
  - 重新保证 Step 4 读取的是“上一轮可信知识”，而不是“系统里最新能读到的任何知识”。
  - 这是 Step 4 当前最关键的 correctness 修复。
- 改造成本：中
- 建议动作：现在做

### 建议卡：放宽 donor 匹配到 `(operator_code, lac, cell_id)`，不要用 `tech_norm` 阻断补数

- 等级：P1
- 当前方案：
  - `_insert_enriched_records()` 当前 donor JOIN 条件除了 `(operator_filled, lac_filled, cell_id)` 外，还要求 `COALESCE(d.tech_norm, p.tech_norm) = p.tech_norm`，见 `rebuild5/backend/app/enrichment/pipeline.py:194`。
- 问题：
  - 文档定义的 donor 业务键是 `(operator_code, lac, cell_id)`，`tech_norm` 是 donor 维度字段，不应反过来成为 donor 命中的必要条件。
  - 现在如果记录本身 `tech_norm` 为空，JOIN 会直接失败，导致 donor 无法命中；这甚至会让 `tech` 自身的补数永远无法发生。
- 替代方案：
  - donor 主匹配统一收回到 `(operator_code, lac, cell_id)`。
  - `tech_norm` 保留为 donor 属性；若确实需要校验，只能作为附加审计或冲突检测，而不是主匹配条件。
- 预期收益：
  - 让 Step 4 donor 匹配与 Step 2 / 文档 / 全局实体模型重新一致。
  - 避免因为缺少 `tech_norm` 造成整条 donor 链断掉。
- 改造成本：中
- 建议动作：现在做

### 建议卡：把 `pressure_avg` 补数从文档承诺变成真实实现

- 等级：P2
- 当前方案：
  - Step 4 文档已经把 `pressure_avg` 作为可选 donor 字段写明，Step 5 的 schema / window 聚合也已有 `pressure_avg`，但 Step 4 当前仍只把原始 `pressure` 透传为 `pressure_final`，并未真正读取 donor `pressure_avg`，见 `rebuild5/backend/app/enrichment/pipeline.py:166`。
- 问题：
  - 文档、Step 5 schema 和 Step 4 实现目前是脱节的。
  - 虽然这是可选能力，但当前描述已经超过了实现能力。
- 替代方案：
  - 若决定支持压力补数，就把 donor `pressure_avg` 真正纳入 JOIN / SELECT / fill source。
  - 若短期不做，就把 Step 4 文档明确降级为“预留字段，暂未启用”。
- 预期收益：
  - 减少文档与实现偏差。
- 改造成本：低
- 建议动作：先记账

### 建议卡：为 Step 4 补 donor 版本 / fill source / anomaly 级测试

- 等级：P2
- 当前方案：
  - 现有测试只覆盖 enrichment stats router 的基础包装，没有覆盖：
    - donor 版本是否正确钉住
    - `anchor_eligible=true` 过滤
    - fill source 是否正确落 `trusted_cell`
    - anomaly 跳过 collision 的版本边界
- 问题：
  - Step 4 的核心风险都在 SQL 和版本边界层，目前几乎没有护栏。
- 替代方案：
  - 新增最小 fixture 级测试，至少覆盖：
    - Step 4 donor 版本固定到 Step 2 所引用的上一轮
    - 缺 `tech_norm` 不阻断 donor 主匹配
    - GPS / signal / operator / lac fill source 落值正确
    - collision anomaly skip 使用同版本碰撞表
- 预期收益：
  - 让 Step 4 后续修复后不再反复退化成“最新库补数”或“过窄 donor 匹配”。
- 改造成本：中
- 建议动作：先记账

- 优先级结论：P0
- 是否已改代码：否
- 是否仅更新文档：是（本次仅写入审计记录）
- 下一步：进入 M5 Step 5 画像维护审计，优先复盘发布链、碰撞逻辑、窗口重算和退出管理是否与前几步主流程真正闭环

## M5 Step 5 画像维护

- 状态：done
- 当前方案摘要：
  - Step 5 作为“发布链 + 深度治理链”的整体角色仍然合理：以 Step 3 冻结结果为准入基础，用 Step 4 事实层更新当前批观测，再发布新一版 `trusted_*_library`，这个大方向是对的。
  - 当前实现里，对已发布对象做 carry-forward，避免 Path A 对象在新 batch 中从正式库掉出，这条修复后的主线仍然值得保留。
  - 但模块内部最严重的问题已经不再是“发布有没有做”，而是“很多治理逻辑仍是占位实现”。尤其是滑动窗口、真实碰撞判定、多质心分析这三块，当前代码离文档承诺仍有明显距离。
- 保留项：
  - `publish_cell_library()` 对当前 snapshot 与上一版正式库做合并发布，并显式 carry-forward 已发布对象，这个发布思路值得保留，见 `rebuild5/backend/app/maintenance/publish_cell.py:33` 和 `rebuild5/backend/app/maintenance/publish_cell.py:301`。
  - Step 5 能把 `pressure_avg` 写回 `trusted_cell_library`，为下一批 Step 4 donor 扩展预留能力，这条链路方向是对的。
  - B 类 `collision_id_list` 与 A 类真碰撞分层处理的设计仍然正确，不应再混成一类。
- 可疑或可优化的点：
  - 当前 `cell_sliding_window` 只装载“本批最新 `enriched_records`”，并没有真正保留最近 N 天 / 最近 M 条窗口，因此现在的“滑动窗口”其实不是滑动窗口。
  - 由于窗口不连续，`active_days_30d`、`consecutive_inactive_days`、漂移指标、窗口样本量等 Step 5 核心指标都失去了长期维护语义，退出管理也因此不可靠。
  - A 类真碰撞文档已明确要求同 `(operator_code, tech_norm, lac, cell_id)` 才成立，但当前 `_detect_absolute_collision()` 实现没有把 `tech_norm` 纳入真碰撞判定键。
  - 多质心分析当前仍是占位：`is_multi_centroid` 只是 `p90` 触发标记，`cell_centroid_detail` / `bs_centroid_detail` 也只是单簇 stub，不是真正的多簇分析结果。
  - GPS 异常时序目前也只是“按 anomaly_count 粗分 drift / migration_suspect”，并未实现文档承诺的连续天数、时段聚集、单向迁移等时序判定。
  - Step 5 测试几乎没有覆盖窗口、碰撞、carry-forward、退出和多质心主流程。

### 建议卡：把滑动窗口做成真正的滑动窗口，不要只装本批 `enriched_records`

- 等级：P0
- 当前方案：
  - `refresh_sliding_window()` 当前会删除当前 `batch_id` 的窗口数据，再把 `enriched_records` 里“最新 batch”的记录整体插入到 `cell_sliding_window`，见 `rebuild5/backend/app/maintenance/window.py:14`。
- 问题：
  - 这不是真正的窗口维护，而只是“当前批观测副本”。
  - 结果会直接影响：
    - `active_days_30d`
    - `consecutive_inactive_days`
    - `window_obs_count`
    - `max_spread_m / net_drift_m / drift_ratio`
    - 以及后续的退出管理和漂移分类
  - 没有连续窗口，Step 5 最核心的“长期维护”语义就立不住。
- 替代方案：
  - 让窗口按明确规则累积最近 N 天 / 最近 M 条观测，而不是每批重建成“单批临时表”。
  - 至少要保证上一批窗口能和本批 `enriched_records` 合并，再做裁剪。
- 预期收益：
  - 重新让 Step 5 拥有“长期维护”而不是“当前批再加工”的能力。
  - 这是 Step 5 当前最关键的结构性修复。
- 改造成本：高
- 建议动作：现在做

### 建议卡：把 A 类真碰撞判定补回 `tech_norm`

- 等级：P1
- 当前方案：
  - 文档和业务口径都已确认 A 类真碰撞是同 `(operator_code, tech_norm, lac, cell_id)` 在远距离双簇出现。
  - 但当前 `_detect_absolute_collision()` 实现只按 `(operator_code, lac, cell_id)` 比较不同 `bs_id`，见 `rebuild5/backend/app/maintenance/collision.py:76`。
- 问题：
  - 这会把跨制式但同 `operator_code + lac + cell_id` 的情况也纳入真碰撞扫描，扩大误报范围。
  - 既然 B 类 ID 碰撞已单独存在，A 类真碰撞更需要严格按确认后的业务键执行。
- 替代方案：
  - `_detect_absolute_collision()` 应把 `tech_norm` 纳入 pair join 和目标键。
  - B 类 `collision_id_list` 仍保持只看 `(operator_code, lac)` 的映射关系，不要混改。
- 预期收益：
  - 让真碰撞重新对齐已确认业务定义，避免 Step 5 把不该阻断的对象误判为 collision。
- 改造成本：低到中
- 建议动作：现在做

### 建议卡：把多质心从占位标记升级为真实分析

- 等级：P1
- 当前方案：
  - 当前 `is_multi_centroid` 主要通过 `p90_radius_m >= trigger` 触发，`cell_centroid_detail` / `bs_centroid_detail` 仅写一条主簇 stub 记录，见 `rebuild5/backend/app/maintenance/publish_cell.py:206` 和 `rebuild5/backend/app/maintenance/publish_bs_lac.py:17`。
- 问题：
  - 这不是文档承诺的“异常子集聚类 -> 多簇证据 -> 主/次簇落表”。
  - 目前只是把“大半径”近似映射成“多质心候选”，治理语义不够。
- 替代方案：
  - 将多质心分析收敛成真实异常子集计算：
    - 先筛异常 Cell / BS
    - 再做多簇聚类
    - 最终把主/次簇独立写入 detail 表
  - `is_multi_centroid` 不应继续仅由 `p90` 阈值代理。
- 预期收益：
  - 让 Step 5 的“多质心”标签和详情表真正具备治理价值，而不是占位 UI 数据。
- 改造成本：高
- 建议动作：现在做

### 建议卡：把 GPS 异常时序从“计数分档”升级为真实时序判定

- 等级：P1
- 当前方案：
  - `compute_gps_anomaly_summary()` 现在只汇总 `anomaly_count` 和 `last_anomaly_at`，发布时再用 `anomaly_count >= 3` 粗分为 `migration_suspect` 或 `drift`，见 `rebuild5/backend/app/maintenance/cell_maintain.py:100` 和 `rebuild5/backend/app/maintenance/publish_cell.py:460`。
- 问题：
  - 这和文档里的“连续天数 / 时段聚集 / 单向位移 / 往返跳变”完全不是一个层级。
  - 目前 Step 5 实际上还没有真正的 GPS 异常时序判定。
- 替代方案：
  - 建立按天 / 时段 / 方向聚合的时序判断表，再区分：
    - `drift`
    - `time_cluster`
    - `migration_suspect`
    - 进一步 collision confirm
- 预期收益：
  - 让 Step 5 的异常治理从“计数触发器”升级成真实治理逻辑。
- 改造成本：高
- 建议动作：先记账，但应进入 Step 5 主修复序列

### 建议卡：补 Step 5 的窗口 / carry-forward / collision / exit 级测试

- 等级：P2
- 当前方案：
  - 现有测试几乎不覆盖 Step 5 主流程，只覆盖 stats payload 整形和 router 包装。
- 问题：
  - 当前最关键的逻辑——窗口连续性、carry-forward、碰撞判定、退出状态——几乎没有自动护栏。
- 替代方案：
  - 新增最小 fixture 级测试，至少覆盖：
    - Path A 已发布对象 carry-forward
    - 滑动窗口跨批合并
    - A/B 两类碰撞分层
    - dormant / retired 退出链路
    - `pressure_avg` 从 Step 4 -> Step 5 -> Step 4 的回路
- 预期收益：
  - 让 Step 5 修复后不再回退成“单批窗口”或“占位治理”。
- 改造成本：中
- 建议动作：先记账

- 优先级结论：P0
- 是否已改代码：否
- 是否仅更新文档：是（本次仅写入审计记录）
- 下一步：进入 M6 服务层审计，优先复盘服务查询模型、详情结构和报表边界是否与主流程产物一致
