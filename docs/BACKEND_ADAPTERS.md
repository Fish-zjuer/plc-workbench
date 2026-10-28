# 执行后端接口：为 R5 合并保留边界

target 是希望验证的平台，executor 是实际执行器。未知 executor 会阻塞，不会悄悄退回本地执行。

注册只能由宿主 Python 完成。模型工具不能提供 shell 命令、导入任意模块或注册后端。R7 已在 codesys.py 实现并注册官方 CLI/仿真适配器；本机尚未安装 CODESYS，厂商执行待实测。下面说明外部 R5 合并边界，实际配置见 [接入说明](CODESYS_FORMAL.md)。

~~~python
from plc_agent.task_backend import register_backend

class CodesysBackend:
    name = "codesys"
    def capabilities(self, spec, code=""):
        # 核对安装、版本、库、设备、原接口和语法。
        # 返回 status、blockers（feature/message/actions）、
        # target_compile、executor、scope。
        ...
    def fingerprint(self):
        # 绑定真实编译器/运行时、库、设备描述、适配器与判据。
        return "sha256..."
    def evaluate(self, source, spec, cancel_event=None, extra_cases=()):
        # 独立工程导入原 ST，真实编译并重放基线及回归场景。
        # 返回 (result, artifact)，不修改冻结约定。
        ...
    def replay(self, artifact, spec, cases, cancel_event=None):
        # 相同采样约定，每场景全新 FB；审查会调用两次。
        # 返回 status/cases/summary。
        ...

# R7 已占用 codesys 名称；合并时替换现有实现，或另取受信任适配器名称。
register_backend("codesys_r5", CodesysBackend)
~~~

任务选 executor="codesys"，target="codesys"。受信任启动代码导入注册模块即可。接口不依赖 CLI/TUI 或某家模型服务。

result 包括 source_sha256、execution_fingerprint、behavior_tested、status、target_compile 和真实扫描行。artifact 具有 source_sha256、execution_fingerprint 属性，其余由适配器管理。

扫描格式：

~~~json
{
  "status": "pass",
  "cases": [{
    "name": "stop_priority",
    "covers": ["R2"],
    "status": "pass",
    "first_failure": null,
    "rows": [{
      "time_ms": 0,
      "inputs": {"start": true, "stop": true},
      "actual": {"running": false},
      "violations": []
    }]
  }],
  "summary": {"scenarios": 1, "scans": 1, "assertions": 1, "failed": 0}
}
~~~

复用 task_runner.monitor，把读取实际输出与按约定判定分开。不能用手写输出表代替运行 ST。

target_compile="passed" 必须附真实目标编译日志和版本信息，这仍不代表实体 PLC。仅编译通过却没有行为轨迹，不能返回 status="pass"。缺依赖、超时、运行错误等抛出 BackendError，取消抛出 Cancelled。

## 第 18 题

R4 的 PV_COUNT/PV_COMPATIBLE/PV_READ/PV_WRITE 是本地原语。通用任务阻止它被当作厂商兼容结果。CODESYS 官方说明 ANY/ANY_<type> 用于泛型输入，内部转成 typeclass、pvalue、diSize 结构；不能据此把任意 VAR_IN_OUT VARIANT 直接改名就当作兼容。

可保留三种不同结果：

1. 原题接口：能力阻塞及具体诊断。
2. 明确命名的 CODESYS 适配：附库、类型、调用方式并真实编译。
3. 明确命名的具体类型版本，例如 DINT FIFO；不能将其成绩冒充原题完成。

本轮未偷改原题接口。R5 可复用通用编排、会话、模型配置、交付及证据记录。

合并时实际核对接口方向、引用别名、时间推进、首扫和复位语义、取消与超时、每行是否来自目标运行时，以及后端改变能否使旧记录失效。R4 原题库结果单独保留，不覆盖历史原始分数。

资料：[CODESYS ANY](https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_datatype_any.html)、[CODESYS TON](https://content.helpme-codesys.com/en/libs/Standard/Current/Timer/TON.html)。本轮仅据文档和本地运行分析，未调用厂商编译器。
