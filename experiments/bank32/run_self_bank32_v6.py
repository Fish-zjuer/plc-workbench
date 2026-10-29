"""Lean v4: weak prompt + backend facts + JSON repair, no task-level scaffolding."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from plc_agent import dataset_workflow
from plc_agent.bank32_v6 import normalize_v6
from plc_agent.config import ModelConfig
from plc_agent.provider import ChatProvider

R8 = Path(__file__).resolve().parents[2]
OUT = Path(os.environ.get("BANK32_V6_OUT", str(R8 / "reports" / "bank32_v6")))

BACKEND = """

后端事实：
- 类型与语法约定以输入包中的 backend_notes 为准（LTIME、STRING、数组下界、TON 时序等），不要自行假定或重定义内置类型。
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
                           extra_body={"enable_thinking": False,
                                       "stream_options": {"include_usage": True}})
    return ModelConfig(base_url="http://127.0.0.1:4000/v1", model=model,
                       api_key="sk-local", context_window=128000, max_output_tokens=32768,
                       max_steps=24, timeout=180,
                       extra_body={"thinking": {"type": "disabled"},
                                   "stream_options": {"include_usage": True}})


def main() -> int:
    model = sys.argv[1]
    ids = sys.argv[2].split(",") if len(sys.argv) > 2 else (
        [f"PUBLIC_{i:02d}" for i in range(1, 21)] + [f"CUSTOM_{i:02d}" for i in range(1, 13)])
    dataset_workflow.json_value = tolerant_json
    dataset_workflow.AUTHOR += BACKEND
    # Use the same packaging normalization as the Codex arm (single source of truth).
    dataset_workflow.normalize_source = normalize_v6
    cfg = config_for(model)
    cfg.validate()
    provider = ChatProvider(cfg)
    root = OUT / ("self_" + model)
    consecutive_errors = 0
    for ident in ids:
        directory = root / ident
        directory.mkdir(parents=True, exist_ok=True)
        source = directory / "candidate.st"
        # Provider/relay outages are infrastructure failures, not model results;
        # retry them a bounded number of times before recording the receipt.
        experiment_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                            "cost": 0.0, "calls": 0}
        for attempt in range(4):
            receipt = dataset_workflow.run(ident, source, directory, cfg, provider=provider,
                                           max_revisions=5, review=False,
                                           notify=lambda text: print(text, flush=True))
            usage = receipt.get("token_usage") or {}
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                experiment_usage[key] += usage.get(key, 0) or 0
            experiment_usage["cost"] += usage.get("cost", 0.0) or 0.0
            experiment_usage["calls"] += receipt.get("model_calls", 0) or 0
            if receipt.get("status") not in ("agent_error", "interrupted") or attempt == 3:
                break
            print(f"{ident} {receipt.get('status')}; retry {attempt + 1}", flush=True)
            time.sleep(15 * (2 ** attempt))
        receipt["experiment_token_usage"] = experiment_usage
        (directory / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        print(ident, receipt.get("status"), flush=True)
        if receipt.get("status") in ("agent_error", "interrupted"):
            consecutive_errors += 1
            if consecutive_errors >= 2:
                pause = min(60 * consecutive_errors, 180)
                print(f"infrastructure pause {pause}s after {consecutive_errors} consecutive errors", flush=True)
                time.sleep(pause)
        else:
            consecutive_errors = 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
