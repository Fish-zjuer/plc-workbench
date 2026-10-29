"""Aggregate the unified bank32 weak four-way result and strong ablation."""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

R8 = Path(__file__).resolve().parents[2]
BASE = R8 / "reports" / "bank32_full"
STRONG = R8 / "reports" / "bank32_strong"
TASKS = [f"PUBLIC_{i:02d}" for i in range(1, 21)] + [f"CUSTOM_{i:02d}" for i in range(1, 13)]
PASS = {"pass", "finite_pass", "reviewed_finite_pass", "reviewed_target_pass"}
SETTINGS = ["self-deepseek", "self-qwen", "codex-deepseek", "codex-qwen"]


def ok(value) -> bool:
    return value in PASS


def self_map(model: str):
    out = {}
    for path in glob.glob(str(BASE / "self" / f"self_{model}" / "*" / "receipt.json")):
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out[Path(path).parent.name] = value.get("status")
    return out


def codex_map(model: str):
    out = {}
    files = glob.glob(str(BASE / "codex_relay" / f"*_{model}_*.json"))
    for path in sorted(files, key=os.path.getmtime):
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out[value.get("task_id")] = value.get("status")
    return out


def main() -> int:
    maps = {
        "self-deepseek": self_map("deepseek-flash"),
        "self-qwen": self_map("qwen3.8-flash"),
        "codex-deepseek": codex_map("deepseek-flash"),
        "codex-qwen": codex_map("qwen3.8-flash"),
    }
    rows = []
    for setting in SETTINGS:
        statuses = {}
        for task in TASKS:
            statuses[task] = "platform_blocked" if task == "PUBLIC_18" else maps[setting].get(task)
        public = [statuses[t] for t in TASKS[:20] if t != "PUBLIC_18"]
        custom = [statuses[t] for t in TASKS[20:]]
        rows.append((setting, sum(ok(x) for x in public), sum(ok(x) for x in custom),
                     sum(ok(x) for x in public) + sum(ok(x) for x in custom), statuses))
    lines = ["# 32题四域表（weak harness，bank32）", "",
             "口径：Q18 四组 platform_blocked；可做 31 题（公共19 + 自建12）。",
             "", "| 设置 | 公共19 | 自建12 | 合计/31 | 通过率 | 非通过 |",
             "|---|---:|---:|---:|---:|---|"]
    for setting, pub, cus, total, statuses in rows:
        bad = [f"{t}:{statuses[t]}" for t in TASKS if statuses[t] not in (None, "platform_blocked") and not ok(statuses[t])]
        missing = [t for t in TASKS if statuses[t] is None]
        lines.append(f"| {setting} | {pub}/19 | {cus}/12 | **{total}/31** | {total/31:.1%} | "
                     f"{' '.join(bad) if bad else '-'}{' MISSING:' + ','.join(missing) if missing else ''} |")
    lines += ["", "## 逐题状态（weak）", "",
              "| 题 | " + " | ".join(SETTINGS) + " |", "|---|" + "---|" * len(SETTINGS)]
    for task in TASKS:
        lines.append("| " + task + " | " + " | ".join(str(rows[i][4][task]) for i in range(len(SETTINGS))) + " |")
    # Strong ablation (self only, Qwen complete; DeepSeek not run).
    strong_qwen = self_map("qwen3.8-flash") if False else {}
    strong_root = STRONG / "self_qwen3.8-flash"
    strong_qwen = {}
    for path in glob.glob(str(strong_root / "*" / "receipt.json")):
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        strong_qwen[Path(path).parent.name] = value.get("status")
    weak_qwen = {t: maps["self-qwen"].get(t) for t in TASKS if t != "PUBLIC_18"}
    strong = {t: strong_qwen.get(t) for t in TASKS if t != "PUBLIC_18"}
    lines += ["", "## Harness 消融（self-Qwen，31 题口径）", "",
              "| harness | 公共19 | 自建12 | 合计/31 |", "|---|---:|---:|---:|"]
    for name, data in [("weak", weak_qwen), ("strong", strong)]:
        pub = sum(ok(data.get(t)) for t in TASKS[:20] if t != "PUBLIC_18")
        cus = sum(ok(data.get(t)) for t in TASKS[20:])
        lines.append(f"| {name} | {pub}/19 | {cus}/12 | {pub+cus}/31 |")
    text = "\n".join(lines) + "\n"
    (R8 / "reports" / "four_way_32_weak.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
