# launcher

这里不再是占位目录，当前已经承接独立启动器正式实现。

## 入口文件

- 启动器服务：`rebuild3/launcher/launcher.py`
- 启动器界面：`rebuild3/launcher/launcher_ui/index.html`
- 启动脚本：`rebuild3/scripts/dev/start_launcher.sh`

## 默认地址

- 启动器：`http://127.0.0.1:47120`
- 后端：`http://127.0.0.1:47121`
- 前端：`http://127.0.0.1:47122`

## 使用方式

```bash
./rebuild3/scripts/dev/start_launcher.sh
```

启动后，优先在启动器里确认后端 / 前端 / 数据库状态，再进入主工作台。

## 设计来源

- 参考上一版：`rebuild2/launcher_web.py`
- 对齐原型：`rebuild3/docs/UI_v2/launcher/launcher.html`
- 对齐说明：`rebuild3/docs/UI_v2/launcher/launcher_doc.md`
