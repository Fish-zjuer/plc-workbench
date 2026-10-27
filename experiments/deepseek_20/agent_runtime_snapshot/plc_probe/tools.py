from __future__ import annotations

from collections import Counter
import math
from pathlib import Path
import time

from .backend import Artifact, compile_source, run_batch
from .config import save_json
from .contracts import MONITOR_VERSION, PROFILES
from .scenarios import generate


EVIDENCE_SCOPE = {
    "execution": "Actual ST source transpiled by STruC++ 0.7.0 and executed as native C++",
    "evaluation": "Finite scan-sequence tests against independent handwritten contracts",
    "codesys_compile": "not_executed",
    "formal_verification": "not_executed",
    "hardware_validation": "not_executed",
}


def summary(results: list[dict]) -> dict:
    failures = [r for r in results if r["status"] == "fail"]
    return {
        "scenarios": len(results), "scans": sum(len(r["rows"]) for r in results),
        "passed": len(results) - len(failures), "failed": len(failures),
        "first_failure_properties": dict(Counter(r["first_failure"]["property"] for r in failures)),
        "cases": [{k: r[k] for k in ("name", "family", "status", "first_failure")} for r in results],
    }


def _normalized(rows: list[dict]) -> list[dict]:
    start = rows[0]["time_ms"]
    return [{"time_ms": row["time_ms"] - start, "inputs": dict(row["inputs"])} for row in rows]


def minimize_failure(artifact: Artifact, result: dict, budget: int = 60) -> dict:
    if not 0 <= budget <= 200:
        raise ValueError("minimization budget must be 0..200")
    failure = result["first_failure"]
    if failure is None:
        raise ValueError("Cannot minimize a passing scenario")
    target = failure["property"]
    original = [{"time_ms": r["time_ms"], "inputs": r["inputs"]} for r in result["rows"][:failure["scan"] + 1]]
    current, attempts, partitions = _normalized(original), 0, 2
    while len(current) > 1 and attempts < budget:
        size = math.ceil(len(current) / partitions)
        candidates = []
        for begin in range(0, len(current), size):
            remaining = current[:begin] + current[begin + size:]
            if remaining and len(candidates) < budget - attempts:
                candidates.append({"name": "shrink", "trace": _normalized(remaining)})
        evaluated = run_batch(artifact, candidates) if candidates else []
        attempts += len(evaluated)
        chosen = next((r for r in evaluated if any(v["property"] == target for row in r["rows"] for v in row["violations"])), None)
        if chosen:
            current = [{"time_ms": row["time_ms"], "inputs": row["inputs"]} for row in chosen["rows"]]
            partitions = max(2, partitions - 1)
        elif partitions >= len(current):
            break
        else:
            partitions = min(len(current), partitions * 2)
    scenario = {"name": result["name"] + "_minimized", "family": "minimized", "trace": current}
    replay = run_batch(artifact, [scenario])[0]
    reproduced = any(v["property"] == target for row in replay["rows"] for v in row["violations"])
    if not reproduced:
        raise RuntimeError("Internal error: minimized scenario did not reproduce the target property")
    return {
        "schema": "plc-probe-counterexample-v1", "profile": artifact.profile,
        "source_sha256": artifact.sha256, "monitor_version": MONITOR_VERSION,
        "target_property": target, "original_failure_prefix_scans": len(original),
        "minimized_scans": len(current), "candidate_replays": attempts,
        "minimality": "deletion reduction under an explicit replay budget; not guaranteed globally shortest",
        "scenario": scenario, "reproduced": reproduced, "result": replay,
        "evidence_scope": EVIDENCE_SCOPE,
    }


def probe(source: str, profile: str, suite: str = "focused", seed: int = 20261026,
          output: str | None = None, shrink_budget: int = 60) -> dict:
    started = time.perf_counter()
    artifact = compile_source(source, profile)
    results = run_batch(artifact, generate(profile, suite, seed))
    result = {"status": "fail" if any(r["first_failure"] for r in results) else "pass",
              "profile": profile, "source": artifact.source, "source_sha256": artifact.sha256,
              "suite": suite, "seed": seed, "summary": summary(results), "evidence_scope": EVIDENCE_SCOPE}
    first = next((r for r in results if r["first_failure"]), None)
    if first:
        result["counterexample"] = minimize_failure(artifact, first, shrink_budget)
    result["duration_seconds"] = round(time.perf_counter() - started, 4)
    if output:
        save_json(Path(output), result)
    return result


def replay(source: str, counterexample: dict) -> dict:
    if counterexample.get("monitor_version") != MONITOR_VERSION:
        raise ValueError("Counterexample monitor version is not supported")
    artifact = compile_source(source, counterexample["profile"])
    result = run_batch(artifact, [counterexample["scenario"]])[0]
    reproduced = any(v["property"] == counterexample["target_property"] for row in result["rows"] for v in row["violations"])
    return {"status": result["status"], "reproduced": reproduced,
            "source_matches_record": artifact.sha256 == counterexample["source_sha256"],
            "target_property": counterexample["target_property"], "result": result, "evidence_scope": EVIDENCE_SCOPE}


def compare(before: str, after: str, profile: str, suite: str = "focused", seed: int = 20261026) -> dict:
    scenarios = generate(profile, suite, seed)
    before_artifact, after_artifact = compile_source(before, profile), compile_source(after, profile)
    old, new = run_batch(before_artifact, scenarios), run_batch(after_artifact, scenarios)
    changes = [{"name": a["name"], "before": a["status"], "after": b["status"], "after_failure": b["first_failure"]}
               for a, b in zip(old, new) if a["status"] != b["status"]]
    return {"status": "regression" if any(c["after"] == "fail" for c in changes) else "no_new_failure",
            "profile": profile, "before_sha256": before_artifact.sha256, "after_sha256": after_artifact.sha256,
            "new_failures": sum(c["after"] == "fail" for c in changes),
            "resolved_failures": sum(c["after"] == "pass" for c in changes),
            "both_versions_failed": sum(a["status"] == b["status"] == "fail" for a, b in zip(old, new)),
            "before_summary": summary(old), "after_summary": summary(new), "changes": changes,
            "evidence_scope": EVIDENCE_SCOPE}
