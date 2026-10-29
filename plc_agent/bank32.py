"""Unified 32-task bank: frozen public20 + custom12 dataset.

The author packet deliberately excludes scenarios/expected answers; those stay
host-side in dataset.evaluate. Both self and Codex harnesses must use this
packet (or a file rendering of it) so the information set is identical.
"""
from __future__ import annotations

from . import dataset

BACKEND_NOTES = """\
Environment and test contract:
- Frozen finite tests are host-owned; expected answers are never shown to the author.
- Local behavior backend is STruC++ 0.7 with g++; TON/R_TRIG and common math functions are available.
- Declare STRUCT types as TYPE Name : STRUCT ... END_STRUCT END_TYPE; fields use ':'.
- CASE ELSE has no colon. Prefer IF/ELSIF where possible.
- Fixed arrays keep their declared lower bounds; array JSON values start at the declared lower bound.
- CODESYS target compilation is a separate evidence stage; local behavior pass is not a CODESYS runtime claim.
- Use check.ps1 diagnostics only. Do not inspect generated C++ headers or compiler caches.
- Never add, remove, or change interface variables. If the task does not declare CycleTime or Dt inputs, do not add them; use only the frozen interface.
- Do not access TON internal members such as CURRENT_TIME; use declared TON instances' public Q/ET outputs.
- At most 6 source versions, 24 model requests and 1800 seconds per task. Never edit tests or expected data.
"""


def catalog():
    return dataset.catalog()


def load(ident: str):
    return dataset.load(ident)


def questions():
    return [load(entry["id"]) for entry in catalog()["tasks"]]


def author_packet(task: dict, current_source: str = "", failure=None):
    """Information parity packet for self and Codex authors."""
    return {
        "task_id": task["id"],
        "title": task["title"],
        "block": task["block"],
        "requirements": task["requirements"],
        "interface": task["interface"],
        "ltl_requirements": task.get("ltl", {}),
        "backend_notes": BACKEND_NOTES,
        "current_source": current_source,
        "actual_failure": failure,
        "limits": {
            "max_source_versions": 6,
            "max_model_requests": 24,
            "timeout_seconds": 1800,
            "expected_tables": "host_owned_not_visible",
        },
    }


def validate_bank():
    entries = catalog()["tasks"]
    ids = [entry["id"] for entry in entries]
    expected = [f"PUBLIC_{i:02d}" for i in range(1, 21)] + [f"CUSTOM_{i:02d}" for i in range(1, 13)]
    if ids != expected:
        raise ValueError("Bank IDs or order mismatch")
    totals = {"scenarios": 0, "scans": 0}
    for entry in entries:
        task = load(entry["id"])
        if not task.get("block") or not task.get("interface") or not task.get("scenarios"):
            raise ValueError("Incomplete task: " + entry["id"])
        packet = author_packet(task)
        def keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield key
                    yield from keys(child)
            elif isinstance(value, list):
                for child in value:
                    yield from keys(child)
        leaked = set(keys(packet)) & {"scenarios", "trace", "expected", "expect"}
        if leaked:
            raise ValueError("Author packet leaks expected data: " + entry["id"] + " " + str(leaked))
        totals["scenarios"] += len(task["scenarios"])
        totals["scans"] += sum(len(case.get("trace", case.get("rows", []))) for case in task["scenarios"])
    return {"status": "pass", "tasks": len(entries), "public": 20, "custom": 12, **totals}
