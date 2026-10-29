"""Run the 12 custom tasks through the self dataset workflow with DeepSeek."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from plc_agent import dataset_workflow
from plc_agent.config import ModelConfig
from plc_agent.provider import ChatProvider

R8 = Path(__file__).resolve().parents[2]
OUT = R8 / "reports" / "self_deepseek_dataset"


def main() -> int:
    cfg = ModelConfig(base_url="http://127.0.0.1:4000/v1", model="deepseek-flash",
                      api_key="sk-local", context_window=128000, max_output_tokens=32768,
                      max_steps=24, timeout=180,
                      extra_body={"thinking": {"type": "disabled"}})
    cfg.validate()
    provider = ChatProvider(cfg)
    ids = [f"CUSTOM_{i:02d}" for i in range(1, 13)]
    if len(sys.argv) > 1:
        ids = sys.argv[1].split(",")
    for ident in ids:
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
