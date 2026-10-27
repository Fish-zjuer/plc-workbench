from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape
import json
from pathlib import Path
import sys
import time

from .backend import BackendError, compile_source, run_batch
from .config import ROOT, doctor, save_json
from .fixtures import prepare_fixtures
from .scenarios import generate
from .tools import EVIDENCE_SCOPE, minimize_failure, replay, summary


def demo(output: Path | None = None, seed: int = 20261026) -> dict:
    output = output or ROOT / "reports" / "latest"
    output.mkdir(parents=True, exist_ok=True)
    started, matrix = time.perf_counter(), []
    for fixture in prepare_fixtures():
        key = fixture["profile"] + "__" + fixture["variant"]
        print(f"Testing {key}", file=sys.stderr, flush=True)
        item = dict(fixture)
        try:
            artifact = compile_source(fixture["source"], fixture["profile"])
            item.update({"compile_status": "pass", "source_sha256": artifact.sha256,
                         "build_evidence": str(artifact.directory / "build.json")})
            selected = None
            for suite in ("normal", "focused", "random"):
                results = run_batch(artifact, generate(fixture["profile"], suite, seed))
                item[suite] = summary(results)
                if suite == "focused":
                    selected = next((r for r in results if r["first_failure"]), None)
            if selected:
                counterexample = minimize_failure(artifact, selected)
                verified = replay(fixture["source"], counterexample)
                if not verified["reproduced"]:
                    raise RuntimeError("Fresh-process replay did not reproduce failure")
                save_json(output / "counterexamples" / f"{key}.json", counterexample)
                item["counterexample"] = {"path": f"counterexamples/{key}.json",
                                          "original_scans": counterexample["original_failure_prefix_scans"],
                                          "minimized_scans": counterexample["minimized_scans"],
                                          "property": counterexample["target_property"],
                                          "reproduced": True}
        except BackendError as exc:
            item.update({"compile_status": item.get("compile_status", "error"), "backend_error": exc.result})
        matrix.append(item)
        save_json(output / "progress.json", matrix)
    faults = [m for m in matrix if m["kind"] == "synthetic_fault"]
    controls = [m for m in matrix if m["kind"] == "control"]
    result = {
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(), "seed": seed,
        "experiment": "Synthetic mutation study of three small PLC contracts; no LLM comparison was run",
        "evidence_scope": EVIDENCE_SCOPE, "environment": doctor(),
        "counts": {
            "controls": len(controls), "synthetic_faults": len(faults),
            "compiled": sum(m.get("compile_status") == "pass" for m in matrix),
            "normal_detected": sum(m.get("normal", {}).get("failed", 0) > 0 for m in faults),
            "focused_detected": sum(m.get("focused", {}).get("failed", 0) > 0 for m in faults),
            "random_detected": sum(m.get("random", {}).get("failed", 0) > 0 for m in faults),
            "controls_with_failure": sum(any(m.get(s, {}).get("failed", 0) for s in ("normal", "focused", "random")) for m in controls),
            "counterexamples_reproduced": sum(m.get("counterexample", {}).get("reproduced", False) for m in matrix),
            "total_scans": sum(m.get(s, {}).get("scans", 0) for m in matrix for s in ("normal", "focused", "random")),
        },
        "duration_seconds": round(time.perf_counter() - started, 3), "matrix": matrix,
    }
    save_json(output / "results.json", result)
    render_report(result, output)
    return {"status": "completed", "output": str(output), "counts": result["counts"], "duration_seconds": result["duration_seconds"]}


def render_report(result: dict, output: Path) -> None:
    counts = result["counts"]
    markdown = [
        "# PLC 工具原型：第一轮实测", "", f"运行时间：{result['generated_at']}。固定种子：{result['seed']}。", "",
        "## 这轮做了什么", "",
        "实际编译并执行 ST 源码。后端是 STruC++ 0.7.0 和 g++；输出由独立手写的逐扫描契约检查器判断。",
        "覆盖作业中的电机启停示例、公共题 06 风机延时启动、公共题 02 DWORD 边沿检测。", "",
        "样本是人工构造的正确实现与故意植入错误的实现，**不是模型生成效果、工业现场故障统计或完整作业实验**。", "",
        "## 实测计数", "",
        f"- 编译成功：{counts['compiled']} / {counts['controls'] + counts['synthetic_faults']}。",
        f"- 正确对照：{counts['controls']} 个；出现测试失败的对照：{counts['controls_with_failure']} 个。",
        f"- 人工故障样本：{counts['synthetic_faults']} 个。",
        f"- 正常路径检出：{counts['normal_detected']} 个。",
        f"- 针对性场景检出：{counts['focused_detected']} 个。",
        f"- 固定种子随机场景检出：{counts['random_detected']} 个。",
        f"- 已精简并在新进程复现的反例：{counts['counterexamples_reproduced']} 个。",
        f"- 实际执行扫描总数：{counts['total_scans']}；本次运行耗时 {result['duration_seconds']} 秒（受构建缓存影响）。", "",
        "正常路径、针对性和随机套件的场景数不同；这轮只能说明具体场景能否揭露这些人工故障，不能归因于生成策略优劣或宣称公平预算下更高效。", "",
        "## 样本结果", "",
        "| 任务/实现 | 样本性质 | 正常路径 | 针对性场景 | 随机场景 | 精简反例 |",
        "|---|---|---|---|---|---|",
    ]
    html_rows = []
    for m in result["matrix"]:
        def cell(suite: str) -> str:
            s = m.get(suite)
            return "未执行" if s is None else f"{s['failed']} / {s['scenarios']} 失败"
        ce = m.get("counterexample")
        link = f"[{ce['original_scans']} → {ce['minimized_scans']} 轮]({ce['path']})" if ce else "—"
        label = m["profile"] + "/" + m["variant"]
        kind = "正确对照" if m["kind"] == "control" else "人工故障"
        markdown.append(f"| {label} | {kind} | {cell('normal')} | {cell('focused')} | {cell('random')} | {link} |")
        html_rows.append(f"<tr><td>{escape(label)}</td><td>{kind}</td><td>{cell('normal')}</td><td>{cell('focused')}</td><td>{cell('random')}</td><td>{escape(m['description'])}</td></tr>")
    budget_html = ""
    if "budget_study" in result:
        markdown.extend(["", "## 相同扫描调用预算的后续比较", "",
                         "每个实现分别使用 12、48、192 次 FB 调用，10 个固定种子。下表是每轮检出的人工故障个数（共 12 个）的均值。",
                         "只对齐调用数，没有对齐虚拟时间跨度、复位次数或实际耗时；针对性场景与人工故障也并非独立工业数据。", "",
                         "| 每个实现的扫描预算 | 策略 | 平均检出 / 12 | 最少—最多 |", "|---|---|---|---|"])
        parts = []
        for row in result["budget_study"]["summary"]:
            strategy = "针对性" if row["strategy"] == "focused" else "随机"
            markdown.append(f"| {row['scan_budget_per_implementation']} | {strategy} | {row['mean_detected_faults_out_of_12']} | {row['min']}—{row['max']} |")
            parts.append(f"<tr><td>{row['scan_budget_per_implementation']}</td><td>{strategy}</td><td>{row['mean_detected_faults_out_of_12']} / 12</td><td>{row['min']}—{row['max']}</td></tr>")
        budget_html = '<div class="card"><h2>相同扫描调用预算：10 个固定种子</h2><p>仅对齐每个实现的 FB 调用次数；虚拟时间跨度、复位次数及耗时并未对齐。样本仍是人工故障。</p><table><thead><tr><th>每实现调用预算</th><th>策略</th><th>平均检出</th><th>最少—最多</th></tr></thead><tbody>' + ''.join(parts) + '</tbody></table></div>'
    markdown.extend([
        "", "## 初步结论及边界", "",
        "1. 先观察正常运行不足以评价这些有状态程序：中断、重复输入和高位边界能揭露额外错误。",
        "2. 反例可保存为带绝对采样时间的输入序列，缩短后重放；它适合作为 agent 修复反馈及回归用例。",
        "3. 目前没有运行 CODESYS 编译、PLCVerif、实体 PLC 或任何基座模型；没有完成四组作业实验。",
        "4. 当前只支持三个固定接口契约。任意 ST 程序可以交给后端编译，但没有契约就无法自动判断行为正确。",
        "5. 计时以虚拟时间为准；输出取本轮执行后值。输入在相邻采样点之间保持不变。没有测试多任务抢占、实际 I/O 或重启持久化。",
        "6. 边沿检测题没有定义首轮历史值，首轮只建立观测历史，不判正确性。没有替题目补充隐含要求。",
        "7. 对照均通过不是通用误报率证明；人工故障检出率也不能外推到工业现场。还需要第三方实现、独立盲测和真实问题案例。",
        "8. 下一步优先接 CODESYS 执行后端，对同一反例交叉重放；再测试真实 agent 输出，而非继续增加自造故障。", "",
        "## 可追溯文件", "",
        "- `results.json`：源代码 SHA256、每个场景结论、构建日志位置、环境。",
        "- `counterexamples/*.json`：精简输入、逐轮实际/预期输出、违反的性质及重放状态。",
        "- `../../examples/manifest.json`：人工故障定义及全部 ST 源码位置。",
        "- `../../docs/CONTRACTS.md`：扫描语义、时间约定、规约与假设。", "",
    ])
    (output / "report.md").write_text("\n".join(markdown), encoding="utf-8")
    selected_key = "blower__timer_not_reset"
    ce_path = output / "counterexamples" / (selected_key + ".json")
    payload = json.loads(ce_path.read_text(encoding="utf-8")) if ce_path.exists() else None
    trace_rows = ""
    if payload:
        for row in payload["result"]["rows"]:
            trace_rows += "<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in [
                row["time_ms"], row["inputs"], row["actual"], row["expected"],
                ", ".join(v["property"] for v in row["violations"]),
            ]) + "</tr>"
    html = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>PLC 工具实测</title>
<style>body{{font:15px/1.7 system-ui,sans-serif;max-width:1250px;margin:40px auto;padding:0 24px;color:#182e38;background:#f7f9fb}}h1{{font-size:30px}}.card{{background:white;border:1px solid #dbe3ea;border-radius:12px;padding:20px;margin:20px 0}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{text-align:left;padding:9px;border-bottom:1px solid #e3e9ef;vertical-align:top}}th{{background:#eff4f7}}.metrics{{display:flex;flex-wrap:wrap;gap:16px}}.metric{{flex:1;background:white;padding:20px;border:1px solid #dbe3ea;border-radius:12px}}.metric b{{display:block;font-size:27px;color:#176c62}}.muted{{color:#586b77}}input{{padding:10px;border:1px solid #bacad6;border-radius:6px;width:300px}}.scroll{{overflow-x:auto}}code{{background:#edf2f6;padding:2px 5px}}</style>
<h1>PLC 工具：第一轮实测</h1><p class="muted">{escape(result['generated_at'])} · STruC++ 0.7.0 + g++ · 固定种子 {result['seed']}</p>
<div class="metrics"><div class="metric">正常路径检出人工故障<b>{counts['normal_detected']} / {counts['synthetic_faults']}</b></div><div class="metric">针对性场景检出人工故障<b>{counts['focused_detected']} / {counts['synthetic_faults']}</b></div><div class="metric">正确对照出现失败<b>{counts['controls_with_failure']} / {counts['controls']}</b></div><div class="metric">反例成功重放<b>{counts['counterexamples_reproduced']}</b></div></div>
<div class="card"><strong>证据边界</strong><p>这是人工故障样本的离线有限轨迹测试。没有运行 CODESYS、形式化验证器、实体 PLC 或 LLM。套件预算不同，不构成生成策略效率比较，也不能推断工业故障检出率。</p></div>
<div class="card"><h2>急停中断后保留了旧计时：精简反例</h2><p>需求明确规定：恢复后重新等待完整五秒。下表输出均为本轮执行后的值。</p><div class="scroll"><table><thead><tr><th>时间 ms</th><th>输入</th><th>实际输出</th><th>预期输出</th><th>违反性质</th></tr></thead><tbody>{trace_rows}</tbody></table></div></div>
{budget_html}<div class="card"><h2>全部样本</h2><input id="filter" placeholder="筛选：motor / blower / edges / 故障名称"><div class="scroll"><table id="matrix"><thead><tr><th>实现</th><th>类型</th><th>正常路径</th><th>针对性</th><th>随机</th><th>故障说明</th></tr></thead><tbody>{''.join(html_rows)}</tbody></table></div></div>
<p>详细证据：<a href="report.md">实验记录</a> · <a href="results.json">原始 JSON</a></p>
<script>document.getElementById('filter').addEventListener('input',function(){{const q=this.value.toLowerCase();document.querySelectorAll('#matrix tbody tr').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q));}});</script></html>'''
    (output / "report.html").write_text(html, encoding="utf-8")
