from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .backend import BackendError, compile_source
from .adversarial import review
from .config import bootstrap, doctor
from .contracts import PROFILES
from .demo import demo
from .tools import EVIDENCE_SCOPE, compare, probe, replay


def main() -> int:
    parser = argparse.ArgumentParser(description="PLC sequence-testing tool prototype")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    sub.add_parser("bootstrap")
    p = sub.add_parser("demo")
    p.add_argument("--output")
    p.add_argument("--seed", type=int, default=20261026)
    for name in ("compile", "probe", "replay"):
        p = sub.add_parser(name)
        p.add_argument("source")
        if name != "replay":
            p.add_argument("--profile", choices=PROFILES, required=True)
        if name == "probe":
            p.add_argument("--suite", choices=("normal", "focused", "random"), default="focused")
            p.add_argument("--seed", type=int, default=20261026)
            p.add_argument("--output")
            p.add_argument("--shrink-budget", type=int, default=60)
        elif name == "replay":
            p.add_argument("counterexample")
    p = sub.add_parser("compare")
    p.add_argument("before")
    p.add_argument("after")
    p.add_argument("--profile", choices=PROFILES, required=True)
    p.add_argument("--suite", choices=("normal", "focused", "random"), default="focused")
    p.add_argument("--seed", type=int, default=20261026)
    p = sub.add_parser("review", help="Execute independently proposed adversarial traces")
    p.add_argument("proposals_path")
    p.add_argument("--adjudication", dest="adjudication_path")
    p.add_argument("--output")
    sub.add_parser("serve")
    args = parser.parse_args()
    try:
        if args.command == "serve":
            from .server import serve
            serve()
            return 0
        if args.command == "doctor":
            result = doctor()
        elif args.command == "bootstrap":
            result = bootstrap()
        elif args.command == "demo":
            result = demo(Path(args.output) if args.output else None, args.seed)
        elif args.command == "compile":
            artifact = compile_source(args.source, args.profile)
            result = {"status": "compiled", "source_sha256": artifact.sha256,
                      "build_evidence": str(artifact.directory / "build.json"), "evidence_scope": EVIDENCE_SCOPE}
        elif args.command == "probe":
            result = probe(args.source, args.profile, args.suite, args.seed, args.output, args.shrink_budget)
        elif args.command == "replay":
            record = json.loads(Path(args.counterexample).read_text(encoding="utf-8"))
            result = replay(args.source, record)
        elif args.command == "review":
            result = review(args.proposals_path, args.adjudication_path, args.output)
        else:
            result = compare(args.before, args.after, args.profile, args.suite, args.seed)
    except BackendError as exc:
        result = exc.result
    except (ValueError, OSError, KeyError, RuntimeError) as exc:
        result = {"status": "tool_error", "message": str(exc)}
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0 if result["status"] in ("ready", "compiled", "pass", "completed", "no_new_failure", "no_confirmed_counterexample") else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
