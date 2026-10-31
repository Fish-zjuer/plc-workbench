# DMXAPI 与网页工作台

老师提供的说明要求 Chat Completions：Base URL 为 `https://www.dmxapi.cn/v1`，模型 ID 从 https://www.dmxapi.cn/rmb 原样复制。请勿把旧的本地模型别名视为中转站的有效模型名。

## 启动

在项目目录、已安装依赖的 Python 环境执行：

```powershell
python -m plc_agent web --port 8765
```

浏览器打开 http://127.0.0.1:8765 。服务仅监听本机。也可使用 `launch-web.cmd`；端口被占用时添加 `--port 18765`。

1. 打开“模型与环境”，填写准确模型名与助教发放的 Key，保存。
2. 默认使用非流式请求，符合老师示例；流式选项会请求 `stream_options.include_usage`。
3. 如需验证连接，点击“测试连接”，会消耗 Token。
4. “题库与规约”浏览冻结的公共20题、自建12题及 LTL；“代码工作台”选题后生成、自动修复或检查粘贴的代码。
5. 工作台展示源码版本、日志、有限测试证据、Token 和耗时；支持停止及下载 ST。
6. “实验记录”展示网页运行的逐题记录，并可导出 JSON。

Key 存在服务端 `agent_data/private/credentials.json`，浏览器只获得是否配置的状态；也可在启动服务前设置 `DMXAPI_API_KEY`。网页保存操作会切换到 DMXAPI，其他供应商的已存密钥不会被自动复用。配置保存在本地，凭据文件不保证加密。

本地 STruC++ 检查通过不等于 CODESYS 编译通过。环境页可检查 CODESYS 配置；CODESYS 可在网页配置、执行正/负对照验证和单题编译。LTL 展示不等于已执行形式化验证。第一版网页支持冻结题库，任意自然语言需求仍使用现有通用任务 CLI/TUI；网页已接入 Codex 与四设置批量启动，详见 [批量实验说明](CODESYS_WEB_EXPERIMENTS.md)。

## 自研批量实验改用老师中转站

```powershell
$env:PLC_AGENT_PROVIDER = 'dmxapi'
# 通过本机环境安全设置 DMXAPI_API_KEY，不要把真实密钥写入源码。
$env:BANK32_V6_OUT = 'reports/dmxapi_experiment'
python experiments/bank32/run_self_bank32_v6.py '从页面复制的准确模型ID'
```

此模式不注入 DeepSeek/Qwen 官方接口专用的 thinking 参数。未设置 `PLC_AGENT_PROVIDER=dmxapi` 时保留原实验入口。

新实验逐次 usage 保存在 `receipt.json.metrics`；聚合在 `token_usage`。`complete=false` 表示至少一次响应缺少 usage，已知数值只是部分统计，不能算作零消耗或完整总量。DMXAPI 未返回 cost 时不能把聚合字段的 0 解读为免费；费用以中转站账单/该模型价格为准。不会自动试探其他模型或重发收费请求来补 usage。

网页任务目录为 `agent_data/web_runs/<run_id>`，不覆盖历史报告；每次“生成”都是独立运行。再次检查编辑后的代码会产生新的检查记录。服务重启后可读取已保存记录。

题库和约束导入见 [导入说明](IMPORT_BANKS.md)；队友交付差异见 [交付包对照](TEAM_DELIVERY_20261030_REVIEW.md)。
