"""Unified 32-task bank: frozen public20 + custom12 dataset.

The author packet deliberately excludes scenarios/expected answers; those stay
host-side in dataset.evaluate. Both self and Codex harnesses must use this
packet (or a file rendering of it) so the information set is identical.
"""
from __future__ import annotations

from plc_agent import dataset

BACKEND_NOTES = """Environment and test contract:
- Target compiler and functional test executor are CODESYS; tests run in its simulation runtime.
- Preserve the exact task interface, types and array bounds. Never add CycleTime or other inputs.
- Standard TON/R_TRIG and IEC functions use the installed CODESYS libraries and native semantics.
- Use only diagnostics from the shared checker; never inspect hidden tests, compiler caches or reference solutions.
- One fresh FB instance per scenario; inputs are assigned before invocation and outputs sampled afterwards.
- Timer tests use the real CODESYS simulation clock; unsupported scheduling or platform features are infrastructure limits, not permission to change the task.
- The optional local PV_COUNT/PV_READ/PV_WRITE/PV_COMPATIBLE ABI is not a CODESYS library. Do not invent these helpers in native target code.
- Declare STRUCT types as TYPE Name : STRUCT ... END_STRUCT END_TYPE. Keep caller-owned IN_OUT references.
- Compilation, finite testing and formal verification are separate evidence stages. Do not claim unexecuted stages passed.
- Frozen test expectations stay host-owned. At most 6 source versions, 24 model requests and 1800 seconds per task.
"""


def backend_notes(backend):
    if backend=='codesys':return BACKEND_NOTES
    if backend=='optional_local':
        from optional_local_tests.author_notes import BACKEND_NOTES as local_notes
        return local_notes
    raise ValueError('Unknown test backend: '+str(backend))


def catalog():
    return dataset.catalog()


def load(ident: str):
    return dataset.load(ident)


def questions():
    return [load(entry["id"]) for entry in catalog()["tasks"]]


def author_packet(task: dict, current_source: str = "", failure=None, *, backend="codesys"):
    """Information parity packet for self and Codex authors."""
    ltl=task.get('ltl',{})
    if isinstance(ltl,dict):ltl={k:v for k,v in ltl.items() if k!='execution'}
    return {
        "task_id": task["id"],
        "title": task["title"],
        "block": task["block"],
        "requirements": task["requirements"],
        "additional_constraints": task.get("constraints", []),
        "interface": task["interface"],
        "ltl_requirements": ltl,
        "backend_notes": backend_notes(backend),
        "current_source": current_source,
        "actual_failure": failure,
        "limits": {
            "max_source_versions": 6,
            "max_model_requests": 24,
            "timeout_seconds": 1800,
            "expected_tables": "host_owned_not_visible",
            "reserved_internal_prefix": "PVL_ (verification wrapper storage; do not use in candidate code)",
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
