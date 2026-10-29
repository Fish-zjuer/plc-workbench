"""Self harness on the unified 32-task bank (six source versions, non-thinking)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from plc_agent import dataset_workflow
from plc_agent.config import ModelConfig
from plc_agent.provider import ChatProvider

R8 = Path(__file__).resolve().parents[2]
OUT = Path(os.environ.get("BANK32_SELF_OUT", str(R8 / "reports" / "bank32")))


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
