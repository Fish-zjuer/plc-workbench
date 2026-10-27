from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shlex

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
            yield Label("API key 环境变量名")
            yield Input(cfg.key_env, id="key-env")
            yield Label("模型 ID")
            yield Input(cfg.model, placeholder="服务商提供的 model 名称", id="model-name")
            yield Label("独立审查模型 ID（留空使用主模型的新上下文）")
            yield Input(cfg.review_model, id="review-model")
            yield Label("工具协议")
            yield Select([("原生 function calling", "native"), ("JSON 指令兼容模式", "json")], value=cfg.tool_mode, allow_blank=False, id="tool-mode")
            yield Checkbox("流式输出（不支持 SSE 的服务可关闭）", value=cfg.stream, id="stream")
            yield Label("上下文窗口 / 输出上限 / 每轮模型步数（按模型实际能力填写）")
            yield Input(str(cfg.context_window), type="integer", id="context-window")
            yield Input(str(cfg.max_output_tokens), type="integer", id="max-output")
            yield Input(str(cfg.max_steps), type="integer", id="max-steps")
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
            cfg = replace(self.config, base_url=new_base, model=value("model-name"), key_env=value("key-env"),
                          api_key=value("api-key") or (self.config.api_key if new_base == self.config.base_url else ""),
                          review_model=value("review-model"), tool_mode=self.query_one("#tool-mode", Select).value,
                          stream=self.query_one("#stream", Checkbox).value, context_window=int(value("context-window")),
                          max_output_tokens=int(value("max-output")), max_steps=int(value("max-steps")))
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
`/adjudicate 轮次ID 发现ID ambiguous 依据` 裁决审查（也支持 requirement/contract/reject）

支持 ST/文本、PDF、DOCX 和 ZIP；文件保留在本机，按需提取的文本会发送到所配置模型服务。
离线测试使用 STruC++ + g++，当前支持五类接口；不等于 CODESYS 编译或形式化证明。
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
            yield Button("切换模式", id="mode")
            yield Button("模型配置", id="config")
            yield Button("压缩", id="compact")
            yield Button("会话", id="sessions")
            yield Button("停止", variant="error", id="stop")
        yield Footer()

    def on_mount(self):
        self.theme = "textual-dark"
        self.query_one("#chat", RichLog).write(Markdown(HELP))
        for event in self.session.events()[-150:]:
            if event["kind"] in ("user", "assistant", "notice", "error", "tool"):
                self.render_event(event["kind"], event)
        self.refresh_state()
        self.query_one("#composer", TextArea).focus()

    def on_resize(self, event):
        if self.is_mounted:
            self.query_one("#sidebar").display = event.size.width >= 100

    def refresh_state(self):
        data = self.session.data
        self.query_one("#project-state", Static).update(Text(f"{self.session.project.data['title']}\n{self.session.project.data['id']}\n会话 {data['id']}"))
        plan = "\n".join(f"{'✓' if s['status']=='completed' else '▶' if s['status']=='in_progress' else '·'} {s['step']}" for s in data["plan"])
        self.query_one("#plan-state", Static).update(Text(plan or "尚未制定计划"))
        attachments = self.session.project.data["attachments"]
        self.query_one("#attachment-state", Static).update(Text("\n".join(f"{a['name'][:28]} · {a['status']}" for a in attachments[-10:]) or "暂无附件"))
        stats = self.engine.context_stats()
        usage = data.get("token_usage", {})
        context = f"≈{stats['estimated_tokens']:,} / {stats['window']:,}\n约 {stats['ratio']:.0%} · 已压缩 {stats['compactions']} 次"
        if usage:
            context += f"\n上次服务计数 {usage.get('total_tokens', '未提供')}"
        self.query_one("#context-state", Static).update(Text(context))
        mode = "计划 · 项目只读" if data["mode"] == "plan" else "执行 · 可写项目"
        self.query_one("#status", Static).update(Text(f"{mode} | {data['status']} | {self.config.model or '未配置模型'} | 上下文 ≈{stats['ratio']:.0%}"))
        for name in ("mode", "compact", "sessions", "config", "upload"):
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
        elif command == "/pin":
            if rest.strip():
                self.session.data.setdefault("pinned_notes", []).append(rest[:2000])
                self.session.save()
                self.render_event("notice", {"text": "已固定；压缩后仍会保留。"})
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
        self.session = session
        self.engine = self._engine()
        self.query_one("#chat", RichLog).clear()
        self.render_event("notice", {"text": "当前项目：" + session.project.data["title"]})
        for event in session.events()[-150:]:
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
            elif kind == "attach":
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
