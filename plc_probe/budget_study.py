"""A small matched-invocation-budget follow-up, not an industrial benchmark."""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import random
from statistics import mean

from .backend import compile_source, run_batch
from .config import ROOT, save_json
from .demo import render_report
from .fixtures import prepare_fixtures
from .scenarios import generate


def cap_scans(pool: list[dict], budget: int, shuffle_seed: int | None = None) -> list[dict]:
    if not pool or budget <= 0 or any(not item.get("trace") for item in pool):
        raise ValueError("Need a non-empty pool and a positive scan budget")
    order = list(pool)
    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(order)
    result, remaining, index = [], budget, 0
    while remaining:
        item = order[index % len(order)]
        rows = item["trace"][:remaining]
        result.append({"name": f"budget_{index}_{item['name']}", "family": item.get("family", "budget"), "trace": rows})
        remaining -= len(rows)
        index += 1
    return result


def study(output: Path | None = None) -> dict:
    output = output or ROOT / "reports/latest"
    records, totals = [], defaultdict(list)
    fixtures = [f for f in prepare_fixtures() if f["kind"] == "synthetic_fault"]
    seeds = list(range(1000, 1010))
    budgets = [12, 48, 192]
    for fixture in fixtures:
        artifact = compile_source(fixture["source"], fixture["profile"])
        for budget in budgets:
            for strategy in ("focused", "random"):
                for seed in seeds:
                    pool = generate(fixture["profile"], strategy, seed)
                    cases = cap_scans(pool, budget, seed if strategy == "focused" else None)
                    observed = run_batch(artifact, cases)
                    actual_scans = sum(len(r["rows"]) for r in observed)
                    if actual_scans != budget:
                        raise RuntimeError("Invocation budget mismatch")
                    detected = any(r["status"] == "fail" for r in observed)
                    records.append({"profile": fixture["profile"], "variant": fixture["variant"],
                                    "strategy": strategy, "budget": budget, "seed": seed,
                                    "actual_scans": actual_scans, "detected": detected})
    for budget in budgets:
        for strategy in ("focused", "random"):
            for seed in seeds:
                totals[budget, strategy].append(sum(r["detected"] for r in records if
                    r["budget"] == budget and r["strategy"] == strategy and r["seed"] == seed))
    rows = []
    for budget in budgets:
        for strategy in ("focused", "random"):
            counts = totals[budget, strategy]
            rows.append({"scan_budget_per_implementation": budget, "strategy": strategy,
                         "mean_detected_faults_out_of_12": round(mean(counts), 2),
                         "min": min(counts), "max": max(counts), "seed_count": len(seeds)})
    result = {"study": "Equal FB invocation count; no early stop; ten fixed seeds",
              "limitations": [
                  "Synthetic faults and handwritten focused scenarios are not independent industrial data.",
                  "Equal scan invocations do not equalize simulated elapsed time, reset counts, wall time, or model token budget.",
                  "Focused scenario order is shuffled per seed. Random generation uses a different fixed seed per trial.",
                  "The final scenario is truncated to meet the budget; finite pools repeat if exhausted.",
              ], "summary": rows, "trials": records}
    save_json(output / "budget_study.json", result)
    main_path = output / "results.json"
    if main_path.exists():
        main = json.loads(main_path.read_text(encoding="utf-8"))
        main["budget_study"] = {key: result[key] for key in ("study", "limitations", "summary")}
        save_json(main_path, main)
        render_report(main, output)
    return {"status": "completed", "summary": rows, "trial_count": len(records)}


if __name__ == "__main__":
    print(json.dumps(study(), ensure_ascii=False, indent=2))
