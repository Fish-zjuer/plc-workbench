# GitHub源码与Release ZIP

- 当前仓库来自已通过解压自检的R4分享包，未导入agent_data、密钥、账户余额原始记录或运行环境。
- Python依赖wheel放在Release ZIP中，源码默认不提交；setup.ps1在源码使用场景会校验下载。
- 原ZIP文件清单保存在docs/TEAM_PACKAGE_MANIFEST.json，仅对应下载附件，不对应这个Git工作区。
- 本机实验快照可能包含原机绝对路径，不是接收电脑的配置。
- 最新验证：20份候选通过当前有限离线检查；125项工具回归通过、1项跳过；尚未验证厂商ABI、形式化求解器或实体PLC。
