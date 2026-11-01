"""Lazy access to the explicitly removable local testing fallback."""
from importlib import import_module
from plc_probe.backend import BackendError


def backend():
    try:return import_module('optional_local_tests.dataset_backend')
    except ModuleNotFoundError as exc:
        if exc.name not in ('optional_local_tests','optional_local_tests.dataset_backend'):raise
        raise BackendError({'status':'missing_dependency','test_backend':'optional_local',
            'message':'本地备用测试目录 optional_local_tests 已删除；请启用 CODESYS 编译与仿真测试。'}) from exc
