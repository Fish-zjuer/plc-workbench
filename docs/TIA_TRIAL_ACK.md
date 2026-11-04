# PLCSIM 试用通知的命令行辅助工具

Siemens 文档说明，试用实例启动时会显示剩余天数通知，未及时确认会导致启动失败。当前 V8 API 头文件提供 PowerOn 和许可状态读取，未发现确认该通知的专用接口。[官方试用说明](https://docs.tia.siemens.cloud/r/simatic_s7_1500_et_200mp_manual_collection_enus_21/comprehensive-information/cpu-function-manuals/s7-plcsim-advanced/installing/introduction/trial-license?contentId=xlNJOAPK2cqXCzika8BSFQ)

新增 `integrations/tia_trial_ack` 是独立 Windows UI Automation 监听器。由命令行启动后，识别符合条件的试用剩余天数通知，并通过该按钮的 InvokePattern 执行 OK。它不需要坐标或全局回车。

## 运行

在仓库根目录的 PowerShell 执行一次，随后正常启动工作台检查任务：

```powershell
.\scripts\start_tia_trial_ack.ps1 -Acknowledge
```

默认后台运行 30 分钟，最多确认 10 个匹配通知，结束后退出。脚本返回 PID、输出及错误日志路径。日志保存在 `outputs/trial_ack`。不传 `-Acknowledge` 时仅观察，不点击。

```powershell
.\scripts\start_tia_trial_ack.ps1 -Acknowledge -TimeoutSeconds 3600 -MaxClicks 20
```

直接以前台命令行运行也可：

```powershell
.\integrations\tia_trial_ack\bin\Release\net48\TiaTrialAck.exe --ack-trial-notice --timeout-seconds 1800 --max-clicks 10
```

## 匹配条件与边界

- 窗口标题包含 PLCSIM，所属进程位于 Program Files 中的 Siemens 安装目录，且文件公司信息包含 Siemens。
- 通知文字同时包含试用许可、到期/剩余提示及具体天数。
- 只有一个可用、可见的 OK/确定按钮，并能获取 InvokePattern。
- 激活、Skip、允许访问、密码和 Openness 等其他窗口不处理；试用期不会被延长，许可证不会被修改。
- 需要解锁的交互式 Windows 桌面；工具与目标窗口的权限等级需要兼容。无法读取或调用按钮时保留窗口，不改用盲目回车。

该工具是可选辅助程序，没有接入默认 Trial/Campaign。

## 验证范围

.NET Framework 4.8 x64 构建通过，8 项纯匹配正负例通过。实际 PLCSIM 试用通知的识别与 OK 调用已验证；原生行为结果见 [最终报告](../reports/tia_final_20261104/README.md)。

需要解锁的交互式桌面；不同安装版本、窗口文字和权限等级需单独验证。进程状态及确认次数可从脚本返回的运行日志查看。
