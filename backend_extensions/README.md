# PLC-R4 后端扩展

扩展来自[STruC++](https://github.com/Autonomy-Logic/STruCpp)，固定提交`fcccfbdf53704fad1f5e71dd2a05d440b9028b47`，源码及审查用测试改动完整保存在[strucpp_r4.patch](strucpp_r4.patch)。原0.7.0发布版保留，R4安装到工作区缓存的独立目录，构建产物有SHA清单。

## 扩展内容

- 注册LTIME，支持LT#/LTIME#字面量及转换；大时长字面量用BigInt计算后输出精确C++整数，避免JavaScript Number的53位精度损失。
- `TIME_TO_LINT`为毫秒；`LTIME_TO_LINT`为纳秒；时长内部表示为有符号64位纳秒。范围及TIME内部64位存储是这个离线后端的选择，不等同于所有厂商的32位TIME实现。
- 开放数组成员可处于未绑定的空状态；绑定实际调用方的存储并保留下界。越界访问受检查。这里只扩展一维数组。
- 添加本地`VARIANT`类型擦除引用描述符，以及PV_COUNT/PV_COMPATIBLE/PV_READ/PV_WRITE。它们是容量查询、类型检查和一个元素的复制原语，不包含FIFO算法。队列计数、循环索引、边沿及复位优先级都必须在ST中实现。
- 修复源码构建工具在Windows文件URL和中文路径中的问题。编译器前置启动器使用Windows Job Object，外层超时终止时会清理它启动的Node进程。

## PV1 引用契约

| 函数 | 行为 |
|---|---|
| PV_COUNT(buffer) | 已绑定非空一维数组的元素数，须适配正DINT；无效返回0 |
| PV_COMPATIBLE(buffer,item) | 验证数组元素与可写标量的具体C++类型及宽度一致 |
| PV_WRITE(buffer,index,item) | 将标量当前值存入数组第index个元素 |
| PV_READ(buffer,index,item) | 把数组第index个元素复制到标量 |

index是从0开始的相对位置。复制函数在未绑定、类型不匹配或越界时返回FALSE且不写数据。测试覆盖DINT、REAL、BOOL和含两个字段的记录；采用类型化赋值，支持记录元素的字段复制。它没有模拟Siemens或CODESYS的内存布局，也没有完成这些平台的导入/导出。

## 构建与选择

在项目目录中使用准备好的Python，构建还需要Git、Node≥22、npm和g++。

```powershell
python -B -m plc_agent.backend_r4 build
python -B -m plc_agent.backend_r4 activate
python -B -m plc_agent.backend_r4 status
# 切回保留的原发布版
python -B -m plc_agent.backend_r4 legacy
```

构建只使用固定提交及package-lock，不运行npm安装生命周期脚本。选定状态保存在忽略目录`agent_data/backend.json`；用户也可以用STRUC_PP_HOME显式覆盖。缓存依据编译器、运行库、库归档、Node和g++的内容隔离，避免换后端后复用旧程序。选中R4时会核对产物清单，发现修改则要求重建。

原题判据文件不随补丁修改；参考数组/FIFO及补充时长测试另外保存在`plc_agent/reference_checks.py`、`duration_checks.py`。通过记录绑定候选SHA、后端指纹和判据指纹，任一变化后都需要重新验证。

## 许可证

编译器改动及启动器按GPL-3.0-only提供；运行库改动按GPL-3.0及STruC++ Runtime Library Exception提供。原许可证[COPYING](COPYING)、[COPYING.RUNTIME](COPYING.RUNTIME)和[LICENSE](LICENSE)保留在本目录，安装目录也带同样文件。分享此扩展时应同时提供固定源码提交、补丁及构建方法。

这套后端用于离线有限行为检查，没有运行厂商编译器、形式化求解器或实体PLC。
