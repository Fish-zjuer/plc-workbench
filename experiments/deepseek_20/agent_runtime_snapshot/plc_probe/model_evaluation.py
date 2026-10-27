"""Evaluate independently authored model output without rewriting its ST source."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

from .backend import BackendError, compile_source, run_batch
from .adversarial import _read, review, validate_proposals
from .config import ROOT, save_json
from .scenarios import generate
from .tools import EVIDENCE_SCOPE, minimize_failure, replay, summary


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


STAGES = ("first_draft", "repair_1", "repair_2", "adversarial_repair_1")


def evaluate(stage: str, seed: int = 20261027, proposals_path: str | None = None,
             adjudication_path: str | None = None) -> dict:
    if stage not in STAGES:
        raise ValueError("Unsupported generation stage")
    directory = ROOT / "experiments/luna" / stage
    if adjudication_path and not proposals_path:
        raise ValueError("Adjudication requires review proposals")
    if proposals_path:
        sources = validate_proposals(_read(proposals_path))
        for profile, candidate in sources.items():
            if Path(candidate["source"]).resolve() != (directory / (profile + ".st")).resolve():
                raise ValueError("Review candidates must refer to the evaluated generation stage")
    tag = stage + ("_with_review" if proposals_path else "")
    output = ROOT / "experiments/luna/results"
    output.mkdir(parents=True, exist_ok=True)
    matrix, feedback = [], []
    for profile in ("motor", "blower", "edges", "moving_average", "ipv4"):
        source = directory / (profile + ".st")
        item = {"profile": profile, "source": str(source), "source_sha256": sha256(source)}
        try:
            artifact = compile_source(source, profile)
            item["compile_status"] = "pass"
            item["build_evidence"] = str(artifact.directory / "build.json")
            first = None
            for suite in ("normal", "focused", "random"):
                results = run_batch(artifact, generate(profile, suite, seed))
                item[suite] = summary(results)
                if first is None:
                    first = next((r for r in results if r["first_failure"]), None)
            item["behavior_status"] = "fail" if first else "pass"
            if first:
                record = minimize_failure(artifact, first)
                item["counterexample_path"] = str(output / f"{stage}_{profile}_counterexample.json")
                save_json(Path(item["counterexample_path"]), record)
                item["reproduced"] = replay(str(source), record)["reproduced"]
                feedback.append({"profile": profile, "status": "behavior_failure",
                                 "counterexample": {key: record[key] for key in ("target_property", "scenario", "result")}})
            else:
                feedback.append({"profile": profile, "status": "passed_current_finite_tests"})
        except BackendError as exc:
            item["compile_status"] = item.get("compile_status", "error")
            item["behavior_status"] = "not_evaluated" if "normal" not in item else "tool_error"
            item["backend_error"] = exc.result
            feedback.append({"profile": profile, "status": "backend_error", "details": exc.result})
        matrix.append(item)
    report = {
        "requested_model": "gpt-6-luna", "author_agent": "/root/luna_st_author", "stage": stage,
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(), "random_seed": seed,
        "generation_protocol": "First draft: assignment text and interface names only; no reference implementations or test/compiler feedback. Repairs: bounded tool feedback only.",
        "evidence_scope": EVIDENCE_SCOPE,
        "evaluation_code_sha256": {name: sha256(ROOT / "plc_probe" / name) for name in ("contracts.py", "scenarios.py", "backend.py")},
        "counts": {"tasks": len(matrix), "compiled": sum(m["compile_status"] == "pass" for m in matrix),
                   "behavior_passed": sum(m["behavior_status"] == "pass" for m in matrix),
                   "behavior_failed": sum(m["behavior_status"] == "fail" for m in matrix),
                   "not_behavior_evaluated": sum(m["behavior_status"] == "not_evaluated" for m in matrix)},
        "matrix": matrix,
    }
    if proposals_path:
        report["adversarial_review"] = review(proposals_path, adjudication_path)
        report["overall_verdict"] = ("fail" if report["counts"]["behavior_failed"] or report["adversarial_review"]["counts"]["confirmed"]
                                     else "needs_review" if any(m["behavior_status"] != "pass" for m in matrix) or report["adversarial_review"]["counts"]["unresolved"]
                                     else "completed_current_checks")
    save_json(output / (tag + ".json"), report)
    save_json(output / (tag + "_feedback.json"), {
        "backend": "STruC++ 0.7.0 + g++; not CODESYS",
        "sampling": "Inputs at time_ms are used for this invocation; outputs are observed after it. Timer starts at elapsed=0 on the first eligible scan.",
        "task_feedback": feedback,
    })
    lines = ["# Luna 独立生成实测", "", "这组与人工故障自检实验分开记录。生成者为请求指定的 GPT-6 Luna 子代理。", "",
             f"阶段：{stage}；随机种子：{seed}。", "",
             "首稿只提供原题与接口名称，没有提供参考实现、测试目录、预期轨迹或人工故障定义。评估使用既有固定工具；主代理未改写其 ST。", "",
             "| 任务 | 离线编译 | 行为测试 | 正常场景失败 | 针对性失败 | 随机失败 |", "|---|---|---|---|---|---|"]
    for item in matrix:
        cells = [str(item.get(s, {}).get("failed", "未执行")) for s in ("normal", "focused", "random")]
        lines.append(f"| {item['profile']} | {item['compile_status']} | {item['behavior_status']} | {' | '.join(cells)} |")
    if proposals_path:
        lines.extend(["", "追加独立对抗审查：", "", json.dumps(report["adversarial_review"]["counts"], ensure_ascii=False),
                      "", f"完整证据：{report['adversarial_review']['report_path']}",
                      "", f"合并状态：{report['overall_verdict']}。普通测试通过与审查待澄清分别记录。"])
    lines.extend(["", f"边界：只有 {len(matrix)} 道题、每阶段一次生成，没有估计模型总体能力。离线工具链失败需与实际逻辑错误区分，不能直接当作 CODESYS 编译失败。有限轨迹通过也不是形式化证明。", "",
                  "原始代码、源码哈希、逐场景结果和反馈 JSON 均保留在本目录及上级阶段目录中。"])
    (output / (tag + ".md")).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"stage": stage, "counts": report["counts"], "feedback_path": str(output / (tag + "_feedback.json")),
            "adversarial_review": report.get("adversarial_review"), "overall_verdict": report.get("overall_verdict"),
            "tasks": [{"profile": m["profile"], "compile_status": m["compile_status"], "behavior_status": m["behavior_status"],
                       "error": m.get("backend_error")} for m in matrix]}


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument("--review-proposals")
    parser.add_argument("--review-adjudication")
    args = parser.parse_args()
    result = evaluate(args.stage, proposals_path=args.review_proposals,
                      adjudication_path=args.review_adjudication)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["overall_verdict"] in (None, "completed_current_checks") else 1)
