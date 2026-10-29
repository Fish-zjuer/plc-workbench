"""Host-side fixed-test checker used by the Codex dataset workspace."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from plc_agent import dataset
from plc_agent.bank32_v6 import normalize_v6
from plc_probe.backend import BackendError


def main() -> int:
    task_id, source = sys.argv[1], Path(sys.argv[2])
    task = dataset.load(task_id)
    text = source.read_text(encoding="utf-8-sig")
    normalized = normalize_v6(text, task["block"])
    if normalized != text:
        source.write_text(normalized, encoding="utf-8")
    try:
        result = dataset.evaluate(source, task)
    except BackendError as exc:
        result = exc.result
    except Exception as exc:  # noqa: BLE001 - report diagnostics to the agent
        result = {"status": "invalid_candidate", "message": str(exc)}
    compact = {k: v for k, v in result.items() if k != "cases"}
    print(json.dumps(compact, ensure_ascii=False))
    return 0 if result.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
