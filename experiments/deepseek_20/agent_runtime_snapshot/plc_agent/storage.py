from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
import uuid
from contextlib import contextmanager

from .config import DEFAULT_MODEL, STATE_ROOT


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def identifier(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{12}", value):
        raise ValueError("无效的项目/会话编号")
    return value


class Project:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.workspace = self.path / "workspace"
        self.data = json.loads((self.path / "project.json").read_text(encoding="utf-8"))

    @classmethod
    def create(cls, title: str = "PLC 项目", home: Path = STATE_ROOT) -> "Project":
        ident = uuid.uuid4().hex[:12]
        path = home / "projects" / ident
        (path / "workspace").mkdir(parents=True)
        atomic_json(path / "project.json", {"schema": 1, "id": ident, "title": title[:100],
                                           "created_at": now(), "attachments": [], "last_session": None})
        return cls(path)

    @classmethod
    def load(cls, ident: str, home: Path = STATE_ROOT) -> "Project":
        return cls(home / "projects" / identifier(ident))

    @staticmethod
    def list(home: Path = STATE_ROOT) -> list[dict]:
        result = []
        for path in (home / "projects").glob("*/project.json"):
            try:
                result.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return sorted(result, key=lambda p: p["created_at"], reverse=True)

    def save(self):
        atomic_json(self.path / "project.json", self.data)


class Session:
    def __init__(self, project: Project, data: dict):
        self.project, self.data = project, data
        self.lock = threading.RLock()
        self.path = project.path / "sessions" / data["id"]
        self.path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def create(cls, project: Project, model: str = DEFAULT_MODEL) -> "Session":
        session = cls(project, {"schema": 1, "id": uuid.uuid4().hex[:12], "created_at": now(),
                                "model": model, "mode": "plan", "thread_id": None, "plan": [],
                                "token_usage": {}, "compactions": 0, "status": "idle", "last_error": None,
                                "auto_compact_at": 0.75})
        session.save()
        project.data["last_session"] = session.data["id"]
        project.save()
        return session

    @classmethod
    def load(cls, project: Project, ident: str) -> "Session":
        path = project.path / "sessions" / identifier(ident) / "session.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["status"] in ("running", "compacting"):
            data.update(status="interrupted", last_error="上次进程未正常结束；记录已保留，可继续对话。")
        return cls(project, data)

    def save(self):
        with self.lock:
            atomic_json(self.path / "session.json", self.data)

    def event(self, kind: str, **payload) -> dict:
        event = {"time": now(), "kind": kind, **payload}
        with self.lock, (self.path / "events.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
        return event

    def events(self) -> list[dict]:
        path = self.path / "events.jsonl"
        result = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    result.append(json.loads(line))
                except ValueError:
                    continue  # Preserve earlier complete records after a partial crash write.
        return result

    def export(self) -> Path:
        path = self.path / "transcript.md"
        lines = [f"# {self.project.data['title']}", "", f"会话 {self.data['id']} / 模型 {self.data['model']}", ""]
        for event in self.events():
            if event["kind"] in ("user", "assistant", "notice", "error", "tool"):
                lines.extend([f"## {event['kind']} · {event['time']}", "",
                              event.get("text") or json.dumps(event.get("result", {}), ensure_ascii=False, indent=2), ""])
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    @contextmanager
    def lease(self):
        """OS releases this exclusive lock even after a crash; no stale PID guessing."""
        path = self.project.path / "run.lock"
        with path.open("a+b") as stream:
            if path.stat().st_size == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise RuntimeError("同一项目已在另一个进程运行") from None
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
