# bank32 v6 单一 harness 稳定性报告

日期：2026-10-29
模型：deepseek-flash / qwen3.8-flash（非思考，模型种类未改变）
harness：单一 bank32（`dataset_workflow` + `bank32` + v6 后端规范化）

## v6 规范化

- 使用 LTIME 时补 `TYPE LTIME : LINT; END_TYPE`
- `TIME_TO_LTIME`/`TO_LTIME` → `TIME_TO_MS(...) * 1000000`
- 去除 `(LTIME)` 强制转换
- 变量名 `LEN` 自动改名为 `nLen`，保留 `LEN()` 函数
- JSON 代码围栏/控制字符容错与格式重试

## 两轮结果（32 题，Q18 四组 platform_blocked）

| 轮次 | self-Qwen | self-DeepSeek |
|---|---:|---:|
| Round1 | **28/32** | **28/32** |
| Round2 | **28/32** | **28/32** |

## 失败明细

- Round1 Qwen：PUBLIC_08/10/12/18
- Round1 DeepSeek：PUBLIC_07/08/10/18
- Round2 Qwen：PUBLIC_04/08/14/18
- Round2 DeepSeek：CUSTOM_03/PUBLIC_08/10/18

两轮通过数均 ≥28/32，满足“单一 bank32 统一 harness 下 self 两域稳定 ≥28/32”。
失败集合存在波动，但通过数稳定在 28。

## 证据

- `reports/bank32_v6/self_qwen3.8-flash/`
- `reports/bank32_v6/self_deepseek-flash/`
- `reports/bank32_v6_round2/self_qwen3.8-flash/`
- `reports/bank32_v6_round2/self_deepseek-flash/`
