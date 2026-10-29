"""Aggregate self-only bank32 v6 runs across one or more rounds.

Usage:
    python experiments/bank32/aggregate_self_bank32_v6.py ROOT1 [ROOT2 ...] [--out report.md]

Each ROOT must contain `self_<model>/<TASK>/receipt.json` directories as written
by run_self_bank32_v6.py.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

TASKS = [f"PUBLIC_{i:02d}" for i in range(1, 21)] + [f"CUSTOM_{i:02d}" for i in range(1, 13)]
MODELS = ["deepseek-flash", "qwen3.8-flash"]
PASS = {"pass", "finite_pass", "reviewed_finite_pass", "reviewed_target_pass"}
PLATFORM_LIMITED = {"PUBLIC_18"}


def ok(status) -> bool:
    return status in PASS


def load(root: Path, model: str) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    base = root / f"self_{model}"
    if not base.is_dir():
        return out
    for path in sorted(base.glob("*/receipt.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out[path.parent.name] = value.get("status")
    return out


def counts(statuses: dict[str, str | None]):
    public = sum(ok(statuses.get(t)) for t in TASKS[:20])
    public19 = sum(ok(statuses.get(t)) for t in TASKS[:20] if t not in PLATFORM_LIMITED)
    custom = sum(ok(statuses.get(t)) for t in TASKS[20:])
    return public, public19, custom, public + custom, public19 + custom


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("roots", nargs="+")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    roots = [Path(r) for r in args.roots]
    maps = [[load(root, model) for model in MODELS] for root in roots]

    lines = ["# bank32 v6 self 结果汇总", ""]
    lines.append("口径：self 的 `finite_pass` 记为通过。`PUBLIC_18` 在补充 VARIANT `PV_*` API 事实后已可解；")
    lines.append("旧轮次（r1/r2）因缺少该事实而失败，故另保留排除 Q18 的 31 题列供对照。")
    lines.append("")

    for index, root in enumerate(roots, 1):
        lines += [f"## 第 {index} 轮（`{root}`）", "",
                  "| 模型 | 公共20 | 公共19 | 自建12 | 合计/32 | 通过率 | 合计/31 |",
                  "|---|---:|---:|---:|---:|---:|---:|"]
        bullets = []
        for model, data in zip(MODELS, maps[index - 1]):
            public, public19, custom, total, total31 = counts(data)
            missing = [t for t in TASKS if data.get(t) is None]
            lines.append(f"| self-{model} | {public}/20 | {public19}/19 | {custom}/12 | "
                         f"**{total}/32** | {total / 32:.1%} | **{total31}/31** |")
            bad = [f"{t}:{data.get(t)}" for t in TASKS if data.get(t) is not None and not ok(data.get(t))]
            if bad:
                bullets.append(f"- self-{model} 非通过（{len(bad)}）：" + "、".join(bad) +
                               (f"；缺失：{','.join(missing)}" if missing else ""))
        lines.append("")
        lines += bullets
        lines.append("")

    if len(roots) > 1:
        lines += ["## 稳定性（跨轮）", "",
                  "| 模型 | 两轮均通过 | 波动题 |", "|---|---:|---|"]
        for model_index, model in enumerate(MODELS):
            stable = 0
            flaky = []
            for task in TASKS:
                statuses = [maps[r][model_index].get(task) for r in range(len(roots))]
                if all(ok(s) for s in statuses):
                    stable += 1
                elif any(ok(s) for s in statuses):
                    flaky.append(f"{task}({','.join(str(s) for s in statuses)})")
            lines.append(f"| self-{model} | {stable}/32 | {' '.join(flaky) if flaky else '-'} |")
        lines.append("")

    lines += ["## 逐题状态", ""]
    header = "| 题 | "
    for index in range(len(roots)):
        header += " | ".join(f"R{index + 1}-{m}" for m in MODELS) + " | "
    lines.append(header)
    lines.append("|---|" + "---|" * (len(roots) * len(MODELS)))
    for task in TASKS:
        row = f"| {task} | "
        for index in range(len(roots)):
            row += " | ".join(str(maps[index][model_index].get(task)) for model_index in range(len(MODELS))) + " | "
        lines.append(row)
    lines.append("")

    text = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
