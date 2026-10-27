"""Execute independent review hypotheses without treating model claims as truth.

The reviewer writes data, never executable assertions. A separate adjudication
records the requirement basis. Existing monitors remain unchanged. Every finding
is replayed twice in fresh processes; sparse expectations are not delta-shrunk.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path

from .backend import BackendError, compile_source, run_batch
from .config import ROOT, save_json
from .contracts import MONITOR_VERSION, PROFILES, validate_trace
from .tools import EVIDENCE_SCOPE


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: str | Path) -> dict:
    path = Path(path)
    if path.stat().st_size > 2_000_000:
        raise ValueError("Review data exceeds 2 MB")
    value = json.loads(path.read_text(encoding="utf-8"),
                       parse_constant=lambda s: (_ for _ in ()).throw(ValueError(f"Invalid number: {s}")))
    if not isinstance(value, dict):
        raise ValueError("Review data must be an object")
    return value


def _equal(a: float, b: float, floating: bool) -> bool:
    return (math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9) if floating else a == b)


def validate_proposals(plan: dict) -> dict:
    if plan.get("schema") != "plc-probe-review-v1":
        raise ValueError("Unsupported review schema")
    candidates, findings = plan.get("candidates"), plan.get("findings")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= len(PROFILES):
        raise ValueError("Expected 1..5 candidates")
    if not isinstance(findings, list) or len(findings) > 20:
        raise ValueError("Expected at most 20 findings")
    sources = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("Candidate must be an object")
        profile = candidate.get("profile")
        if profile not in PROFILES or profile in sources:
            raise ValueError("Unknown or duplicate candidate profile")
        source = Path(candidate["source"])
        if not source.is_absolute() or source.suffix.lower() != ".st":
            raise ValueError("Candidate must be an absolute .st path")
        if source.stat().st_size > 2_000_000:
            raise ValueError("Source exceeds 2 MB")
        if _sha(source) != candidate.get("source_sha256"):
            raise ValueError(f"Stale source hash for {profile}; create a new review manifest")
        sources[profile] = candidate
    seen, scans = set(), 0
    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError("Finding must be an object")
        ident, profile = finding.get("id"), finding.get("profile")
        if not isinstance(ident, str) or not ident or len(ident) > 80 or ident in seen:
            raise ValueError("Finding IDs must be unique nonempty strings of at most 80 characters")
        seen.add(ident)
        if profile not in sources:
            raise ValueError("Finding references an unknown candidate")
        for field in ("title", "claim", "requirement_basis", "rationale"):
            if not isinstance(finding.get(field), str) or not finding[field].strip():
                raise ValueError(f"Finding lacks {field}")
        if finding.get("scope") not in ("specified", "ambiguous", "outside_supported_domain"):
            raise ValueError("Unknown proposed scope")
        if not isinstance(finding.get("scenario"), dict):
            raise ValueError("Scenario must be an object")
        trace = finding["scenario"]["trace"]
        if not isinstance(trace, list) or any(not isinstance(r, dict) for r in trace):
            raise ValueError("Trace must contain scan objects")
        validate_trace(profile, trace)
        scans += len(trace)
        assertions = finding.get("assertions")
        if not isinstance(assertions, list) or not 1 <= len(assertions) <= 1000:
            raise ValueError("Expected 1..1000 sparse assertions per finding")
        spec = PROFILES[profile]
        kinds = dict(zip(spec.outputs, spec.output_kinds or ("int",) * len(spec.outputs)))
        for assertion in assertions:
            if not isinstance(assertion, dict):
                raise ValueError("Assertion must be an object")
            scan, output, expected = assertion.get("scan"), assertion.get("output"), assertion.get("expected")
            if type(scan) is not int or not 0 <= scan < len(trace) or output not in kinds:
                raise ValueError("Invalid assertion scan or output")
            if type(expected) not in (int, float, bool) or not math.isfinite(expected):
                raise ValueError("Expected output must be a finite number or boolean")
            if kinds[output] != "float" and type(expected) is float:
                raise ValueError("Integer output requires an integer expectation")
    if scans > 10000:
        raise ValueError("Review exceeds 10000 total scans")
    return sources


def _judgements(data: dict, ids: set[str]) -> dict:
    if data.get("schema") != "plc-probe-adjudication-v1":
        raise ValueError("Unsupported adjudication schema")
    result = {}
    if not isinstance(data.get("decisions"), list):
        raise ValueError("Adjudication decisions must be a list")
    for item in data["decisions"]:
        if not isinstance(item, dict):
            raise ValueError("Adjudication decision must be an object")
        ident = item.get("id")
        if ident not in ids or ident in result:
            raise ValueError("Unknown or duplicate adjudication ID")
        if item.get("decision") not in ("accept_requirement", "accept_contract", "ambiguous", "reject"):
            raise ValueError("Invalid adjudication decision")
        if not isinstance(item.get("reason"), str) or not item["reason"].strip():
            raise ValueError("Adjudication requires an explicit reason")
        result[ident] = item
    return result


def _checks(finding: dict, result: dict) -> list[dict]:
    spec = PROFILES[finding["profile"]]
    kinds = dict(zip(spec.outputs, spec.output_kinds or ("int",) * len(spec.outputs)))
    checks = []
    for assertion in finding["assertions"]:
        row, output = result["rows"][assertion["scan"]], assertion["output"]
        actual, proposed = row["actual"][output], assertion["expected"]
        scored = output in row["expected"]
        checks.append({**assertion, "actual": actual,
                       "matches_assertion": _equal(actual, proposed, kinds[output] == "float"),
                       "monitor_scored": scored,
                       "monitor_expected": row["expected"].get(output),
                       "oracle_agrees": scored and _equal(row["expected"][output], proposed, kinds[output] == "float"),
                       "monitor_properties": [v["property"] for v in row["violations"] if v["output"] == output]})
    return checks


def review(proposals_path: str, adjudication_path: str | None = None,
           output: str | None = None) -> dict:
    plan = _read(proposals_path)
    sources = validate_proposals(plan)
    decisions = _judgements(_read(adjudication_path), {f["id"] for f in plan["findings"]}) if adjudication_path else {}
    report_path = Path(output).resolve() if output else Path(proposals_path).resolve().parent / "evaluation.json"
    protected = {Path(proposals_path).resolve(), *(Path(c["source"]).resolve() for c in sources.values())}
    if adjudication_path:
        protected.add(Path(adjudication_path).resolve())
    if report_path.suffix.lower() != ".json" or report_path in protected or report_path.with_suffix(".md") in protected:
        raise ValueError("Review output must be a separate .json file")
    evidence_dir = report_path.parent / (report_path.stem + "_evidence")
    results, artifacts, backend_errors = [], {}, {}
    for index, finding in enumerate(plan["findings"]):
        profile, ident = finding["profile"], finding["id"]
        source, judgement = sources[profile], decisions.get(ident)
        item = {"id": ident, "profile": profile, "title": finding["title"],
                "proposed_scope": finding["scope"], "adjudication": judgement,
                "source_sha256": source["source_sha256"]}
        try:
            if profile in backend_errors:
                raise BackendError(backend_errors[profile])
            if profile not in artifacts:
                artifacts[profile] = compile_source(source["source"], profile)
            artifact = artifacts[profile]
            if artifact.sha256 != source["source_sha256"]:
                raise ValueError("Source changed during review")
            scenario = {**finding["scenario"], "name": finding["scenario"].get("name", ident), "family": "independent_adversarial"}
            runs = [run_batch(artifact, [scenario])[0] for _ in range(2)]
            checks = [_checks(finding, result) for result in runs]
            stable = [r["rows"] for r in runs][0] == [r["rows"] for r in runs][1]
            failed = [[i for i, c in enumerate(run) if not c["matches_assertion"]] for run in checks]
            replicated = sorted(set(failed[0]) & set(failed[1]))
            item.update({"fresh_process_replays": 2, "stable": stable,
                         "assertion_mismatch_reproduced": bool(replicated), "checks": checks[0],
                         "monitor_failed_in_trace": any(r["first_failure"] for r in runs)})
            decision = judgement["decision"] if judgement else None
            if decision == "reject":
                status = "rejected_hypothesis"
            elif decision == "ambiguous":
                status = "needs_requirement_clarification"
            elif not stable:
                status = "unstable_execution"
            elif decision is None:
                status = "pending_adjudication"
            elif any(not c["oracle_agrees"] for c in checks[0]):
                status = "oracle_disagreement"
            elif replicated:
                status = "confirmed_requirement_violation" if decision == "accept_requirement" else "confirmed_contract_violation"
            else:
                status = "not_reproduced"
            item["status"] = status
            evidence_path = evidence_dir / f"finding_{index + 1:02d}.json"
            save_json(evidence_path, {"schema": "plc-probe-review-evidence-v1", "finding": finding,
                                     "candidate": source, "adjudication": judgement, "status": status,
                                     "monitor_version": MONITOR_VERSION, "runs": runs, "assertion_checks": checks,
                                     "build_evidence": str(artifact.directory / "build.json"),
                                     "replay_note": "Exact original trace; no deletion minimization of sparse assertions.",
                                     "evidence_scope": EVIDENCE_SCOPE})
            item["evidence_path"] = str(evidence_path)
        except BackendError as exc:
            if exc.result.get("status") in ("compile_error", "missing_dependency"):
                backend_errors[profile] = exc.result
            item.update({"status": "backend_error", "backend_error": exc.result})
        results.append(item)
    counts = dict(Counter(r["status"] for r in results))
    confirmed = sum(n for key, n in counts.items() if key.startswith("confirmed_"))
    unresolved = sum(counts.get(key, 0) for key in ("pending_adjudication", "needs_requirement_clarification",
                                                 "oracle_disagreement", "unstable_execution", "backend_error"))
    report = {"schema": "plc-probe-review-results-v1",
              "status": "fail" if confirmed else "needs_review" if unresolved else "no_confirmed_counterexample",
              "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
              "reviewer": plan.get("reviewer"), "proposals_path": str(Path(proposals_path).resolve()),
              "proposals_sha256": _sha(Path(proposals_path)), "candidates": list(sources.values()),
              "adjudication_path": str(Path(adjudication_path).resolve()) if adjudication_path else None,
              "adjudication_sha256": _sha(Path(adjudication_path)) if adjudication_path else None,
              "monitor_version": MONITOR_VERSION,
              "monitor_sha256": _sha(ROOT / "plc_probe/contracts.py"),
              "comparison_tolerance": {"relative": 1e-9, "absolute": 1e-9},
              "counts": {"proposals": len(results), "confirmed": confirmed, "unresolved": unresolved, "by_status": counts},
              "findings": results, "evidence_scope": EVIDENCE_SCOPE,
              "limitation": "A model hypothesis and a supplied adjudication are not proof; no confirmed counterexample is not a correctness claim."}
    save_json(report_path, report)
    lines = ["# 独立对抗性审查", "", "独立 Luna 仅阅读题面、输入域及候选源码，不读取既有测试和通过结论。主控按需求依据裁决；原监视器保持不变。", "",
             f"提出 {len(results)} 项假设；确认 {confirmed} 项；待处理 {unresolved} 项。", "",
             "每条可执行轨迹在全新进程中重放两次。数值断言采用既有相对/绝对 1e-9 容差。", "",
             "| ID | 任务 | 假设 | 执行裁决 |", "|---|---|---|---|"]
    for item in results:
        lines.append(f"| {item['id']} | {item['profile']} | {item['title'].replace('|', '/')} | {item['status']} |")
    lines.extend(["", "原始提案、需求裁决、两次逐扫描执行及源码哈希分别留档。没有确认反例不代表正确性证明；题面歧义不计入代码缺陷。", "",
                  "执行后端：STruC++ 0.7.0 + g++；未运行 CODESYS、形式化验证或实体 PLC。"])
    report_path.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {key: report[key] for key in ("status", "counts", "findings", "evidence_scope")} | {"report_path": str(report_path)}
