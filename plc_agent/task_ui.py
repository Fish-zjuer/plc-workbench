"""Read-only task inspector and explicit human contract action."""
import json
from rich.text import Text
from textual import on
from textual.containers import Horizontal,Vertical
from textual.screen import ModalScreen
from textual.widgets import Button,Checkbox,Label,RichLog

from .task_spec import render_plan

STATUS_LABELS={
    "not_run":"尚未执行","planned":"已制定计划","requires_contract_confirmation":"待确认需求与测试",
    "reviewed_offline_pass":"本地检查和审查通过","offline_pass_target_pending":"本地通过 · 目标平台待验证",
    "reviewed_target_pass":"目标后端检查和审查通过","review_disagreement":"审查预期与执行结果有争议",
    "review_questions":"审查有待确认问题","capability_blocked":"目标接口暂未支持",
    "coverage_gap":"检查条件未被触发","repair_limit":"修订预算用尽","task_error":"执行出错",
    "stale_evidence":"代码、需求或后端已变化","interrupted":"已停止","delivery_error":"交付包导出失败",
    "new_assumptions_require_plan":"提案含未确认需求假设"}

class TaskInspector(ModalScreen[str|None]):
    BINDINGS=[("escape","dismiss(None)","关闭")]
    DEFAULT_CSS="""
    TaskInspector { align: center middle; background: $background 70%; }
    TaskInspector > Vertical { width: 94%; height: 94%; border: round $accent; background: $surface; padding: 1 2; }
    TaskInspector RichLog { height: 1fr; margin: 1 0; }
    TaskInspector Horizontal { height: 3; }
    TaskInspector Button { min-width: 8; width: auto; margin-right: 1; }
    TaskInspector Checkbox { height: auto; margin-bottom: 1; }
    """
    def __init__(self,spec,view,receipt):
        super().__init__();self.spec=spec;self.view=view;self.receipt=receipt
    def compose(self):
        with Vertical():
            yield Label(f"PLC 任务 · {self.view['task_id']} · {self.spec['title']}")
            yield RichLog(wrap=True,markup=False,highlight=False,id="task-detail")
            yield Checkbox("我已核对需求、接口、假设和预期输出，确认这一版测试约定",id="task-consent",disabled=self.view["accepted"])
            with Horizontal():
                yield Button("确认约定",variant="primary",id="task-confirm",disabled=True)
                yield Button("运行任务",id="task-execute",disabled=not self.view["accepted"])
                yield Button("导出",id="task-export",disabled="run_id" not in self.receipt)
                yield Button("关闭",id="task-close")
            with Horizontal():
                yield Button('形式化检查',id='task-verify',disabled=not self.view['accepted'])
                yield Button('CODESYS编译',id='task-compile',disabled=not self.view['accepted'])
    def on_mount(self):
        log=self.query_one("#task-detail",RichLog)
        log.write(Text("结果："+STATUS_LABELS.get(self.receipt["status"],self.receipt["status"]),style="bold cyan"))
        log.write(Text("检查目标："+self.spec["target"]+"；执行适配器："+self.spec["executor"]))
        log.write(Text(render_plan(self.spec)))
        log.write(Text("完整测试约定 JSON（可滚动查看）：",style="bold"))
        log.write(Text(json.dumps(self.spec,ensure_ascii=False,indent=2)))
        log.write(Text("后端能力与下一步："+json.dumps(self.view["capabilities"],ensure_ascii=False,indent=2)))
        log.write(Text('独立形式化检查：'+json.dumps(self.view.get('separate_formal_check',{'status':'not_executed'}),ensure_ascii=False,indent=2)))
        log.write(Text('独立CODESYS编译：'+json.dumps(self.view.get('separate_codesys_compile',{'status':'not_executed'}),ensure_ascii=False,indent=2)))
        if "run_id" in self.receipt:
            from .task_tools import compact_receipt
            log.write(Text("本次结果和证据："+json.dumps(compact_receipt(self.receipt),ensure_ascii=False,indent=2)))
        log.scroll_home(animate=False)
    @on(Checkbox.Changed,"#task-consent")
    def consent(self,event):
        self.query_one("#task-confirm",Button).disabled=not event.value or bool(self.spec["questions"])
    @on(Button.Pressed)
    def choose(self,event):
        event.stop()
        command={"task-confirm":"accept","task-execute":"run","task-export":"export",'task-verify':'verify','task-compile':'compile'}.get(event.button.id)
        self.dismiss(command)
