"""TIA-only process coordination and stage-specific infrastructure diagnostics."""
from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
import tempfile
import time

from .provider import Cancelled


class VendorBusy(Exception):
    pass


@contextmanager
def vendor_lease(timeout, cancel_event=None, *, lock_path=None):
    """Serialize Web/CLI/checkouts for this Windows user, not only one process.

    The OS releases the byte lock if the process exits. Never delete another
    process's lease or terminate existing user Portal/simulator sessions.
    """
    path = Path(lock_path) if lock_path else Path(tempfile.gettempdir())/'plc-workbench-tia'/'vendor.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if path.stat().st_size == 0:
            stream.write(b'0'); stream.flush()
        deadline = None
        while True:
            if cancel_event and cancel_event.is_set(): raise Cancelled('TIA process queue cancelled')
            stream.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK): raise
                now = time.monotonic()
                if deadline is None: deadline = now+timeout
                if now >= deadline: raise VendorBusy('Another workbench Web/CLI process owns the local TIA session') from exc
                if cancel_event: cancel_event.wait(min(.1, max(0, deadline-now)))
                else: time.sleep(min(.1, max(0, deadline-now)))
        try: yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def infrastructure_details(result, directory):
    """Keep the original failure; add evidence-based phase and recovery advice."""
    if result.get('status') not in ('timeout','bridge_error','simulation_error','backend_busy'):
        return result
    directory = Path(directory)
    phase = result.get('phase')
    if phase in ('prepare_card','failed','unknown'): phase=None
    for filename in ('simulator_runtime.json', 'bridge_progress.json'):
        if phase: break
        try:
            snapshot = json.loads((directory/filename).read_text(encoding='utf-8-sig'))
            phase = snapshot.get('phase')
        except (OSError, ValueError, AttributeError): continue
    text = str(result.get('message',''))
    if 'EngineeringSecurityException' in text:
        kind = 'openness_access'
        advice = 'TIA Openness 访问初始化失败；检查本机访问授权及运行用户。未开始候选代码验证，不要修改 SCL。'
    elif 'PowerOn' in text and ('Timeout' in text or 'Error Code: -11,' in text):
        kind = 'startup_timeout'
        advice = ('PLCSIM 上电超时。若出现 21 天试用提示，请在新一轮启动时及时点击 OK；'
                  '没有提示时检查 simulator_runtime.json 的状态和许可，不能据 Timeout 推定未确认提示。'
                  '待本次实例清理完成后，用同一份源码重跑；不会自动修改代码或无限重试。')
    elif result.get('status')=='timeout':
        kind = 'stage_timeout'
        advice = '本阶段超时；结合阶段记录与 stderr 检查 TIA/仿真环境和时间预算，用同一源码复验。'
    else:
        kind = 'vendor_environment'
        advice = '保留厂商错误，先检查本机环境；这不是候选逻辑失败，不应触发模型源码修复。'
    return {**result, 'phase':phase or 'unknown', 'failure_kind':kind, 'recovery_hint':advice}
