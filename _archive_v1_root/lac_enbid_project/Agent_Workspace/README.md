# Agent_Workspace：agent 工作区

> 用途：给自动化 agent 使用的临时工作目录，可以自由放置一次性脚本、小规模抽样数据和中间结果文件。

约定：

- 这里的内容默认是“临时的 / 可重建的”，不视为长期沉淀文档；  
- 真正稳定的规则、视图定义、结论需要写回对应的 Layer 文档（例如 `Layer_1/Lac/README.md` 等）；  
- 如需暂存 SQL、Python 脚本、调试日志等，建议放在本目录下对应子目录中，例如：  
  - `Agent_Workspace/sql/`  
  - `Agent_Workspace/scripts/`  
  - `Agent_Workspace/tmp/`

后续如果有需要，也可以在这里额外加一个简单的 `CHANGELOG.md`，记录 agent 在本目录下做过的关键操作。 

