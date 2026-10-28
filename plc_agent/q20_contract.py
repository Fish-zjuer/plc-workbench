"""Q20 v2: bounded response windows, without inventing a kick pulse width.

Each observation consists of this scan's inputs and post-call outputs. Automatic
actions may respond on this scan or the next scan. Mutual exclusion is checked
on every scan. The next station is not injected inside a response window.
"""
from __future__ import annotations

VERSION = "q20-response-windows-v2"
INPUTS = ("Mode ForwardButton ReverseButton SensorFeed SensorWash SensorWeight SensorFiring "
          "SensorOutput washComplete weightComplete weight firingComplete").split()


def scenarios():
    cases = []

    def make(name, events, base=None, windows=None):
        defaults = dict.fromkeys(INPUTS, 0) | (base or {})
        rows = [{"time_ms": i * 10, "inputs": defaults | changes, "expected": expected}
                for i, (changes, expected) in enumerate(events)]
        cases.append({"name": name, "trace": rows,
                      "invariants": [{"not_both": ["MotorForward", "MotorReverse"]}],
                      "response_windows": windows or []})

    make("manual_interlock", [({}, {}), ({"ForwardButton": 1}, {"MotorForward": 1, "MotorReverse": 0}),
         ({"ReverseButton": 1}, {"MotorForward": 0, "MotorReverse": 1}),
         ({"ForwardButton": 1, "ReverseButton": 1}, {}), ({}, {"MotorForward": 0, "MotorReverse": 0})])
    for weight in (99, 100, 150, 200, 201):
        events = [({}, {}), ({"SensorFeed": 1}, {}), ({}, {}), ({}, {"MotorForward": 1}),
                  ({"SensorWash": 1}, {}), ({"SensorWash": 1}, {}),
                  ({"SensorWash": 1, "washComplete": 1}, {}), ({"SensorWash": 1}, {}),
                  ({}, {"MotorForward": 1}), ({"SensorWeight": 1}, {}), ({"SensorWeight": 1}, {}),
                  ({"SensorWeight": 1, "weightComplete": 1}, {}), ({"SensorWeight": 1}, {})]
        windows = [window(1, {"MotorForward": 1}, "feed_start"),
                   window(4, {"MotorForward": 0}, "wash_stop"),
                   window(6, {"MotorForward": 1}, "wash_restart"),
                   window(9, {"MotorForward": 0}, "weight_stop")]
        if 100 <= weight <= 200:
            windows += [window(11, {"firingTemp": 500 + (weight - 100) * .5,
                                   "MotorForward": 1, "kick": 0}, "qualified_departure")]
            events += [({}, {"MotorForward": 1}), ({"SensorFiring": 1}, {}),
                       ({"SensorFiring": 1}, {}), ({"SensorFiring": 1}, {"MotorForward": 0}),
                       ({"SensorFiring": 1, "firingComplete": 1}, {}), ({"SensorFiring": 1}, {}),
                       ({}, {"MotorForward": 1}), ({"SensorOutput": 1}, {}), ({"SensorOutput": 1}, {}),
                       ({"SensorOutput": 1}, {"MotorForward": 0, "CompletionLight": 1}),
                       ({}, {}), ({}, {}), ({}, {"CompletionLight": 0})]
            windows += [window(14, {"MotorForward": 0}, "firing_stop"),
                        window(17, {"MotorForward": 1}, "firing_restart"),
                        window(20, {"MotorForward": 0, "CompletionLight": 1}, "finished_arrival"),
                        window(23, {"CompletionLight": 0}, "product_removed")]
        else:
            windows += [window(11, {"kick": 1}, "reject_command")]
            # No duration/reset requirement is scored: the question specifies
            # issuing kick, but neither pulse width nor its reset event.
            events += [({"SensorWeight": 1}, {}), ({}, {}), ({}, {})]
        make(f"weight_boundary_{weight}", events, {"Mode": 1, "weight": weight}, windows)
    return cases


def window(start, expected, name):
    return {"name": name, "start_scan": start, "end_scan": start + 1, "expected": expected}
