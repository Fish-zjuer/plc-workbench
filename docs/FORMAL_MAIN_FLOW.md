# 形式化主流程

## 范围和输入

单题和批量共用 `evaluate_candidate → dataset_formal.attach → plcverif_backend.verify`，所有题目均进入同一个入口。编译或功能测试尚未通过时，形式化逐条记录not_executed并优先返修原问题。

规约在 `datasets/course32.json` 的每题 `ltl` 中：

- `properties`：性质ID和原始公式；当前共233条。
- `definitions` / `definitions_and_rules_markdown`：文字定义。
- `semantics`：扫描采样和有限前缀语义。
- `execution.bindings`：把辅助命题展开为接口表达式或独立观察器值。
- `execution.declarations`：观察器存储；`entry`在调用前快照接口，`before`在调用后更新观察器，`after`在本次性质采样后更新历史。
- `execution.assumptions`：该模型适用的调用方输入约定；与结果同时保存。
- `execution.requires_model`：尚缺的平台模型，明确阻塞，不生成假断言。

JSON、文本形式的LTL共用一个读入函数。纯文本每行一个公式，可使用 `P01: G(Stop -> !Run)`，空行及以#或//开头的注释忽略。未知符号、重复ID和不支持的语法均报明原因。

## 有界含义

默认前20次FB调用，规约采样周期10ms，可在网页“模型与环境”修改。涉及独立时钟的规约按固定周期解释；含CycleTime的题目还保留其调用间隔约定。第一次调用时刻为0，周期模型的第N次采样时刻为(N-1)×周期。CODESYS原生定时器仍需要准确的库和时钟模型，不能仅靠周期配置宣称兼容。

调用方在每次扫描开始提供声明类型范围内的非确定输入，并受记录的假设约束。独立包装FB调用原候选，然后计算辅助命题。执行到上界后冻结候选和观察器；后续循环不再成为有效采样。先检查所有路径能完成指定扫描前缀，避免候选卡在扫描内时得到真空结论。

G/F/X/U按有限前缀解释，X跳到下一扫描结束而非下一条ST指令，R1表示当前或下一扫描满足。未来义务因前缀结束而失败时保守记bounded_inconclusive；不将其自动作为返修依据。CBMC入口在每次扫描后记录原子命题，完成N次扫描后由后向递推计算每条LTLf公式，并转换为带性质ID的断言；不把LTL直接交给只支持安全断言的PLCverif CBMC接口。

## 工具及准确性限制

默认使用PLCverif + CBMC。首次没有配置文件时，自动发现项目tools目录、同级plcverif、PATH和JAVA_HOME中的工具；不依赖开发者盘符。网页“模型与环境”提供PLCverif CLI、Java和CBMC可执行文件路径，保存时自动生成本机agent_data/formal_config.json，启动时自动读回。Java需匹配使用的PLCverif包。运行保存配置快照；tools_ready只表示可执行文件存在。

当前支持范围仍不完整：

- 30题已有辅助命题转换定义；其可转换性不等于已验证候选程序或独立审核了所有解释。
- PUBLIC_08的开放数组/结构体IN_OUT和PUBLIC_18的VARIANT引用仍需准确的调用方、容量、类型及别名模型，当前报告unsupported_model。
- CBMC模型保留REAL/LREAL为IEEE binary32/binary64，不使用nuXmv的定点近似。当前导出适配根据CFA宽度补充REAL常量后缀，并修正nondet_float函数声明；同值常量混用32/64位、REAL数学库调用等仍拒绝，不猜测类型。ST前端到C的全语义等价尚未得到证明。
- 其他不支持的CODESYS语法、类型转换和库会附实际诊断，不能通过改弱公式替代模型适配。

模型副本中的有限语法转换记录在source_adaptations中。原源码SHA256与派生源码SHA256分别保存。[CODESYS枚举文档](https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_datatype_enum.html)规定默认基类型为INT；当前只降低具有零默认值、明确整数成员的枚举，其他情况保守拒绝。

PLCverif的建模任务使用一个仅保留观察变量的内部条件，并故意不调用其默认后端；plcverif.log末尾可能出现构建专用引擎不存在的信息。这个条件的结论不作为验证结果。默认CBMC使用结构化C模型，禁用模型约简。原始导出保存在model/ltl-model.c和CFA文件中，适配后输入为checked.i，参数保存在cbmc-command.json，完整结果为cbmc.json。checked.i已包含固定宽度类型定义和宽度断言，不需要GCC或Visual Studio头文件。旧nuXmv分支保留作诊断回退，含浮点时仍拒绝其近似模型。

内部循环展开默认256，可在网页调整；实际值至少为扫描上界+1。开启展开完整性、数组边界、指针、除零、无效移位和有符号整数溢出检查；任一失败均阻止性质计入通过。通过独立域见证断言确认存在满足全部假设的完整扫描轨迹，防止空输入域导致真空通过。域见证的FAILURE表示找到了有效轨迹，这是预期结果，不是LTL违反；因此不能直接用CBMC总退出码判断性质。

## 状态、返修与预算

- bounded_pass：列出的性质在记录范围与假设下通过源模型检查，不是无限扫描证明。
- counterexample：源模型给出违反安全性质的反例；未声称在CODESYS复现。
- bounded_inconclusive：有限前缀不能兑现未来义务、内部循环展开不足、模型安全检查失败或不存在有效输入域；具体原因及检查结果随报告保存。
- unsupported / unsupported_model：缺少准确模型、前端特性或辅助定义。
- timeout / not_configured / interrupted：超时、环境缺失或取消。

编译和功能测试结论独立保存。源模型反例使主流程停在formal_blocked；只有经过真实平台复核，才适合进一步开放自动返修。当前不会让作者根据未确认的反例反复改程序。

每题原预算仍为6个源码版本、24次实际模型请求、1800秒。形式化不调用模型；默认每版120秒，受整题剩余时间限制，排队也计时。已完整返回的逐条结果保留。CBMC超时而JSON未完整返回时不推断任何性质通过；保留原始输出。Windows子进程组设置内存与CPU上限，并支持取消。

## 输出和运行

重启start.cmd后重新导入更新的course32.json，再运行“编译与验证检查”或“生成并自动修复”。旧实验和旧导入版本保留其快照，不自动替换。

每题 `details/submissions/N/formal/` 保存requirements.json、formal.json、candidate.scl、生成模型、checked.i、cbmc-command.json、plcverif.log、cbmc.json及counterexamples.json（有实际检查时）。失败或取消也保存已生成的诊断。完整运行日志位于每题外层run.log和details/events.jsonl，网页可下载。

完整32题的准确验证覆盖尚未完成；运行时的未支持状态必须保留在总性质分母中。
