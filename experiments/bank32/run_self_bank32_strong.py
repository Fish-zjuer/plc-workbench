"""Strong dataset harness: main-workflow rules applied to the unified bank.

The weak harness is dataset_workflow from agent-32-integration. This variant
keeps the same bank/checker but adds requirement checklists, timing/backend
rules and tolerant JSON parsing, without changing the frozen tests.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from plc_agent import bank32, dataset_workflow
from plc_agent.config import ModelConfig
from plc_agent.provider import ChatProvider

R8 = Path(__file__).resolve().parents[2]
OUT = Path(os.environ.get("BANK32_STRONG_OUT", str(R8 / "reports" / "bank32_strong_v2")))

STRONG_RULES = """

Strong-harness rules:
- 逐条实现 requirement_checklist 中的每个编号需求；接口字段只读语义必须遵守。
- 接口没有 CycleTime 时，不要假设 1ms 扫描步长；使用 TON，PT 取题面值；状态置位后同一扫描调用 TON；上电初始化是一次性的，急停不能重启已完成的初始化。
- 当前 STruC++ 后端没有内建 LTIME；如使用 LTIME，必须声明 TYPE LTIME : LINT;，但禁止使用 LTIME#/LT# 字面量。
- 禁止使用 LTIME#/LT# 字面量；需要长时间累计时用 T# 或 TIME_TO_LTIME。
- STRING 使用 LEN/ADR/POINTER TO BYTE；禁止 .at()、CHAR、STRING[] 索引。
- ARRAY 保留声明下界；STRUCT 用 TYPE Name : STRUCT ... END_STRUCT END_TYPE；CASE ELSE 不加冒号。
- 输出必须是严格 JSON：code 字符串中的换行写成 \\n，不能包含未转义控制字符。
"""


def tolerant_json(text):
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```[a-zA-Z]*\s*", "", value)
        value = re.sub(r"\s*```$", "", value)
    try:
        return json.loads(value)
    except Exception:
        pass
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        value = value[start:end + 1]
    return json.loads(value, strict=False)


def checklist(task):
    text = task.get("requirements", "")
    items = []
    for match in re.finditer(r"^\s*(\d+)\.\s+(.+?)(?=\n\s*\d+\.\s|\n##|\Z)", text, re.M | re.S):
        items.append(f"R{match.group(1)}: " + re.sub(r"\s+", " ", match.group(2)).strip())
    for port in task.get("interface", []):
        items.append(f"FIELD {port['name']} ({port['type']}, {port['direction']})")
    return items[:40]


def timing_rules(task):
    text = task.get("requirements", "")
    if not re.search(r"\b(TIME|TON|TOF|debounce|elapsed|hold|seconds?|ms)\b", text, re.I):
        return []
    return [
        "No fixed scan step: use IEC TON with PT from the task.",
        "Set the state a timer observes, then call that TON in the same scan.",
        "A one-shot power-up initialization must not restart when emergency stop clears.",
    ]


def config_for(model: str) -> ModelConfig:
    if model.startswith("qwen"):
        key = os.environ.get("DASHSCOPE_API_KEY", "")
        if not key:
            raise SystemExit("missing DASHSCOPE_API_KEY")
        return ModelConfig(base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                           model=model, api_key=key, context_window=128000,
                           max_output_tokens=32768, max_steps=24, timeout=180,
                           extra_body={"enable_thinking": False})
    return ModelConfig(base_url="http://127.0.0.1:4000/v1", model=model,
                       api_key="sk-local", context_window=128000, max_output_tokens=32768,
                       max_steps=24, timeout=180,
                       extra_body={"thinking": {"type": "disabled"}})


def main() -> int:
    model = sys.argv[1]
    ids = sys.argv[2].split(",") if len(sys.argv) > 2 else (
        [f"PUBLIC_{i:02d}" for i in range(1, 21)] + [f"CUSTOM_{i:02d}" for i in range(1, 13)])
    dataset_workflow.json_value = tolerant_json
    dataset_workflow.AUTHOR += STRONG_RULES
    original_normalize = dataset_workflow.normalize_source

    def strong_normalize(code, block):
        code = original_normalize(code, block)
        if "LTIME" in code.upper() and "TYPE LTIME" not in code.upper():
            code = "TYPE LTIME : LINT;\n" + code
        return code

    dataset_workflow.normalize_source = strong_normalize
    original_packet = bank32.author_packet

    def strong_packet(task, current_source="", failure=None):
        packet = original_packet(task, current_source, failure)
        packet["requirement_checklist"] = checklist(task)
        packet["timing_rules"] = timing_rules(task)
        if task["id"] == "PUBLIC_10":
            packet["timing_rules"].append(
                "Q10 order: set OverheatLatched first, then call the hold TON in the same scan; "
                "call TON(IN := TRUE) on the trigger scan, not the next scan.")
        return packet

    bank32.author_packet = strong_packet
    cfg = config_for(model)
    cfg.validate()
    provider = ChatProvider(cfg)
    root = OUT / ("self_" + model)
    for ident in ids:
        directory = root / ident
        directory.mkdir(parents=True, exist_ok=True)
        source = directory / "candidate.st"
        receipt = dataset_workflow.run(ident, source, directory, cfg, provider=provider,
                                       max_revisions=5, review=False, notify=lambda text: print(text, flush=True))
        (directory / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        print(ident, receipt.get("status"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
