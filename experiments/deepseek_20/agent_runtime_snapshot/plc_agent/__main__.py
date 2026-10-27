from __future__ import annotations

import argparse
import getpass
import json
import sys

from .attachments import attach
from .config import ModelConfig, doctor
from .engine import Engine
from .storage import Project, Session


def select_session(project_id=None, session_id=None, new_title=None, model=""):
    projects = Project.list()
    if new_title:
        project = Project.create(new_title)
    elif project_id:
        project = Project.load(project_id)
    elif projects:
        project = Project.load(projects[0]["id"])
    else:
        project = Project.create()
    ident = session_id or (None if new_title else project.data.get("last_session"))
    return Session.load(project, ident) if ident else Session.create(project, model)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="PLC Workbench · 厂商无关的本地终端 agent")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("doctor", help="检查配置，不发送网络请求")
    commands.add_parser("projects", help="列出本机项目")
    cfg = commands.add_parser("config", help="交互配置模型；密钥不写入命令行")
    cfg.add_argument("--base-url")
    cfg.add_argument("--model")
    for command in ("ui", "run", "export"):
        item = commands.add_parser(command)
        item.add_argument("--project")
        item.add_argument("--session")
        item.add_argument("--new", metavar="TITLE")
        item.add_argument("--attach", action="append", default=[])
        if command == "run":
            item.add_argument("--mode", choices=("plan", "execute"), default="plan")
            item.add_argument("prompt")
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            print(json.dumps(doctor(), ensure_ascii=False, indent=2))
            return 0
        if args.command == "projects":
            print(json.dumps(Project.list(), ensure_ascii=False, indent=2))
            return 0
        config = ModelConfig.load()
        if args.command == "config":
            previous_base = config.base_url
            config.base_url = (args.base_url or input(f"Base URL [{config.base_url}]: ") or config.base_url).rstrip("/")
            config.model = args.model or input(f"Model [{config.model}]: ") or config.model
            key = getpass.getpass("API key（留空使用当前值/环境变量）: ")
            if key:
                config.api_key = key
            elif previous_base != config.base_url:
                config.api_key = ""
            config.validate()
            config.save()
            print("配置已保存。")
            return 0
        session = select_session(getattr(args, "project", None), getattr(args, "session", None),
                                 getattr(args, "new", None), config.model)
        for path in getattr(args, "attach", []):
            attach(session.project, path)
        if args.command == "export":
            print(session.export())
        elif args.command == "run":
            session.data["mode"] = args.mode
            def notice(kind, payload):
                if kind != "delta":
                    print(json.dumps({"event": kind, **payload}, ensure_ascii=False))
            engine = Engine(session, config, notify=notice)
            engine.run(args.prompt)
            return 0 if session.data["status"] == "idle" else 1
        else:
            from .tui import Workbench
            Workbench(session, config).run()
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
