"""Shared v6 source normalization for self and Codex on bank32."""
from __future__ import annotations

import re

from .dataset_workflow import normalize_source as base_normalize


def normalize_v6(code: str, block: str) -> str:
    code = base_normalize(code, block)
    # The backend has a native LTIME duration type, so keep LTIME literals and
    # TIME_TO_LTIME/TO_LTIME calls intact; only the invalid (LTIME) cast is dropped.
    code = code.replace("(LTIME)", "")
    if re.search(r"\bLEN\s*:", code, re.I):
        code = re.sub(r"\bLEN\b(?!\s*\()", "nLen", code, flags=re.I)
    return code
