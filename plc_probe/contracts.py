"""Independent, stateful output oracles. They do not interpret the ST program.

Rows contain inputs sampled at time t and outputs after that invocation. Input
values are assumed constant between samples. A timer starts at its first true
sample (elapsed = 0). Clock is simulated milliseconds, never wall clock.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

MONITOR_VERSION = "1"


@dataclass(frozen=True)
class Profile:
    block: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    input_bounds: tuple[tuple[int, int], ...]
    provenance: str
    input_kinds: tuple[str, ...] = ()
    output_kinds: tuple[str, ...] = ()


PROFILES = {
    "motor": Profile("MOTORCONTROL", ("StartBtn", "StopBtn", "EStop"), ("Motor",), ((0, 1),) * 3,
                     "Assignment motor start/stop example; EStop=TRUE means active."),
    "blower": Profile("BLOWERCONTROL", ("DO_LOW", "AERATION_E_STOP_NC"),
                      ("BLOWER_RUN", "AERATION_BLOWER_CYCLE_COUNT"), ((0, 1),) * 2,
                      "Public question 06; AERATION_E_STOP_NC=TRUE permits operation."),
    "edges": Profile("EDGEDETECTION", ("value",),
                     ("hasChanged", "hasRisingEdges", "risingBits", "noOfRisingBits",
                      "hasFallingEdges", "fallingBits", "noOfFallingBits"), ((0, 0xFFFFFFFF),),
                     "Public question 02. First invocation is not scored: its previous-value policy is unspecified."),
    "moving_average": Profile("MOVINGAVERAGE", ("cyclicExecution", "trigger", "value", "windowSize", "reset"),
                              ("average", "windowSizeReached", "error", "status"),
                              ((0, 1), (0, 1), (-1e9, 1e9), (-32768, 32767), (0, 1)),
                              "Public question 09. Window changes only between fresh instances; reset samples have no sample request. Empty averages are not scored.",
                              ("int", "int", "float", "int", "int"), ("float", "int", "int", "int")),
    "ipv4": Profile("IPV4PARSER", ("ipText",), ("ipValue",), ((0, 254),),
                    "Public question 14. Printable ASCII inputs only; invalid text must clear a previous valid result.",
                    ("str",), ("int",)),
}

PROPERTY_TEXT = {
    "motor.stop_priority": "停止或急停输入有效时，本轮执行后的电机指令应关闭。",
    "motor.start": "启动有效且停止、急停均无效时，电机指令应开启。",
    "motor.hold": "没有新启动或停止事件时，应保持原运行状态。",
    "blower.permissive": "需求消失或急停有效时，风机指令应立即关闭。",
    "blower.no_early_start": "每段连续有效需求均须等待完整 5000 ms。",
    "blower.start_after_delay": "允许条件连续满足 5000 ms 后，风机应启动。",
    "blower.start_count": "只在实际运行指令由 FALSE 变为 TRUE 时增加一次启动计数。",
    "edges.changed": "hasChanged 应反映 DWORD 与上轮输入是否不同。",
    "edges.rising_flag": "hasRisingEdges 应反映是否至少有一个上升沿。",
    "edges.rising_mask": "risingBits 应精确标记 32 位输入的上升沿。",
    "edges.rising_count": "上升沿计数应包含全部 32 位。",
    "edges.falling_flag": "hasFallingEdges 应反映是否至少有一个下降沿。",
    "edges.falling_mask": "fallingBits 应精确标记 32 位输入的下降沿。",
    "edges.falling_count": "下降沿计数应包含全部 32 位。",
    "moving_average.mean": "新采样后输出应为最近窗口内已采集样本的算术平均；无采样时保持。",
    "moving_average.window": "windowSizeReached 应反映是否已收集到完整窗口的样本。",
    "moving_average.error": "窗口长度不在 1..100 时必须报告错误，合法设置正常执行时不得报错。",
    "moving_average.status": "非法窗口使用 16#8200，正常执行使用 16#0000。",
    "ipv4.value": "合法四段十进制地址按网络字节序组装；非法文本须将结果清零。",
}


class Monitor:
    def __init__(self, profile: str):
        self.profile = profile
        self.running = False
        self.enabled_since: int | None = None
        self.count = 0
        self.previous_word: int | None = None
        self.samples: list[float] = []
        self.previous_trigger = False

    def observe(self, row: dict, actual: dict) -> tuple[dict, list[dict]]:
        inputs = row["inputs"]
        properties: list[str]
        if self.profile == "motor":
            if inputs["StopBtn"] or inputs["EStop"]:
                self.running = False
                prop = "motor.stop_priority"
            elif inputs["StartBtn"]:
                self.running = True
                prop = "motor.start"
            else:
                prop = "motor.hold"
            expected = {"Motor": int(self.running)}
            properties = [prop]
        elif self.profile == "blower":
            permit = bool(inputs["DO_LOW"] and inputs["AERATION_E_STOP_NC"])
            if not permit:
                self.enabled_since = None
            elif self.enabled_since is None:
                self.enabled_since = row["time_ms"]
            elapsed = 0 if self.enabled_since is None else row["time_ms"] - self.enabled_since
            running = permit and elapsed >= 5000
            if running and not self.running:
                self.count = (self.count + 1) % 65536
            self.running = running
            prop = ("blower.permissive" if not permit else
                    "blower.start_after_delay" if running else "blower.no_early_start")
            expected = {"BLOWER_RUN": int(running), "AERATION_BLOWER_CYCLE_COUNT": self.count}
            properties = [prop, "blower.start_count"]
        elif self.profile == "moving_average":
            size = inputs["windowSize"]
            expected = {}
            property_map = {}
            if not 1 <= size <= 100:
                expected = {"error": 1, "status": 0x8200}
                property_map = {"error": "moving_average.error", "status": "moving_average.status"}
            else:
                if inputs["reset"]:
                    self.samples.clear()
                elif inputs["cyclicExecution"] or (inputs["trigger"] and not self.previous_trigger):
                    self.samples.append(float(inputs["value"]))
                    self.samples = self.samples[-size:]
                expected.update({"windowSizeReached": int(len(self.samples) == size), "error": 0, "status": 0})
                property_map.update({"windowSizeReached": "moving_average.window", "error": "moving_average.error", "status": "moving_average.status"})
                if self.samples:
                    expected["average"] = math.fsum(self.samples) / len(self.samples)
                    property_map["average"] = "moving_average.mean"
            self.previous_trigger = bool(inputs["trigger"])
            properties = [property_map[key] for key in expected]
        elif self.profile == "ipv4":
            parts = inputs["ipText"].split(".")
            valid = len(parts) == 4 and all(p and p.isascii() and p.isdigit() and int(p) <= 255 for p in parts)
            value = 0
            if valid:
                for part in parts:
                    value = (value << 8) | int(part)
            expected = {"ipValue": value}
            properties = ["ipv4.value"]
        else:
            current = inputs["value"]
            if self.previous_word is None:
                self.previous_word = current
                return {}, []
            rising = current & ~self.previous_word & 0xFFFFFFFF
            falling = self.previous_word & ~current & 0xFFFFFFFF
            expected = dict(zip(PROFILES["edges"].outputs, [
                int(current != self.previous_word), int(rising != 0), rising, rising.bit_count(),
                int(falling != 0), falling, falling.bit_count(),
            ]))
            self.previous_word = current
            properties = ["edges.changed", "edges.rising_flag", "edges.rising_mask", "edges.rising_count",
                          "edges.falling_flag", "edges.falling_mask", "edges.falling_count"]
        violations = [
            {"property": prop, "description": PROPERTY_TEXT[prop], "output": name,
             "expected": value, "actual": actual[name]}
            for (name, value), prop in zip(expected.items(), properties)
            if not (math.isclose(actual[name], value, rel_tol=1e-9, abs_tol=1e-9)
                    if type(value) is float else actual[name] == value)
        ]
        return expected, violations


def validate_trace(profile: str, trace: list[dict]) -> None:
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile: {profile}")
    if not isinstance(trace, list) or not trace or len(trace) > 10000:
        raise ValueError("A trace must contain 1..10000 scans")
    last = -1
    spec = PROFILES[profile]
    for row in trace:
        timestamp = row.get("time_ms")
        if type(timestamp) is not int or timestamp < 0 or timestamp > 86400000 or timestamp <= last:
            raise ValueError("time_ms must be a strictly increasing integer in 0..86400000")
        last = timestamp
        if set(row.get("inputs", {})) != set(spec.inputs):
            raise ValueError(f"Each scan must supply exactly these inputs: {spec.inputs}")
        kinds = spec.input_kinds or ("int",) * len(spec.inputs)
        for name, (low, high), kind in zip(spec.inputs, spec.input_bounds, kinds):
            value = row["inputs"][name]
            if kind == "str":
                valid = isinstance(value, str) and low <= len(value) <= high and all(32 <= ord(c) <= 126 for c in value)
            elif kind == "float":
                valid = type(value) in (float, int) and math.isfinite(value) and low <= value <= high
            else:
                valid = type(value) in (int, bool) and low <= value <= high
            if not valid:
                raise ValueError(f"Invalid input value for {name}")
