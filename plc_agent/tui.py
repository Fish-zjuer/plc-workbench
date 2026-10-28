from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shlex
import os

from rich.markdown import Markdown
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, DirectoryTree, Footer, Header, Input, Label, RichLog, Select, Static, TextArea

from .attachments import attach
from .config import ModelConfig, STATE_ROOT
from .engine import Engine
from .storage import Project, Session


class FilePicker(ModalScreen[str | None]):
    BINDINGS = [("escape", "dismiss(None)", "取消")]
    DEFAULT_CSS = """
    FilePicker { align: center middle; background: $background 70%; }
    FilePicker > Vertical { width: 85%; height: 85%; border: round $accent; background: $surface; padding: 1 2; }
    FilePicker DirectoryTree { height: 1fr; }
    FilePicker Input { margin: 1 0; }
    FilePicker Horizontal { height: 3; }
    """

    def __init__(self, initial: Path):
        super().__init__()
        self.initial = initial

    def compose(self):
        with Vertical():
            yield Label("上传附件 · 保留原件并复制到当前项目")
            yield DirectoryTree(self.initial, id="file-tree")
            yield Input(placeholder="也可粘贴完整文件路径，支持空格和中文", id="file-path")
            with Horizontal():
                yield Button("上传", variant="primary", id="upload-confirm")
                yield Button("取消", id="upload-cancel")

    @on(DirectoryTree.FileSelected)
    def selected(self, event):
        self.query_one("#file-path", Input).value = str(event.path)

    @on(Button.Pressed, "#upload-confirm")
    @on(Input.Submitted, "#file-path")
    def confirm(self):
        value = self.query_one("#file-path", Input).value.strip().strip('"')
        if Path(value).is_file():
            self.dismiss(value)
        else:
            self.notify("请选择一个存在的文件", severity="error")

    @on(Button.Pressed, "#upload-cancel")
    def cancel(self):
        self.dismiss(None)


class Settings(ModalScreen[ModelConfig | None]):
    BINDINGS = [("escape", "dismiss(None)", "取消")]
    DEFAULT_CSS = """
    Settings { align: center middle; background: $background 70%; }
    Settings > VerticalScroll { width: 82; height: 90%; border: round $accent; background: $surface; padding: 1 2; }
    Settings Label { margin-top: 1; }
    Settings Horizontal { height: 3; margin-top: 1; }
    """

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config

    def compose(self):
        cfg = self.config
        with VerticalScroll():
            yield Static("模型连接 · Chat Completions 兼容协议", classes="heading")
            yield Label("Base URL（自行填写服务地址，通常包括 /v1）")
            yield Input(cfg.base_url, placeholder="https://你的服务地址/v1", id="base-url")
            yield Label("API key（本机保存，不进入会话/导出；留空保留当前值）")
            yield Input(password=True, placeholder="可使用环境变量，或在这里填写", id="api-key")
            yield Checkbox('清除本机保存的密钥（仍可使用环境变量）',id='clear-key')
            yield Label("API key 环境变量名")
            yield Input(cfg.key_env, id="key-env")
            yield Label("模型 ID")
            yield Input(cfg.model, placeholder="服务商提供的 model 名称", id="model-name")
            yield Label("独立审查模型 ID（留空使用主模型的新上下文）")
            yield Input(cfg.review_model, id="review-model")
            yield Label("工具协议")
            yield Select([("原生 function calling", "native"), ("JSON 指令兼容模式", "json")], value=cfg.tool_mode, allow_blank=False, id="tool-mode")
            yield Checkbox("流式输出（不支持 SSE 的服务可关闭）", value=cfg.stream, id="stream")
            yield Label("上下文窗口 / 输出上限 / 每轮模型调用上限（含PLC流程内部请求）")
            yield Input(str(cfg.context_window), type="integer", id="context-window")
            yield Input(str(cfg.max_output_tokens), type="integer", id="max-output")
            yield Input(str(cfg.max_steps), type="integer", id="max-steps")
            yield Label('请求超时（秒）')
            yield Input(str(cfg.timeout),type='integer',id='request-timeout')
            yield Label('压缩：近期原文轮数 / 目标窗口比例 / 摘要输出预算')
            yield Input(str(cfg.compact_keep_turns),type='integer',id='compact-keep')
            yield Input(str(cfg.compact_target_ratio),id='compact-target')
            yield Input(str(cfg.compact_summary_tokens),type='integer',id='compact-output')
            yield Label('仅压缩使用的服务扩展参数 JSON（覆盖同名主配置）')
            yield Input(json.dumps(cfg.compact_extra_body,ensure_ascii=False),id='compact-extra-body')
            yield Label("服务扩展参数 JSON（例如 thinking、reasoning_effort；留 {} 不启用）")
            yield Input(json.dumps(cfg.extra_body, ensure_ascii=False), id="extra-body")
            yield Static("", id="settings-error")
            with Horizontal():
                yield Button("保存配置", variant="primary", id="save-settings")
                yield Button("取消", id="cancel-settings")

    @on(Button.Pressed, "#save-settings")
    def save(self):
        try:
            def value(ident):
                return self.query_one("#" + ident, Input).value.strip()
            new_base = value("base-url").rstrip("/")
            env_name=value('key-env')
            clear=self.query_one('#clear-key',Checkbox).value
            key=value('api-key')
            if not key:
                key=os.environ.get(env_name,'') or (self.config.api_key if not clear and new_base==self.config.base_url and env_name==self.config.key_env else '')
            cfg = replace(self.config, base_url=new_base, model=value("model-name"), key_env=value("key-env"),
                          api_key=key,
                          review_model=value("review-model"), tool_mode=self.query_one("#tool-mode", Select).value,
                          stream=self.query_one("#stream", Checkbox).value, context_window=int(value("context-window")),
                          max_output_tokens=int(value("max-output")), max_steps=int(value("max-steps")),
                          timeout=int(value('request-timeout')),compact_keep_turns=int(value('compact-keep')),
                          compact_target_ratio=float(value('compact-target')),compact_summary_tokens=int(value('compact-output')),
                          compact_extra_body=json.loads(value('compact-extra-body') or '{}'),
                          extra_body=json.loads(value("extra-body") or "{}"))
            cfg.validate()
            cfg.save()
            self.dismiss(cfg)
        except (OSError, ValueError) as exc:
            self.query_one("#settings-error", Static).update(str(exc))

    @on(Button.Pressed, "#cancel-settings")
    def cancel(self):
        self.dismiss(None)


class SessionPicker(ModalScreen[tuple[str, str] | None]):
    BINDINGS = [("escape", "dismiss(None)", "取消")]
    DEFAULT_CSS = """
    SessionPicker { align: center middle; background: $background 70%; }
    SessionPicker > VerticalScroll { width: 80%; height: 80%; border: round $accent; background: $surface; padding: 1 2; }
    SessionPicker Button { width: 100%; margin: 0 0 1 0; }
    """
    def compose(self):
        with VerticalScroll():
            yield Label("恢复项目 / 会话")
            for project in Project.list():
                for path in sorted((STATE_ROOT / "projects" / project["id"] / "sessions").glob("*/session.json"), reverse=True):
                    data = json.loads(path.read_text(encoding="utf-8"))
                    label = f"{project['title']} · {data['id']} · {data['mode']} · {data['created_at'][:16]}"
                    yield Button(label, id="session-" + project["id"] + "-" + data["id"])
            yield Button("取消", id="sessions-cancel")

    @on(Button.Pressed)
    def choose(self, event):
        ident = event.button.id
        self.dismiss(tuple(ident.split("-")[1:]) if ident.startswith("session-") else None)


HELP = """**PLC Workbench** · 上传题面和 ST，先讨论计划，再执行测试与修复。

`Ctrl+O` 上传文件　`Ctrl+P` 切换计划/执行　`Ctrl+Enter` 发送　`Esc` 停止

`/help` 帮助 · `/config` 配置模型 · `/plan` 计划模式 · `/act` 执行模式
`/attach 完整路径` 上传 · `/files` 附件 · `/compact` 压缩 · `/pin 内容` 固定笔记
`/new 项目名` 新项目 · `/sessions` 恢复 · `/export` 导出 · `/test` 测试模型连接
`/audit 接口 源码路径 需求文本路径` 独立审查（执行模式）
`/solve 05` 专用PLC流程：计划模式只制定计划，执行模式自动生成/修复并测试
`/task plan 合约JSON路径` 导入一般PLC任务；也可上传需求后让助手调用任务规划工具
`/task show 任务ID` 看需求和检查；`/task accept 任务ID` 确认本版约定
`/task run 任务ID` 实现→编译→扫描检查→独立审查→导出；`/task status 任务ID` 核对结果
`/task verify 任务ID` 从当前ST执行Z3形式化检查；支持的性质和限制写入结果
`/task compile 任务ID` 用已配置的CODESYS单独编译当前ST，保存厂商证据
`/task reject 任务ID Q1 "依据"` 人工驳回审查误报；再次 run 会重新编译和重放
`/adjudicate 轮次ID 发现ID ambiguous 依据` 裁决审查（也支持 requirement/contract/reject）

`/memory` 查看工作记忆 · `/history 关键词` 检索原始会话
`/backend` 查看当前验证后端与适用范围

支持 ST/文本、PDF、DOCX 和 ZIP；上传到本地项目，按需读取的正文发给所配置的模型服务。
通用PLC接口与公共题库有各自的有限检查；结果以执行证据为准。
"""


class Workbench(App):
    TITLE = "PLC Workbench"
    SUB_TITLE = "计划 · 实现 · 测试 · 审查"
    BINDINGS = [Binding("ctrl+enter", "send", "发送", priority=True), Binding("ctrl+o", "upload", "上传", priority=True),
                Binding("ctrl+p", "mode", "计划/执行", priority=True), Binding("ctrl+k", "compact", "压缩", priority=True),
                Binding("escape", "stop", "停止", priority=True), Binding("ctrl+q", "quit", "退出")]
    CSS = """
    Screen { background: #0c1220; }
    Header { background: #16213a; color: #d9e9ff; }
    #body { height: 1fr; }
    #sidebar { width: 33; padding: 1; background: #111c30; border-right: solid #263c58; overflow-y: auto; }
    #sidebar Static { height: auto; margin-bottom: 1; }
    #main { width: 1fr; }
    #chat { height: 1fr; padding: 1 2; background: #0c1220; }
    #streaming { height: auto; max-height: 5; padding: 0 2; color: #9bb9d6; }
    #status { height: 1; background: #172a43; padding: 0 1; color: #b9d9ec; }
    #composer { height: 5; border: round #365a80; margin: 0 1; }
    #buttons { height: 3; padding: 0 1; }
    #buttons Button { min-width: 8; width: auto; margin-right: 1; }
    .heading { text-style: bold; color: #69d8c9; }
    """

    def __init__(self, session: Session, config: ModelConfig, provider_factory=None):
        super().__init__()
        self.session, self.config = session, config
        self.provider_factory = provider_factory
        self.busy, self.stream_text = False, ""
        self.engine = self._engine()

    def _engine(self):
        provider = self.provider_factory(self.config) if self.provider_factory else None
        return Engine(self.session, self.config, provider=provider, notify=lambda k, p: self.call_from_thread(self.receive, k, p))

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Static("PROJECT", classes="heading")
                yield Static("", id="project-state")
                yield Static('PLC 任务',classes='heading')
                yield Static('上传需求后先制定任务计划',id='task-state')
                yield Static("计划", classes="heading")
                yield Static("尚未制定计划", id="plan-state")
                yield Static("附件", classes="heading")
                yield Static("暂无附件", id="attachment-state")
                yield Static("上下文", classes="heading")
                yield Static("", id="context-state")
            with Vertical(id="main"):
                yield RichLog(id="chat", wrap=True, markup=False, highlight=False, max_lines=15000)
                yield Static("", id="streaming", markup=False)
        yield Static("", id="status")
        yield TextArea(id="composer", soft_wrap=True)
        with Horizontal(id="buttons"):
            yield Button("发送", variant="primary", id="send")
            yield Button("上传", id="upload")
            yield Button('任务',id='tasks')
            yield Button("切换模式", id="mode")
            yield Button("模型配置", id="config")
            yield Button("压缩", id="compact")
            yield Button("会话", id="sessions")
            yield Button("停止", variant="error", id="stop")
        yield Footer()

    def on_mount(self):
        self.theme = "textual-dark"
        self.query_one("#chat", RichLog).write(Markdown(HELP))
        for event in self.session.events(tail=150):
            if event["kind"] in ("user", "assistant", "notice", "error", "tool"):
                self.render_event(event["kind"], event)
        self.refresh_state()
        self.query_one("#composer", TextArea).focus()

    def on_resize(self, event):
        if self.is_mounted:
            self.query_one("#sidebar").display = event.size.width >= 100

    def refresh_state(self):
        data = self.session.data
        task=data.get('task_plan')
        if task:
            from .task_ui import STATUS_LABELS
            receipt=data.get('last_task',{})
            state=receipt.get('status','not_run') if receipt.get('task_id')==task['id'] else 'not_run'
            self.query_one('#task-state',Static).update(Text(task['title'][:40]+'\n'+task['id']+'\n'+
                ('约定已确认' if task.get('accepted') else '约定待确认')+'\n'+STATUS_LABELS.get(state,state)))
        else:self.query_one('#task-state',Static).update(Text('上传需求后，要求助手建立通用PLC任务。'))
        self.query_one("#project-state", Static).update(Text(f"{self.session.project.data['title']}\n{self.session.project.data['id']}\n会话 {data['id']}"))
        plan = "\n".join(f"{'✓' if s['status']=='completed' else '▶' if s['status']=='in_progress' else '·'} {s['step']}" for s in data["plan"])
        self.query_one("#plan-state", Static).update(Text(plan or "尚未制定计划"))
        attachments = self.session.project.data["attachments"]
        self.query_one("#attachment-state", Static).update(Text("\n".join(f"{a['name'][:28]} · {a['status']}" for a in attachments[-10:]) or "暂无附件"))
        stats = self.engine.context_stats()
        usage = data.get("token_usage", {})
        context = f"≈{stats['estimated_tokens']:,} / {stats['window']:,}\n约 {stats['ratio']:.0%} · 已压缩 {stats['compactions']} 次"
        context+=f"\n本轮调用 {stats['model_calls_this_turn']}/{stats['model_call_limit']}"
        memory=data.get('working_memory')
        if memory:context+=f"\n记忆 + {memory.get('retained_user_turns',0)}轮原文"
        if usage:
            context += f"\n上次服务计数 {usage.get('total_tokens', '未提供')}"
        self.query_one("#context-state", Static).update(Text(context))
        mode = "计划 · 只规划，不执行代码" if data["mode"] == "plan" else "执行 · 可写项目"
        self.query_one("#status", Static).update(Text(f"{mode} | {data['status']} | {self.config.model or '未配置模型'} | 上下文 ≈{stats['ratio']:.0%}"))
        for name in ("mode", "compact", "sessions", "config", "upload",'tasks'):
            self.query_one("#" + name, Button).disabled = self.busy

    def render_event(self, kind, payload):
        log = self.query_one("#chat", RichLog)
        if kind in ("user", "assistant"):
            log.write(Text("\n你" if kind == "user" else "\nAgent", style="bold cyan" if kind == "user" else "bold green"))
            log.write(Text(payload["text"]) if kind == "user" else Markdown(payload["text"]))
        elif kind == "tool":
            result = payload["result"]
            status = result.get("status", "completed")
            log.write(Text(f"  ↳ {payload['name']} · {status}", style="yellow"))
            if result.get("message"):
                log.write(Text(result["message"][:600]))
            if result.get("diff"):
                log.write(Text(result["diff"][:1600], style="dim"))
        else:
            log.write(Text(payload.get("text", ""), style="red" if kind == "error" else "dim"))

    def receive(self, kind, payload):
        if kind == "delta":
            self.stream_text = (self.stream_text + payload["text"])[-1800:]
            self.query_one("#streaming", Static).update(Text(self.stream_text))
        elif kind == "tool_start":
            self.stream_text = ""
            self.query_one("#streaming", Static).update(Text(f"执行工具：{payload['name']} …"))
        else:
            self.render_event(kind, payload)
            if kind in ("assistant", "error", "notice"):
                self.stream_text = ""
                self.query_one("#streaming", Static).update("")
        self.refresh_state()

    @on(Button.Pressed)
    def button(self, event):
        actions = {"send": self.action_send, "upload": self.action_upload, "mode": self.action_mode,
                   'tasks':self.action_tasks,
                   "config": self.action_config, "compact": self.action_compact, "sessions": self.action_sessions, "stop": self.action_stop}
        if event.button.id in actions:
            actions[event.button.id]()

    def action_send(self):
        area = self.query_one("#composer", TextArea)
        text = area.text.strip()
        if not text:
            return
        if self.busy:
            self.notify("当前任务运行中；可按 Esc 停止，输入内容会保留")
            return
        if not text.startswith('/'):
            try:self.config.validate()
            except ValueError as exc:
                self.notify(str(exc),severity='error')
                return
        area.clear()
        if text.startswith("/"):
            self.command(text)
        else:
            self.start_job("run", text)

    def command(self, text):
        command, _, rest = text.partition(" ")
        if command == "/help":
            self.query_one("#chat", RichLog).write(Markdown(HELP))
        elif command == "/config":
            self.action_config()
        elif command in ("/plan", "/act"):
            self.set_mode("plan" if command == "/plan" else "execute")
        elif command == "/attach":
            self.start_job("attach", rest) if rest.strip() else self.action_upload()
        elif command == "/compact":
            self.action_compact()
        elif command == "/files":
            self.query_one("#chat", RichLog).write(Text(json.dumps(self.session.project.data["attachments"], ensure_ascii=False, indent=2)))
        elif command=='/memory':
            self.query_one('#chat',RichLog).write(Text(json.dumps(self.session.data.get('working_memory',{'message':'尚未压缩；当前保留原始对话。'}),ensure_ascii=False,indent=2)))
        elif command=='/history':
            result=self.engine.toolbox.call('read_history',{'query':rest.strip(),'max_events':8})
            self.query_one('#chat',RichLog).write(Text(json.dumps(result,ensure_ascii=False,indent=2)))
        elif command=='/backend':
            from .backend_r4 import info
            from plc_probe.config import toolchain_dir,cache_dir
            backend=info()
            from .validation import ValidationConfig,home_for
            validation=ValidationConfig.load(home_for(self.session))
            self.query_one('#chat',RichLog).write(Text(json.dumps({'label':backend['label'] if backend else 'Preserved STruC++ release',
                'variant_api':backend.get('variant_api') if backend else None,'home':str(toolchain_dir()),'cache':str(cache_dir()),
                'validation_mode':validation.mode,'target_profile':validation.profile if validation.mode=='codesys' else None,
                'required_gates':['静态与接口检查','CODESYS目标编译','有限离线行为检查'] if validation.mode=='codesys' else ['有限离线检查'],
                'scope':'未运行实体PLC或形式化验证；R4的PV1接口不等于已配置的CODESYS库。'},ensure_ascii=False,indent=2)))
        elif command == "/pin":
            if rest.strip():
                if len(rest)>4000:
                    self.notify('固定笔记超过4000字，请拆分；内容未保存',severity='error');return
                self.session.data.setdefault("pinned_notes", []).append(rest.strip())
                self.session.save()
                self.render_event("notice", {"text": "已固定；压缩后仍会保留。"})
            else:self.command('/pins')
        elif command=='/pins':
            self.query_one('#chat',RichLog).write(Text('\n'.join(f'{i+1}. {note}' for i,note in enumerate(self.session.data.get('pinned_notes',[]))) or '暂无固定笔记'))
        elif command=='/unpin':
            try:
                index=int(rest.strip())-1
                notes=self.session.data.get('pinned_notes',[])
                if not 0<=index<len(notes):raise ValueError('invalid index')
                notes.pop(index);self.session.save()
                self.render_event('notice',{'text':'已删除该固定笔记。'})
            except ValueError:self.notify('用法：/unpin 编号；可先用 /pins 查看',severity='error')
        elif command == "/new":
            self.switch(Session.create(Project.create(rest.strip() or "PLC 项目"), self.config.model))
        elif command == "/sessions":
            self.action_sessions()
        elif command == "/export":
            self.render_event("notice", {"text": "已导出：" + str(self.session.export())})
        elif command == "/test":
            self.start_job("test", "")
        elif command == "/audit":
            self.start_job("audit", rest)
        elif command == "/adjudicate":
            self.start_job("adjudicate", rest)
        elif command == "/solve":
            self.start_job("solve", rest)
        elif command == '/task':
            self.start_job('task',rest)
        elif command == '/dataset':
            self.start_job('dataset',rest)
        else:
            self.notify("未知命令，使用 /help 查看", severity="warning")
        self.refresh_state()

    def set_mode(self, mode):
        if self.busy:
            self.notify("请先停止当前任务，再切换模式")
            return
        self.session.data["mode"] = mode
        self.session.save()
        self.session.event("notice", text="切换为" + ("计划模式" if mode == "plan" else "执行模式"))
        self.refresh_state()

    def action_mode(self):
        self.set_mode("execute" if self.session.data["mode"] == "plan" else "plan")

    def action_tasks(self):
        if self.busy:return
        task=self.session.data.get('task_plan')
        if not task:
            self.notify('先上传需求，并让助手建立通用PLC任务，或 /task plan 合约JSON路径');return
        from .task_store import TaskStore
        from .task_ui import TaskInspector
        try:
            store=TaskStore(self.session);spec=store.load(task['id']);view=store.show(task['id']);receipt=store.latest(task['id'])
            view['separate_formal_check']=store.formal_status(task['id'])
            from .task_codesys import status as codesys_status
            view['separate_codesys_compile']=codesys_status(self.session,task['id'])
            self.push_screen(TaskInspector(spec,view,receipt),lambda action:self.start_job('task',action+' '+task['id']) if action else None)
        except (OSError,ValueError,KeyError) as exc:self.notify(str(exc),severity='error')

    def action_upload(self):
        if not self.busy:
            initial = Path(__file__).resolve().parents[4] / "输入"
            self.push_screen(FilePicker(initial if initial.is_dir() else Path.cwd()), lambda path: self.start_job("attach", path) if path else None)

    def action_config(self):
        if not self.busy:
            def configured(config):
                if config:
                    self.config = config
                    self.engine = self._engine()
                    self.refresh_state()
            self.push_screen(Settings(self.config), configured)

    def action_compact(self):
        if not self.busy:
            self.start_job("compact", "")

    def action_sessions(self):
        if not self.busy:
            def selected(pair):
                if pair:
                    self.switch(Session.load(Project.load(pair[0]), pair[1]))
            self.push_screen(SessionPicker(), selected)

    def switch(self, session):
        session.activate()
        self.session = session
        self.engine = self._engine()
        self.query_one("#chat", RichLog).clear()
        self.render_event("notice", {"text": "当前项目：" + session.project.data["title"]})
        for event in session.events(tail=150):
            if event["kind"] in ("user", "assistant", "notice", "error", "tool"):
                self.render_event(event["kind"], event)
        self.refresh_state()

    def action_stop(self):
        if isinstance(self.screen, ModalScreen):
            self.screen.dismiss(None)
            return
        if self.busy:
            self.engine.cancel()
            self.notify("停止请求已发送；正在运行的编译/执行会在当前有界步骤结束后停止")

    def action_quit(self):
        if self.busy:
            self.action_stop()
            self.notify("等待当前步骤结束后，再按 Ctrl+Q 退出")
        else:
            self.exit()

    def start_job(self, kind, value):
        if self.busy:
            return
        self.busy = True
        self.refresh_state()
        self.job(kind, value)

    @work(thread=True, exit_on_error=False)
    def job(self, kind, value):
        try:
            if kind == "run":
                self.engine.run(value)
            elif kind == "compact":
                self.engine.compact()
            elif kind == 'solve':
                from .workflow import PLCWorkflow
                parts=[p.strip('"') for p in shlex.split(value,posix=False)]
                if not 1<=len(parts)<=2:
                    raise ValueError('用法：/solve 05 [candidate.st]')
                with self.session.lease():
                    if self.session.data['mode']=='execute':self.engine._ready()
                    else:self.engine.sync_from_disk()
                    result=PLCWorkflow(self.session,self.config,self.engine.scoped_provider,
                                       lambda k,p:self.call_from_thread(self.receive,k,p)).run(parts[0].zfill(2),parts[1] if len(parts)==2 else None,already_leased=True)
                    self.engine.checkpoint()
                self.engine.emit('notice',text='PLC流程：'+result['status'])
            elif kind == 'dataset':
                from .dataset_cli import perform as dataset_perform
                parts=value.split()
                if not parts or len(parts)>2:raise ValueError('Use /dataset list | show/run PUBLIC_01 or CUSTOM_01')
                with self.session.lease():
                    self.engine.sync_from_disk();self.engine.scoped_provider.reset();self.engine.provider.cancel_event.clear()
                    result=dataset_perform(self.session,self.config,*parts,provider=self.engine.scoped_provider,
                        notify=lambda text:self.call_from_thread(self.receive,'notice',{'text':text}))
                    self.engine.checkpoint()
                self.engine.emit('notice',text=json.dumps(result,ensure_ascii=False,indent=2)[:24000])
            elif kind == 'task':
                from .task_cli import perform
                parts=[p.strip('"') for p in shlex.split(value,posix=False)]
                extra={}
                if parts[:1]==['reject'] and len(parts)>=4:
                    extra={'item':parts[2],'reason':' '.join(parts[3:])};parts=parts[:2]
                if len(parts)!=2:
                    raise ValueError('用法：/task plan 合约JSON路径，或 /task show/accept/run/status/export 任务ID')
                with self.session.lease():
                    self.engine.sync_from_disk()
                    self.engine.provider.cancel_event.clear()
                    self.engine.cancel_event.clear()
                    self.engine.scoped_provider.reset()
                    result=perform(self.session,self.config,*parts,base=self.session.project.workspace,
                        provider=self.engine.scoped_provider,notify=lambda k,p:self.call_from_thread(self.receive,k,p),already_leased=True,**extra)
                    self.engine.checkpoint()
                self.engine.emit('notice',text=json.dumps(result,ensure_ascii=False,indent=2)[:24000])
            elif kind == "attach":
                with self.session.lease():
                    self.engine.sync_from_disk()
                    records = attach(self.session.project, value)
                self.engine.emit("notice", text=f"已上传 {len(records)} 项：" + records[0]["name"])
            elif kind == "test":
                self.config.validate()
                self.engine.provider.cancel_event.clear()
                response = self.engine.provider.complete([{"role": "user", "content": "请只回复：连接成功"}])
                self.engine.emit("notice", text="模型连接返回：" + response["text"][:300])
            elif kind == "audit":
                parts = [part.strip('"') for part in shlex.split(value, posix=False)]
                if len(parts) != 3:
                    raise ValueError("用法：/audit motor candidate.st requirements.md（路径含空格时加引号）")
                from .review import audit
                result = audit(self.engine, *parts)
                self.engine.emit("notice", text=f"审查完成：{result['status']}；{result['counts']}；证据 {result['report_path']}")
            elif kind == "adjudicate":
                parts = value.split(maxsplit=3)
                if len(parts) != 4:
                    raise ValueError("用法：/adjudicate 轮次ID ADV-001 ambiguous 原题未规定同步事件优先级")
                from .review import adjudicate
                result = adjudicate(self.engine, *parts)
                self.engine.emit("notice", text=f"裁决与重放：{result['status']}；{result['counts']}")
        except Exception as exc:
            text = str(exc).replace(self.config.api_key, "[redacted]") if self.config.api_key else str(exc)
            self.call_from_thread(self.render_event, "error", {"text": text[:1500]})
        finally:
            self.call_from_thread(self.finish_job)

    def finish_job(self):
        self.busy = False
        self.stream_text = ""
        self.query_one("#streaming", Static).update("")
        self.refresh_state()
