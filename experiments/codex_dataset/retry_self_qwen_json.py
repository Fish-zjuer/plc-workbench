"""Retry self-Qwen tasks whose proposals used invalid JSON control characters."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from plc_agent import dataset_workflow
from plc_agent.config import ModelConfig
from plc_agent.provider import ChatProvider

R8 = Path(__file__).resolve().parents[2]
OUT = R8 / "reports" / "self_qwen_dataset_retry"


def _tolerant_json(text):
    try:
        return json.loads(text)
    except Exception:
        return json.loads(text, strict=False)


def main() -> int:
    dataset_workflow.json_value = _tolerant_json
    dataset_workflow.AUTHOR += (
        "\n输出必须是严格 JSON：code 字符串中的换行必须写成 \\n，"
        "禁止在字符串里直接包含换行、制表符或其他未转义控制字符。"
    )
    key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not key:
        raise SystemExit("missing DASHSCOPE_API_KEY")
    cfg = ModelConfig(base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                      model="qwen3.8-flash", api_key=key, context_window=128000,
                      max_output_tokens=32768, max_steps=24, timeout=180,
                      extra_body={"enable_thinking": False})
    cfg.validate()
    provider = ChatProvider(cfg)
    for ident in (sys.argv[1].split(",") if len(sys.argv) > 1 else ["CUSTOM_03", "CUSTOM_05"]):
        directory = OUT / ident
        directory.mkdir(parents=True, exist_ok=True)
        source = directory / "candidate.st"
        receipt = dataset_workflow.run(ident, source, directory, cfg, provider=provider,
                                       max_revisions=3, review=False, notify=lambda text: print(text, flush=True))
        (directory / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        print(ident, receipt.get("status"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
