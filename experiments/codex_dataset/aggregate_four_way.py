"""Aggregate public20 + custom12 into a four-setting comparison table."""
from __future__ import annotations

import glob
import json
import os
from collections import Counter
from pathlib import Path

R8 = Path(__file__).resolve().parents[2]
MAIN = Path(r"D:\大三上\GenAI赋能工业编程\final project\plc-workbench")
CUSTOM = [f"CUSTOM_{i:02d}" for i in range(1, 13)]
PASS = {"pass", "finite_pass", "reviewed_finite_pass", "reviewed_target_pass"}
SETTINGS = ["self-deepseek", "self-qwen", "codex-deepseek", "codex-qwen"]


def latest(pattern: str) -> Path | None:
    files = glob.glob(pattern)
    return Path(max(files, key=os.path.getmtime)) if files else None


def load_status(path: Path | None):
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("status")


def public_counts():
    rows = [json.loads(line) for line in (MAIN / "reports/experiments/four_group_20261028/full_latest_flash/results.jsonl")
            .read_text(encoding="utf-8").splitlines() if line.strip()]
    out = {}
    for setting in SETTINGS:
        real = [r for r in rows if r["setting"] == setting and r["question_id"] != "18"]
        passed = sum(r["status"] == "pass" for r in real)
        q18 = next((r["status"] for r in rows if r["setting"] == setting and r["question_id"] == "18"), None)
        out[setting] = {"pass": passed, "total": len(real), "q18": q18,
                        "bad": [f"Q{r['question_id']}:{r['status']}" for r in real if r["status"] != "pass"]}
    return out


def custom_statuses():
    out = {s: {} for s in SETTINGS}
    for task in CUSTOM:
        out["codex-deepseek"][task] = load_status(latest(str(R8 / "reports/codex_relay" / f"{task}_deepseek-flash_*.json")))
        relay_qwen = latest(str(R8 / "reports/codex_relay" / f"{task}_qwen3.8-flash_*.json"))
        direct_qwen = latest(str(R8 / "reports/codex_dataset" / f"{task}_qwen3.8-flash_*.json"))
        out["codex-qwen"][task] = load_status(relay_qwen or direct_qwen)
        original = R8 / "reports/self_qwen_dataset" / task / "receipt.json"
        retry = R8 / "reports/self_qwen_dataset_retry" / task / "receipt.json"
        status = load_status(retry if retry.exists() else original)
        out["self-qwen"][task] = status
        deepseek_receipt = R8 / "reports/self_deepseek_dataset" / task / "receipt.json"
        out["self-deepseek"][task] = load_status(deepseek_receipt)
    return out


def main() -> int:
    public = public_counts()
    custom = custom_statuses()
    lines = ["# 32题四域汇总（公共20 + 自建12）", "",
             "口径：公共20 来自最新 full_latest_flash，自建12 来自最新 R8 数据集运行；每格为 agent 带修复循环后的通过数；Q18 四组均为 platform_blocked。",
             "", "| 设置 | 公共20 | 自建12 | 合计/31 | Q18 | 非通过明细 |",
             "|---|---:|---:|---:|---|---|"]
    for setting in SETTINGS:
        p = public[setting]
        cvals = custom[setting]
        cpass = sum(v in PASS for v in cvals.values())
        missing = [k for k, v in cvals.items() if v is None]
        bad = p["bad"] + [f"{k}:{v}" for k, v in cvals.items() if v is not None and v not in PASS]
        lines.append(f"| {setting} | {p['pass']}/{p['total']} | {cpass}/{len(CUSTOM)} | "
                     f"{p['pass'] + cpass}/{p['total'] + len(CUSTOM)} | {p['q18']} | "
                     f"{' '.join(bad) if bad else '-'}{' MISSING:' + ','.join(missing) if missing else ''} |")
    lines += ["", "## 自建12题逐题状态", "",
              "| 题 | self-deepseek | self-qwen | codex-deepseek | codex-qwen |",
              "|---|---|---|---|---|"]
    for task in CUSTOM:
        lines.append("| " + task + " | " + " | ".join(str(custom[s][task]) for s in SETTINGS) + " |")
    text = "\n".join(lines) + "\n"
    (R8 / "reports/four_way_32.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
