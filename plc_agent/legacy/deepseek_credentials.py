"""Read explicitly authorized local DeepSeek keys; never print or persist them."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

OFFICIAL = "https://api.deepseek.com"


def candidates(folder: Path):
    seen = set()
    for path in sorted(folder.glob("*.txt")):
        if path.stat().st_size > 1_000_000:
            continue
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        context = ""
        distance = 10
        for line in lines:
            keys = re.findall(r"sk-[A-Za-z0-9_-]{16,}", line)
            if not keys and line.strip():
                context = line.strip()
                distance = 0
            for key in keys:
                if distance <= 3 and re.search(r"deepseek|深度求索", context, re.I) and key not in seen:
                    seen.add(key)
                    yield key, {"fingerprint": hashlib.sha256(key.encode()).hexdigest()[:12],
                                "credential_file": path.name, "label": context[:100]}
            distance += 1


def get(key: str, route: str):
    if route not in ("/user/balance", "/models"):
        raise ValueError("Unsupported credential discovery route")
    req = urllib.request.Request(OFFICIAL + route, headers={"Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read(500000).decode("utf-8"))


def select(folder: Path, minimum_cny: float = 3.0):
    checked = []
    fallback = None
    for key, public in candidates(folder):
        try:
            balance = get(key, "/user/balance")
        except urllib.error.HTTPError as exc:
            checked.append({**public, "http_status": exc.code})
            exc.close()
            continue
        available = balance.get("is_available", False)
        cny = sum(float(b["total_balance"]) for b in balance.get("balance_infos", []) if b["currency"] == "CNY")
        checked.append({**public, "available": available, "balance_infos": balance.get("balance_infos", [])})
        if available and cny > .1:
            fallback = fallback or (key, public, balance)
            if cny >= minimum_cny:
                return key, {**public, "balance": balance, "checked": checked}
    if fallback:
        key, public, balance = fallback
        return key, {**public, "balance": balance, "checked": checked}
    raise RuntimeError("DeepSeek 凭据中未找到可用余额；未输出或保存密钥")
