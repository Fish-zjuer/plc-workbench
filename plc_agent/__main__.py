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
    session=Session.load(project, ident) if ident else Session.create(project, model)
    session.activate()
    return session


def main():
    if sys.argv[1:2] == ['web']:
        from .web import main as web_main
        return web_main(sys.argv[2:])
    if sys.argv[1:2]==['dataset']:
        from .dataset_cli import main as dataset_main
        return dataset_main(sys.argv[2:])
    if sys.argv[1:2]==['codesys']:
        from .codesys_cli import main as codesys_main
        return codesys_main(sys.argv[2:])
    if sys.argv[1:2]==['task']:
        from .task_cli import main as task_main
        return task_main(sys.argv[2:])
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="PLC Workbench · 厂商无关的本地终端 agent")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("doctor", help="检查配置，不发送网络请求")
    project_list=commands.add_parser("projects", help="列出本机项目")
    project_list.add_argument('--include-benchmarks',action='store_true')
    cfg = commands.add_parser("config", help="交互配置模型；密钥不写入命令行")
    cfg.add_argument("--base-url")
    cfg.add_argument("--model")
    for command in ("ui", "run", "export", "solve",'compact','memory','history'):
        item = commands.add_parser(command)
        item.add_argument("--project")
        item.add_argument("--session")
        item.add_argument("--new", metavar="TITLE")
        item.add_argument("--attach", action="append", default=[])
        if command == "run":
            item.add_argument("--mode", choices=("plan", "execute"), default="plan")
            item.add_argument("prompt")
        if command=='solve':
            item.add_argument('question_id',choices=[f'{n:02d}' for n in range(1,21)])
            item.add_argument('--mode',choices=('plan','execute'),default='plan')
            item.add_argument('--source',default=None)
            item.add_argument('--max-revisions',type=int,choices=range(1,6),default=None)
        if command=='history':
            item.add_argument('query',nargs='?',default='')
            item.add_argument('--start-event',type=int,default=0)
            item.add_argument('--max-events',type=int,default=8)
    args = parser.parse_args()
    session=None
    try:
        if args.command == "doctor":
            print(json.dumps(doctor(), ensure_ascii=False, indent=2))
            return 0
        if args.command == "projects":
            print(json.dumps(Project.list(include_benchmarks=args.include_benchmarks), ensure_ascii=False, indent=2))
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
        elif args.command=='memory':
            print(json.dumps(session.data.get('working_memory',{'message':'尚未压缩；原始对话仍保留。'}),ensure_ascii=False,indent=2))
        elif args.command=='history':
            from .toolbox import Toolbox
            result=Toolbox(session).call('read_history',{'query':args.query,'start_event':args.start_event,'max_events':args.max_events})
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return 1 if result.get('status')=='tool_error' else 0
        elif args.command=='compact':
            engine=Engine(session,config)
            changed=engine.compact()
            print(json.dumps({'compacted':changed,'memory':session.data.get('working_memory')},ensure_ascii=False,indent=2))
        elif args.command == "run":
            session.data["mode"] = args.mode
            def notice(kind, payload):
                if kind != "delta":
                    print(json.dumps({"event": kind, **payload}, ensure_ascii=False))
            engine = Engine(session, config, notify=notice)
            engine.run(args.prompt)
            return 0 if session.data["status"] == "idle" else 1
        elif args.command=='solve':
            from .workflow import PLCWorkflow
            session.data['mode']=args.mode;session.save()
            def notice(kind,payload):
                if kind in ('notice','error'):print(payload['text'],file=sys.stderr)
            result=PLCWorkflow(session,config,notify=notice).run(args.question_id,args.source,args.max_revisions)
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return 0 if result['status'] in ('verified','planned') else 1
        else:
            from .tui import Workbench
            Workbench(session, config).run()
        return 0
    except KeyboardInterrupt:
        if session:
            session.data['status']='interrupted';session.save();session.event('notice',text='终端中止；已完成的文件修改和证据保留。')
        print('已停止；会话和证据保留。',file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
