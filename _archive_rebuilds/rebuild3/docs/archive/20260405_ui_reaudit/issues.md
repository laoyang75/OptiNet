# issues

## 当前已知未覆盖项

1. `migration_suspect` 尚未在样本中覆盖，需要在 Gate F 前补充全量验证。
2. 当前样本阶段使用 rebuild2 `l0_*` 作为标准化快路径，未直接回到 legacy 27 列原始契约。
3. 最小前后端骨架已建，但当前环境缺少 FastAPI/Vue 依赖，尚未运行真实服务。
