"""Lean v4: weak prompt + backend facts + JSON repair, no task-level scaffolding."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from plc_agent import dataset_workflow
from plc_agent.config import ModelConfig
from plc_agent.provider import ChatProvider

R8 = Path(__file__).resolve().parents[2]
OUT = Path(os.environ.get("BANK32_V4_OUT", str(R8 / "reports" / "bank32_v4")))

BACKEND = """

后端事实：
- 当前 STruC++ 后端没有内建 LTIME；如使用 LTIME，必须声明 TYPE LTIME : LINT;。
- TIME 转 LTIME 使用 TO_LTIME(...)，不要使用 TIME_TO_LTIME。
- STRING 使用 ADR/POINTER TO BYTE；不要使用 CHAR、.at() 或 STRING 下标；不要把 LEN 用作变量名。
- 输出必须是严格 JSON；code 中换行写成 \\n，不要使用 Markdown 代码围栏。
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
    start, end = value.find("{"), value.rfind("}")
    if start >= 0 and end > start:
        value = value[start:end + 1]
    return json.loads(value, strict=False)


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
    dataset_workflow.AUTHOR += BACKEND
    original_normalize = dataset_workflow.normalize_source

    def normalize(code, block):
        code = original_normalize(code, block)
        code = code.replace("TIME_TO_LTIME(", "TO_LTIME(")
        if "LTIME" in code.upper() and "TYPE LTIME" not in code.upper():
            code = "TYPE LTIME : LINT;\n" + code
        return code

    dataset_workflow.normalize_source = normalize
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
