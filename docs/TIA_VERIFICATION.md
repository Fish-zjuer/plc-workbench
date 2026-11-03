# 在现有 CODESYS 工作流中接入 TIA

本次只增加平台适配。SHL、TON、开放数组、VARIANT、CBMC 性能与验证窗口问题由队友维护的共享验证后端负责，此分支不再另行修复或替换它们。

## 共用与替换的边界

| 共用部分 | TIA 替换部分 |
| --- | --- |
| 题库、需求、接口和测试判据 | SCL 作者提示、固定接口检查 |
| Trial：6 个版本、24 次请求、1800 秒预算、请求计量 | `.scl` 文件与 TIA 评估入口 |
| self / Codex、两个模型、批量并发、暂停/恢复/停止 | 平台选择及 TIA 环境检查 |
| 测试序列和 `dataset.judge_output` | Openness 编译、PLCSIM Advanced 仿真执行 |
| `dataset_formal.attach`、PLCverif、CBMC、LTL 结果处理 | SCL 语法正规化回调，随后调用原共享验证器 |
| 日志、历史、版本、CSV、统计与最终代码导出 | 平台字段与 `.scl` 下载 |

TIA 的单题入口、CLI 完整检查及 2×2 批量实验均使用现有 Trial/Campaign。CODESYS 的现有入口及默认行为保留。模型请求可以并行，单机 TIA 调用串行排队，防止同时启动大量 Portal 会话。

完整流程为：生成源码 → 厂商编译 → 原生测试 → 共用判卷 → 共用形式化入口 → 结果记录/预算内修复。编译与行为阶段未通过时，形式化不执行，与 CODESYS 相同。遇到共享后端不支持、超时或待复核反例时，保留它的结论，不另外造一个 TIA 验证模型让其通过。

`tia_formal.py` 仅处理 SCL 边界：块名与局部变量写法、头部元数据、定时器实例调用写法、移位函数命名参数，以及 Siemens 临时变量的调用生命周期。它不提供 SHL/SHR 或 TON 的函数实现，不修改共享验证上界、求解策略、输入域或 LTL 判据。类型与指令是否支持最终由共享后端决定。

## 本机配置与使用

1. 构建 `integrations/tia_bridge/TiaBridge.csproj`，使用本机 Openness V21 的 `net48` API 目录。
2. 在“模型与环境”填写 Bridge、编译模板及可选 Openness 目录。
3. 原生仿真还需要已授权的 PLCSIM Advanced x64 API DLL，以及专用 S7-1500 `.ap21` 仿真模板。当前 S7-1200 模板仅用于编译。新 EXE 的 Openness 访问确认由使用者手动处理。
4. 形式化工具继续使用共用的 `formal_config.json`。本机已解压的 PLCverif/Java/CBMC 位于忽略目录 `.runtime`，不随代码提交。

```powershell
# 现有 SCL，使用相同阶段门禁检查；不调用模型
python -m plc_agent tia check PUBLIC_02 path/to/candidate.scl --output outputs/tia_check

# 通过共用 Trial 生成、检查与修复
python -m plc_agent tia run PUBLIC_02

# 保留阶段三单独编译模式
python -m plc_agent tia run PUBLIC_02 --compile-only
```

工作台单题选择 TIA；批量实验也可选择 TIA，复用原有 self/Codex × 模型 A/B 的四组实验。平台配置未齐全时预检查阻止付费批量生成。

## 验证状态

已验证 Bridge 能通过本机 Openness V21 编译；PUBLIC_02 与 CUSTOM_01 的测试驱动能被真实 TIA 编译。单元与服务测试检查平台路由、相同预算/版本限制、四组调度、文件类型、结果统计和共享形式化调用。

**原生仿真尚未验收**：本机仍缺 PLCSIM Advanced 和匹配的 S7-1500 模板。当前不能声称行为测试覆盖已经与 CODESYS 相同。大型驱动还需在实际 CPU 的存储容量内验证。

上一轮独立形式化扩展及其 2026-11-03 证据已退出本次改动，保存在本机 `.tmp-tests/tia-scope-backup`。其中 PUBLIC_02 的移位模型存在空函数问题，先前的通过数和反例数不得作为有效结论使用。2026-11-01 的原始编译验收报告及哈希保持不变。

本次没有修改 `plcverif_backend.py`、`cbmc_model.py`、`plcverif_st.py`、`ltl_adapter.py` 中的验证算法/模型。后续合入队友的后端更改后，TIA 继续调用同一后端。
