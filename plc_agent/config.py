from __future__ import annotations

import os
from pathlib import Path
from dataclasses import asdict, dataclass, field
import json
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
STATE_ROOT = Path(os.environ.get("PLC_AGENT_HOME", ROOT / "agent_data")).resolve()
DEFAULT_MODEL = ""


@dataclass
class ModelConfig:
    base_url: str = ""
    model: str = ""
    key_env: str = "PLC_AGENT_API_KEY"
    api_key: str = field(default="", repr=False)
    tool_mode: str = "native"
    stream: bool = True
    context_window: int = 32000
    max_output_tokens: int = 4096
    max_steps: int = 24
    timeout: int = 45
    review_model: str = ""
    extra_body: dict = field(default_factory=dict)
    compact_keep_turns: int = 2
    compact_target_ratio: float = .5
    compact_summary_tokens: int = 2048
    compact_extra_body: dict = field(default_factory=dict)

    def validate(self, require_ready=True):
        for name in ('base_url','model','key_env','api_key','tool_mode','review_model'):
            if not isinstance(getattr(self,name),str):raise ValueError(f'{name} 必须为文本')
        for name in ('context_window','max_output_tokens','max_steps','timeout','compact_keep_turns','compact_summary_tokens'):
            if type(getattr(self,name)) is not int:raise ValueError(f'{name} 必须为整数')
        if type(self.stream) is not bool:raise ValueError('stream 必须为布尔值')
        if type(self.compact_target_ratio) not in (int,float) or not .25<=self.compact_target_ratio<=.7:
            raise ValueError('压缩目标比例须为0.25..0.7')
        if not 1<=self.compact_keep_turns<=20 or not 256<=self.compact_summary_tokens<=8192:
            raise ValueError('近期原文轮数须为1..20，摘要输出预算须为256..8192')
        if self.base_url:
            url = urlparse(self.base_url)
            if url.scheme not in ("https", "http") or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError("Base URL 必须是 http(s) 地址，不含账号、查询串或片段")
        if require_ready and (not self.base_url or not self.model.strip()):
            raise ValueError("请先配置 base_url 和 model；API key 可填入配置界面或指定的环境变量")
        if self.tool_mode not in ("native", "json"):
            raise ValueError("tool_mode 必须为 native 或 json")
        for name in ('extra_body','compact_extra_body'):
            extra=getattr(self,name)
            if not isinstance(extra, dict) or set(extra) & {"messages", "model", "tools", "stream", "tool_choice", "api_key", "authorization", "max_tokens"}:
                raise ValueError(f'{name} 必须为对象，不能覆盖消息、模型、工具、鉴权或流式协议')
            try:json.dumps(extra,allow_nan=False)
            except (TypeError,ValueError):raise ValueError(f'{name} 必须为有限JSON数据') from None
        if not 4096 <= self.context_window <= 2_000_000 or not 256 <= self.max_output_tokens < self.context_window:
            raise ValueError("上下文窗口至少 4096，输出上限至少 256 且小于窗口")
        if not 1 <= self.max_steps <= 100 or not 5 <= self.timeout <= 180:
            raise ValueError("工具轮数须为 1..100，超时须为 5..180 秒")

    @property
    def endpoint(self):
        base = self.base_url.rstrip("/")
        return base if base.endswith("/chat/completions") else base + "/chat/completions"

    def public(self):
        value = asdict(self)
        value.pop("api_key")
        return value

    @classmethod
    def load(cls, home: Path = STATE_ROOT):
        path = home / "config.json"
        value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(value,dict):raise ValueError('模型配置须为JSON对象；原文件已保留')
        allowed = set(cls.__dataclass_fields__) - {"api_key"}
        config = cls(**{k: v for k, v in value.items() if k in allowed})
        for field_name, env in (("base_url", "PLC_AGENT_BASE_URL"), ("model", "PLC_AGENT_MODEL")):
            if os.environ.get(env):
                setattr(config, field_name, os.environ[env])
        private = home / "private" / "credentials.json"
        stored = json.loads(private.read_text(encoding="utf-8")) if private.exists() else {}
        if not isinstance(stored,dict):raise ValueError('本机凭据文件须为JSON对象；原文件已保留')
        # A key saved for a different endpoint must never be sent to a new host.
        config.api_key = os.environ.get(config.key_env, "") or (stored.get("api_key", "") if stored.get("base_url") == config.base_url else "")
        config.validate(require_ready=False)
        return config

    def save(self, home: Path = STATE_ROOT):
        from .storage import atomic_json
        self.validate(require_ready=False)
        atomic_json(home / "config.json", self.public())
        path = home / "private" / "credentials.json"
        saved_key = "" if self.api_key and os.environ.get(self.key_env) == self.api_key else self.api_key
        atomic_json(path, {"base_url": self.base_url, "api_key": saved_key})
        if os.name != "nt":
            path.chmod(0o600)


def doctor() -> dict:
    try:
        config = ModelConfig.load()
        return {"status": "configured" if config.base_url and config.model else "setup_required",
                "configuration": config.public(), "has_api_key": bool(config.api_key),
                "state_root": str(STATE_ROOT), "connection_tested": False}
    except (OSError, ValueError) as exc:
        return {"status": "setup_required", "message": str(exc)}
