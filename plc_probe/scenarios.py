from __future__ import annotations

import itertools
import random

from .contracts import PROFILES


def scenario(profile: str, name: str, family: str, samples: list[tuple]) -> dict:
    return {"name": name, "family": family, "trace": [
        {"time_ms": sample[0], "inputs": dict(zip(PROFILES[profile].inputs, sample[1:]))}
        for sample in samples
    ]}


def generate(profile: str, suite: str = "focused", seed: int = 20261026) -> list[dict]:
    if profile not in PROFILES or suite not in ("normal", "focused", "random"):
        raise ValueError("Unknown profile or suite")
    if profile == "ipv4":
        if suite == "normal":
            return [scenario(profile, "common_valid_addresses", "normal", [(i * 100, text) for i, text in enumerate([
                "0.0.0.0", "127.0.0.1", "192.168.1.10", "255.255.255.255",
            ])])]
        if suite == "focused":
            invalid = ["", ".", "1.2.3", "1.2.3.4.5", "1..3.4", ".1.2.3.4", "1.2.3.4.",
                       "-1.2.3.4", "+1.2.3.4", " 1.2.3.4", "1.2.3.4 ", "1.2.a.4", "256.2.3.4",
                       "1.256.3.4", "1.2.256.4", "1.2.3.256", "999999999999999999999.1.2.3",
                       "1.2.3.4junk", "1/2/3/4", "0x1.2.3.4", '1.2.3."4', "1.2.3.\\4"]
            valid = ["001.002.003.004", "255.0.0.0", "0.255.0.0", "0.0.255.0", "0.0.0.255"]
            return [scenario(profile, f"address_{i:02}", "format_and_range", [(0, "1.2.3.4"), (100, text), (200, "4.3.2.1")])
                    for i, text in enumerate(invalid + valid)]
        rng = random.Random(seed)
        result = []
        for number in range(40):
            samples = []
            for i in range(100):
                text = ".".join(str(rng.randrange(256)) for _ in range(4))
                if rng.random() < 0.5:
                    text = rng.choice([text + ".", "." + text, text + "x", "256." + text, text.replace(".", "..", 1), " " + text])
                samples.append((i * 100, text))
            result.append(scenario(profile, f"random_{seed}_{number:02}", "random", samples))
        return result
    if profile == "moving_average":
        if suite == "normal":
            return [scenario(profile, "cyclic_window_three", "normal", [(0, 0, 0, 0.0, 3, 1)] +
                             [(i * 100, 1, 0, value, 3, 0) for i, value in enumerate([1.0, 2.0, 3.0, 4.0, 5.0], 1)])]
        if suite == "focused":
            result = []
            for size in (1, 2, 3, 10, 100):
                samples = [(0, 0, 0, 0.0, size, 1)]
                samples += [(i * 100, 1, i % 2, ((i % 7) - 3) * 1.25, size, 0) for i in range(1, size + 6)]
                result.append(scenario(profile, f"cyclic_window_{size}", "window_wrap", samples))
                samples = [(0, 0, 0, 0.0, size, 1)]
                for i, (trigger, value) in enumerate([(1, 10.5), (1, 99.0), (1, -99.0), (0, 1.0), (1, 20.5), (0, 2.0), (1, -4.25)], 1):
                    samples.append((i * 100, 0, trigger, value, size, 0))
                result.append(scenario(profile, f"manual_window_{size}", "trigger_hold", samples))
            for size in (-1, 0, 101, 32767):
                result.append(scenario(profile, f"invalid_window_{size}", "invalid_configuration", [(0, 0, 0, 5.0, size, 0)]))
            result.append(scenario(profile, "reset_after_samples", "reset", [
                (0, 0, 0, 0.0, 3, 1), (100, 1, 0, 9.0, 3, 0), (200, 1, 0, 3.0, 3, 0),
                (300, 0, 0, 0.0, 3, 1), (400, 0, 1, -2.5, 3, 0), (500, 0, 1, 100.0, 3, 0),
            ]))
            return result
        rng = random.Random(seed)
        result = []
        for number in range(40):
            size, previous_mode = rng.choice([1, 2, 3, 10, 100]), False
            samples = [(0, 0, 0, 0.0, size, 1)]
            for i in range(1, 100):
                reset = rng.random() < 0.05
                mode = False if reset else rng.random() < 0.5
                trigger = 0 if reset or mode != previous_mode else rng.randrange(2)
                samples.append((i * 100, int(mode), trigger, rng.randrange(-400, 401) / 4, size, int(reset)))
                previous_mode = mode
            result.append(scenario(profile, f"random_{seed}_{number:02}", "random", samples))
        return result
    if suite == "random":
        rng = random.Random(seed + list(PROFILES).index(profile) * 7919)
        result = []
        for number in range(40):
            timestamp, samples = 0, []
            values = [0] * len(PROFILES[profile].inputs)
            for _ in range(100):
                if profile == "edges":
                    if rng.random() < 0.7:
                        values = [rng.getrandbits(32)]
                elif profile == "motor":
                    values = [rng.randrange(2) for _ in values]
                elif rng.random() < 0.12:
                    values = [rng.randrange(2), rng.randrange(2)]
                samples.append((timestamp, *values))
                timestamp += rng.choice([1, 10, 99, 100, 101, 333, 1000])
            result.append(scenario(profile, f"random_{seed}_{number:02}", "random", samples))
        return result
    if profile == "motor":
        if suite == "normal":
            return [scenario(profile, "start_hold_stop", "normal", [
                (0, 0, 0, 0), (100, 1, 0, 0), (200, 0, 0, 0), (300, 0, 1, 0), (400, 0, 0, 0),
            ])]
        # Bounded enumeration, not an unbounded model-checking proof.
        alphabet = list(itertools.product((0, 1), repeat=3))
        return [scenario(profile, f"all_inputs_depth3_{number:03}", "bounded_all_inputs", [
            (0, 0, 0, 0), *((index * 100, *values) for index, values in enumerate(sequence, 1)),
        ]) for number, sequence in enumerate(itertools.product(alphabet, repeat=3))]
    if profile == "edges":
        if suite == "normal":
            values = [0, 1, 3, 7, 15, 31]
            return [scenario(profile, "low_bits_rising", "normal", [(i * 100, value) for i, value in enumerate(values)])]
        result = []
        for bit in range(32):
            values = [0, 1 << bit, 1 << bit, 0, 0]
            result.append(scenario(profile, f"bit_{bit}_rise_hold_fall", "bit_boundary",
                                   [(i * 100, value) for i, value in enumerate(values)]))
        for name, values in [
            ("all_bits", [0, 0xFFFFFFFF, 0xFFFFFFFF, 0]),
            ("alternating", [0, 0xAAAAAAAA, 0x55555555, 0xAAAAAAAA, 0]),
            ("sign_boundary", [0, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF, 0]),
        ]:
            result.append(scenario(profile, name, "word_boundary", [(i * 100, value) for i, value in enumerate(values)]))
        return result
    if suite == "normal":
        return [scenario(profile, "one_uninterrupted_start", "normal", [
            (0, 0, 0), *((t, 1, 1) for t in range(100, 6200, 100)), (6200, 0, 1),
        ])]
    result = []
    for event, disabled in [("estop", (1, 0)), ("demand_loss", (0, 1))]:
        for offset in [2, 4999, 5000, 5001, 7000]:
            for duration in [1, 100, 5000]:
                interruption = 100 + offset
                recovery = interruption + duration
                samples = [(0, 0, 0), (100, 1, 1)]
                if interruption > 5100:
                    samples.append((5100, 1, 1))
                samples.extend([
                    (interruption, *disabled), (recovery, 1, 1), (recovery + 1, 1, 1),
                    (recovery + 4999, 1, 1), (recovery + 5000, 1, 1), (recovery + 5001, 1, 1),
                ])
                result.append(scenario(profile, f"{event}_at_{offset}ms_for_{duration}ms", event, samples))
    result.append(scenario(profile, "demand_after_long_idle", "idle_then_demand", [
        (0, 0, 1), (5000, 0, 1), (6000, 0, 1), (6100, 1, 1),
        (6101, 1, 1), (11099, 1, 1), (11100, 1, 1), (11101, 1, 1),
    ]))
    result.append(scenario(profile, "exact_4999_5000_boundary", "timer_boundary", [
        (0, 1, 1), (4999, 1, 1), (5000, 1, 1), (5001, 1, 1),
        (6000, 0, 1), (6001, 1, 1), (11000, 1, 1), (11001, 1, 1),
    ]))
    for interval in [99, 101, 333, 1000]:
        samples = [(0, 0, 0), *((t, 1, 1) for t in range(interval, 7000, interval))]
        result.append(scenario(profile, f"scan_interval_{interval}ms", "scan_interval", samples))
    result.append(scenario(profile, "repeated_signal_chatter", "chatter", [
        (0, 0, 0), (100, 1, 1), (4900, 0, 1), (5000, 1, 1),
        (9900, 1, 0), (10000, 1, 1), (14999, 1, 1), (15000, 1, 1),
    ]))
    return result
