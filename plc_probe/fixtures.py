"""Explicit synthetic faults for tool evaluation, not model-generated answers."""
from __future__ import annotations

from pathlib import Path

from .config import ROOT, save_json


def prepare_fixtures() -> list[dict]:
    records = []
    for profile in ("motor", "blower", "edges"):
        directory = ROOT / "examples" / profile
        correct = (directory / "correct.st").read_text(encoding="utf-8")
        for variant in ("correct", "alternative"):
            records.append({"profile": profile, "variant": variant, "kind": "control",
                            "source": str(directory / f"{variant}.st"), "description": "人工编写的不同风格正确实现"})
        if profile == "motor":
            mutations = [
                ("lost_latch", "松开启动后丢失运行保持", "ELSIF StartBtn THEN\n    Motor := TRUE;\nEND_IF;",
                 "ELSIF StartBtn THEN\n    Motor := TRUE;\nELSE\n    Motor := FALSE;\nEND_IF;"),
                ("start_over_stop", "同时输入时启动覆盖停止", "IF StopBtn OR EStop THEN\n    Motor := FALSE;\nELSIF StartBtn THEN\n    Motor := TRUE;",
                 "IF StartBtn THEN\n    Motor := TRUE;\nELSIF StopBtn OR EStop THEN\n    Motor := FALSE;"),
                ("ignore_estop", "遗漏急停输入", "IF StopBtn OR EStop THEN", "IF StopBtn THEN"),
            ]
        elif profile == "blower":
            call = "startDelay(IN := DO_LOW AND AERATION_E_STOP_NC, PT := T#5s);"
            mutations = [
                ("timer_not_reset", "条件失效时未调用 TON，旧计时状态被保留", call,
                 "IF DO_LOW AND AERATION_E_STOP_NC THEN\n    startDelay(IN := TRUE, PT := T#5s);\nEND_IF;"),
                ("timer_ignores_demand", "计时只看急停允许，空闲时间被算入启动延时", call,
                 "startDelay(IN := AERATION_E_STOP_NC, PT := T#5s);"),
                ("ignore_estop", "运行及计时均遗漏急停条件", "DO_LOW AND AERATION_E_STOP_NC", "DO_LOW"),
                ("count_each_scan", "连续运行时每个扫描周期重复计数", "IF BLOWER_RUN AND NOT previousRun THEN", "IF BLOWER_RUN THEN"),
                ("early_delay", "错误使用四秒启动延时", "PT := T#5s", "PT := T#4s"),
            ]
        else:
            mutations = [
                ("count_only_16_bits", "边沿个数只统计低十六位", "0 TO 31 DO", "0 TO 15 DO"),
                ("missing_falling_count", "下降沿个数始终为零", "noOfFallingBits := noOfFallingBits + 1;", "noOfFallingBits := 0;"),
                ("latched_changed_flag", "变化标志被错误锁存", "hasChanged := value <> previousValue;", "hasChanged := hasChanged OR (value <> previousValue);"),
                ("previous_updated_early", "计算边沿前就覆盖历史值", "risingBits := value AND NOT previousValue;", "previousValue := value;\nrisingBits := value AND NOT previousValue;"),
            ]
        for name, description, old, new in mutations:
            if old not in correct:
                raise RuntimeError(f"Mutation no longer applies: {profile}/{name}")
            source = "(* SYNTHETIC FAULT: " + name + " -- deliberately incorrect. *)\n" + correct.replace(old, new)
            path = directory / "mutants" / f"{name}.st"
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.read_text(encoding="utf-8") != source:
                raise RuntimeError(f"Refusing to overwrite an edited fixture: {path}")
            path.write_text(source, encoding="utf-8")
            records.append({"profile": profile, "variant": name, "kind": "synthetic_fault", "source": str(path), "description": description})
    save_json(ROOT / "examples" / "manifest.json", records)
    return records
