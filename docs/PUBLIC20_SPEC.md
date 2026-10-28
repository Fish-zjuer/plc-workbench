# 公共20题：规约、采样及实验边界

版本：public20-spec-v1；题面以 `experiments/deepseek_20/questions.json` 为准。这里只处理公共20题。下列LTL是逐题需求规约，不是已经由PLCVerif证明的结论；本项目实际执行的自动检查是有限场景与独立数值/状态观察器。测试覆盖不等于整个规约覆盖。

## 公共记号与观察器定义

`G p`表示始终，`X p`表示下一次扫描，`F p`表示最终，`p U q`表示在q成立前持续p。`R1(p)`是LTL宏`p | X p`，表示当拍或下一拍响应；其允许时间是扫描次数，不是固定毫秒。展开时保留括号。安全停机和互锁的同拍规则不使用R1。

普通观测状态同时包含本次调用前的输入、调用前的数据副本`pre`及本次FB调用后的输出`post`。`rise(x)`由输入观察器保存前次x计算；计时器根据测试给出的真实时间戳计算，不使用被测程序自己的内部计时值。`initial`指FB实例创建后、第一次调用前的初始化状态。除初始化性质外，公式只在正常调用观测状态解释。

下文`sumOK`、`queueAfterPopOK`等名字是原子命题：由紧邻说明给出的独立数学定义求值，不是模型自己报告的布尔变量。有限数组上的“每个i”表示对实例的所有合法索引分别展开一条LTL。对任意具体数组长度的性质，应针对该实例展开；本项目没有声称证明无限容量。

除明确写明的输入域外，不替题面新增错误处理。多个操作同时发出、模式切换的状态保持、未定义的首扫历史等若未明确，不计为无条件缺陷。REAL/LREAL的执行比较分别采用1e-5/1e-9绝对和相对容差，数学规约仍用精确表达式。

## Q01 灌装线

观察器按输入维护独立阶段：idle→clean→fill→cap→pack→done→idle。idle仅由bottleSensor启动；clean/fill/cap/pack分别由对应ConfirmButton推进；done仅由finishedButton复位。阶段错误的确认按钮不推进。阶段输出依次为Pump_Motor、Filling_Valve、Capping_Machine、Packing_Machine、Completion_Light。`stageOutputOK`表示对应阶段输出有效且其他阶段输出关闭，这是当前有限测试采用的顺序工序解释。

```text
G(idleBefore & bottleSensor -> R1(cleanOutputOK))
G(cleanBefore & cleaningConfirmButton -> R1(fillOutputOK))
G(fillBefore & fillingConfirmButton -> R1(capOutputOK))
G(capBefore & cappingConfirmButton -> R1(packOutputOK))
G(packBefore & packingConfirmButton -> R1(doneOutputOK))
G(doneBefore & finishedButton -> R1(idleOutputOK))
G(waitingForCurrentConfirmation -> currentStageHeld)
G(wrongStageConfirmationOnly -> observerStageUnchanged)
```

按钮用单拍脉冲或阶段内有效电平测试，不对“到站前始终按住确认”的未定义策略打分。阶段和输出的对应表构成上述原子命题的完整定义。

## Q02 DWORD边沿检测

跳过第一次调用的历史初始化差异。从第二次调用起，独立保存`prevValue`：`rising=value & ~prevValue & 0xFFFFFFFF`，`falling=prevValue & ~value & 0xFFFFFFFF`；popcount为32位中1的个数。

```text
G(historyReady -> risingBitsOK)
G(historyReady -> fallingBitsOK)
G(historyReady -> risingCountOK)
G(historyReady -> fallingCountOK)
G(historyReady -> changedFlagOK)
G(historyReady -> risingFlagOK)
G(historyReady -> fallingFlagOK)
```

命题分别定义为`risingBits=rising`、`fallingBits=falling`、`noOfRisingBits=popcount(rising)`、`noOfFallingBits=popcount(falling)`、`hasChanged=(value!=prevValue)`、`hasRisingEdges=(rising!=0)`、`hasFallingEdges=(falling!=0)`。

## Q03 滞环报警

`invalidLimits`为loLevel>=hiLevel；`invalidWindow`为hystWindow>=hiLevel-loLevel且非invalidLimits；`valid`为两者均否。`highSet/Reset`分别为Value>hiLevel、Value<hiLevel-hystWindow；低报警相反，严格比较；边界相等保持上一报警状态。无效配置时的报警输出是否清零，题面没有统一规定，不作为规约必须项。

```text
G(invalidLimits -> error8001)
G(invalidWindow -> error8002)
G(valid -> normalStatus)
G(valid & highSet -> hiAlarm)
G(valid & highReset -> !hiAlarm)
G(valid & highBand -> highAlarmHeld)
G(valid & lowSet -> loAlarm)
G(valid & lowReset -> !loAlarm)
G(valid & lowBand -> lowAlarmHeld)
```

`error8001/8002`包含error=TRUE及相应status；normalStatus表示error=FALSE、status=0。highBand/lowBand为既不触发也不复位的区间；Held表示post报警等于pre报警。负滞环的额外处置不打分。

## Q04 黏度泵、消抖及维护

v3采样约定：CycleTime等于距离上一实际调用的间隔，首拍为0ms；固定扫描不再跳过中间时间却只累计一拍。

`permissive=VISCOSITY_OK & PASTE_E_STOP_NC`；`debounced`由独立连续有效时钟计算，首次有效时elapsed=0，elapsed>=DebounceTime时有效。当前有限测试采用急停恢复后重新确认的解释。`runtimeOK`表示本拍运行时post累计=pre累计+CycleTime，停机时保持；时间统一换算到相同单位。`maintenanceOK`表示PUMP_MAINT_DUE与累计>=500小时等价。

```text
G(initial -> pumpInitialOK)
G(!PASTE_E_STOP_NC -> !VFD_RUN)
G(!VISCOSITY_OK -> !VFD_RUN)
G(VFD_RUN -> debounced)
G(permissive & debounced -> VFD_RUN)
G(runtimeOK)
G(maintenanceOK)
```

pumpInitialOK为运行关闭、累计0、维护FALSE。维护到期不加入运行许可。已完成消抖后发生急停的恢复策略在题面中有解释空间；若采用不同契约，应作为协议变更而非直接修改历史分数。

## Q05 焊缝报警与启动抑制

`initializing`为上电后不足5000ms。独立消抖仅在初始化结束且Weld_E_Stop_NC、Gap_Exceeded均真时累计；初始化内或条件失效立即清零。`gapReady`表示消抖达到DebounceTime。

```text
G(initializing -> !Operator_Alert)
G(initializing -> Weld_Soft_Start_Active)
G(!initializing -> !Weld_Soft_Start_Active)
G(!Weld_E_Stop_NC -> !Operator_Alert)
G(!Gap_Exceeded -> !Operator_Alert)
G(!initializing & Weld_E_Stop_NC & gapReady -> Operator_Alert)
G(Operator_Alert -> !initializing & Weld_E_Stop_NC & gapReady)
```

Weld_Soft_Start_Active只表示启动抑制，不解释为连续调速斜坡；急停不产生额外的报警。

## Q06 曝气风机

`eligible=DO_LOW & AERATION_E_STOP_NC`；`delayReady`为自本轮连续eligible首次调用起elapsed>=5000ms。任何eligible失效都会清除观察器时钟。`startCountOK`表示运行输出每次FALSE→TRUE时计数加1，其余保持；有限测试不外推溢出策略。

```text
G(initial -> blowerInitialOK)
G(!eligible -> !BLOWER_RUN)
G(BLOWER_RUN -> eligible & delayReady)
G(eligible & delayReady -> BLOWER_RUN)
G(startCountOK)
```

blowerInitialOK为运行FALSE、计数0。开始计时的首拍elapsed=0，不把某次调用前的未知时间算进等待。

## Q07 五泵切换

独立运行使能锁存器`enabled`在stop时关闭，在start且非stop时开启，其余保持；停止优先是当前测试口径。`manualSelectionOK`为每个RunComd=enabled & selection。`topThreeOK`为启用自动模式恰好3泵运行，且任一运行泵的priority不低于任一备用泵。`configPreserved`表示priority和selection均未被FB改写。

```text
G(stop -> allPumpsOff)
G(!enabled -> allPumpsOff)
G(!mode & enabled -> manualSelectionOK)
G(mode & enabled -> topThreeOK)
G(configPreserved)
```

优先级较大者优先；边界相同优先级允许任意满足topThreeOK的选择，不把未规定的索引优先当必需条件。当前结构体适配采用调用方持有数据的显式copy-in/copy-out，未证明厂商ABI兼容。

## Q08 模拟量批处理

调用方保证0<=count<=两个数组长度的较小值。第k个元素配对各自lowerBound+k。FB只能写被处理通道的retVal/outputValue；原始值、配置、未处理通道保持。禁用通道不执行转换。

```text
G(rawArrayPreserved)
G(channelConfigPreserved)
G(unprocessedChannelsPreserved)
G(enabledInvalidMode -> channelError8001)
G(enabledInvalidLimits -> channelError8002)
G(enabledValidMode0 -> linearScalingOK)
G(enabledValidMode1 -> standardTemperatureOK)
G(enabledValidMode2 -> climaticTemperatureOK)
```

对所有处理通道逐项展开：单极性缩放loLIM+raw*(hiLIM-loLIM)/27648；双极性为loLIM+(raw+27648)*(hiLIM-loLIM)/55296；温度分别raw/10、raw/100。模式不在0/1/2时报8001，hiLIM<=loLIM时报8002。两种错误同时发生时的优先级、禁用时输出值和超量程钳位未由题面完整规定，应单列假设，不能无条件作为模型缺陷。

## Q09 移动平均

`validWindow`为1..100；`sample`为cyclicExecution或rise(trigger)。独立历史H在reset时清空，在合法采样时将data加入末尾、仅保留最近windowLength个样本；`meanOK`为average=sum(H)/len(H)，使用独立重算而非复用候选环形数组。无样本时average值不打分。

```text
G(!validWindow -> windowError8200)
G(validWindow -> normalStatus)
G(validWindow & reset -> historyEmpty)
G(validWindow & !reset & sample -> newHistoryOK)
G(validWindow & !reset & !sample -> historyHeld)
G(validWindow & nonemptyHistory -> meanOK)
```

当前有限测试在实例内固定窗口，避开reset与采样同拍；若要评价动态窗口与重置优先级，应先补充独立需求，不能凭某份实现选择规则。

## Q10 温控与过热保护

`sensorFault`为温度<0或>100；`demand`为当前温度<设定；`overrun`为连续加热超过5000ms；独立保护时钟从实际进入保护的时刻开始，`cooling`为保护尚未等待满3000ms。`displayOK`为当前/设定温度显示等于对应输入，HeaterStatus与加热输出一致。

```text
G(sensorFault -> !HeaterOutput)
G(temperatureAboveSetpoint -> !HeaterOutput)
G(overrun -> !HeaterOutput & OverheatProtection)
G(cooling -> !HeaterOutput & OverheatProtection)
G(validSensor & demand & protectionReleased -> HeaterOutput)
G(displayOK)
```

输入恰等于设定值时的滞留/关闭策略未明确，不强加要求。冷却等待不能从保护前的上一调用时间起算，以免缩短实际等待。

## Q11 三工位线

独立工序观察器A→moveB→B→moveC→C→done。A处ButtonA启动至B，B到达停止、ButtonB启动至C，C到达停止、ButtonC点灯，SensorC消失熄灯。自动响应采用当前有限测试的最多一个附加扫描约定。

```text
G(!(MotorForward & MotorReverse))
G(manualForwardOnly -> MotorForward & !MotorReverse)
G(manualReverseOnly -> MotorReverse & !MotorForward)
G(atA & ButtonA -> R1(moveBOutputOK))
G(movingB & SensorB -> R1(motorStopped))
G(atB & ButtonB -> R1(moveCOutputOK))
G(movingC & SensorC -> R1(motorStopped))
G(atC & ButtonC -> R1(CompletionLight))
G(done & !SensorC -> R1(!CompletionLight))
```

单工位按钮不能跳过前序工位；模式切换后是否恢复半成品状态未指定，当前测试不裁定。

## Q12 板厚报警、计数与历史

v3采样约定：固定场景及补充保持场景的CycleTime均等于实际调用间隔。触发拍elapsed=0，后续拍累加；10ms触发、每10ms扫描时，500ms仍需保持，510ms可释放。

`validFault=THICKNESS_SIGNAL_VALID & THICKNESS_FAULT`。独立有效故障上升沿观察器维护计数、最近5个时间戳和最近报警触发时刻；有效性失效清除保持状态，不清除既有统计。`holdRequired`为最近有效触发后不足500ms；`runtimeOK`只在CUTTING_RUN且信号有效且无当前故障时加CycleTime，其余保持。

```text
G(initial -> slabInitialOK)
G(!THICKNESS_SIGNAL_VALID -> !THICKNESS_ALARM)
G(validFault -> THICKNESS_ALARM)
G(THICKNESS_SIGNAL_VALID & holdRequired -> THICKNESS_ALARM)
G(validFaultRise -> countIncremented & newestHistoryShiftOK)
G(!validFaultRise -> faultCountHeld & historyHeld)
G(runtimeOK)
```

newestHistoryShiftOK为post[0]=FaultTimestamp，post[i]=pre[i-1]（i=1..4）；不要求改变外部设备运行许可。初始化计数、累计及历史全0；正常首拍可随后累加CycleTime。

## Q13 HVAC

`eligible=OCCUPANCY_DETECTED & HVAC_MODE_SELECTOR!=3`；独立延时满30000ms为fanReady，条件失效立即复位。`adjustmentOK`由下表精确求值：Night恒4；其他模式occupied为0；unoccupied的Auto为saving?3:2，Comfort为1，Economy为4。

```text
G(initial -> hvacInitialOK)
G(!eligible -> !SUPPLY_FAN_RUN)
G(SUPPLY_FAN_RUN -> eligible & fanReady)
G(eligible & fanReady -> SUPPLY_FAN_RUN)
G(normalCalculation -> adjustmentOK)
G(adjustmentWithinFourDegrees)
```

模式输入限定0..3；节能选择只影响Auto。初始OFF/0指调用前初始化，正常计算随后依当前输入更新。

## Q14 IPv4

独立解析器检查恰好4个非空纯十进制数字段，每段0..255，以3个点分隔。有效值`N=a*2^24+b*2^16+c*2^8+d`；前导零仍按十进制解释，不另加15字符上限。

```text
G(validIPv4 -> parsedNetworkOrderOK)
G(!validIPv4 -> ipValueZero)
```

parsedNetworkOrderOK为ipValue=N，ipValueZero为ipValue=0。覆盖合法0.0.0.0输出0以及合法输入后接非法输入时不能遗留旧值。接口容量和本地执行桥接限制下仅评价有限ASCII输入；当前场景不穷举全部字符串。

## Q15 配比

独立阶段A→B→（processMode?C:mix）→mix→D，阈值分别50、80、100。所有阀门和电机组成allOff。手动每个按钮上升沿单独翻转对应输出，不因按钮保持连续翻转。

```text
G(!estop -> allOff)
G(estop & manualMode & oneManualRise -> matchingOutputToggled)
G(estop & manualMode & noManualRise -> manualOutputsHeld)
G(autoIdle & autoStart -> R1(valveAActive))
G(autoA & levelAtLeast50 -> R1(valveBActive))
G(autoB & levelAtLeast80 & processMode -> R1(valveCActive))
G(autoB & levelAtLeast80 & !processMode -> R1(mixerActive))
G(autoC & levelAtLeast100 -> R1(mixerActive))
G(autoMix & mixMotorComplete -> R1(valveDActive))
```

各Active命题包含关闭前一工序输出。输出动作最多一个附加扫描是当前冻结检查的操作口径；题面未量化延迟，报告应把时序口径不符与更明确的安全/数值错误分开解释。

## Q16 柔性路线

调用方保证processLength为1..8，最后一个有效序号为5，其他为2..4。独立cursor从首项开始，仅在目标站完成后前移。`directionOK`为目标站在当前位置右侧时只右行、左侧时只左行、相同位置不移动；目标sensor到达后停止。

```text
G(!(conveyorLeft & conveyorRight))
G(routeStart -> R1(firstTargetSelected))
G(transporting & !targetReached -> directionOK)
G(targetReached -> R1(conveyorStopped))
G(waitingProcessing & !targetComplete -> cursorHeld & conveyorStopped)
G(waitingProcessing & targetComplete -> R1(nextTargetSelected))
G(finalStationReached -> R1(conveyorStopped))
```

firstTargetSelected、nextTargetSelected比较独立cursor及根据输出方向/后续停站观测的路线，不读取候选内部状态。题面未规定非法路线处理；不把调用方违约输入算作失败。

## Q17 配方管理

请求使用隔开的单拍脉冲，每拍至多一种操作；recipeID为非零标识，0仅代表空槽。独立保存调用前数据库D。exists为有匹配ID，free为有空槽，j为最小空槽索引。相等比较含所有配方字段。

```text
G(query & !exists -> error8001)
G(query & exists -> queryResultMatches)
G(add & exists -> error8002 & databaseHeld)
G(add & !exists & !free -> error8003 & databaseHeld)
G(add & !exists & free -> addedAtFirstFree & otherEntriesHeld)
G(delete & !exists -> error8004 & databaseHeld)
G(delete & exists -> matchingIDCleared & otherEntriesHeld)
G(modify & !exists -> error8005 & databaseHeld)
G(modify & exists -> matchingEntryReplaced & otherEntriesHeld)
G(nonzeroIDsUnique)
```

queryResultMatches为recipeQueryResult=D[匹配索引]；addedAtFirstFree为postD[j]=recipeIn；matchingIDCleared只要求相应recipeID=0，不要求擦除其他无效字段；matchingEntryReplaced为完整替换recipeIn。失败查询的输出保留策略、并发请求优先级和ID0的额外错误码未规定，当前规约不裁定。

## Q18 VARIANT FIFO

容量C由关联数组的实际长度确定，item与buffer元素同型，实例期间buffer关联不变；enqueue与dequeue不能同拍请求。独立数学队列Q初始化为空，保存入队时的值副本，输入观察器检测上升沿。`queueAfterAppend/PopOK`为按FIFO更新Q并正确读写item；物理环形索引是实现细节，不要求固定head/tail布局。

```text
G(initial -> queueEmpty)
G(reset -> queueEmpty & elementCountZero & statusZero)
G(!reset & enqueueRise & notFull -> queueAfterAppendOK & statusZero)
G(!reset & enqueueRise & full -> queueHeld & itemHeld & status8002)
G(!reset & dequeueRise & notEmpty -> queueAfterPopOK & statusZero)
G(!reset & dequeueRise & empty -> queueHeld & itemHeld & status8001)
G(!reset & idleRequest -> queueHeld & statusZero)
G(countMatchesQueue)
G(countWithinCapacity)
```

reset优先，不要求清零物理存储；countMatchesQueue为elementCount=len(Q)，范围0..C。当前CODESYS目标缺少已验证VARIANT适配器，四组统一记platform_blocked，保留在20题分母；R4泛型引用测试不能代替厂商VARIANT编译证据。

## Q19 机械臂

EmergencyStop=FALSE表示急停。调用方保证四个模式互斥。独立动作序列为Down→Grip→Up→Right→Down→Release→Up→Left。动作到位反馈分别用对应LimitSwitch，夹紧/松开采用GripLimitSwitch/ReleaseLimitSwitch；运动初始位为左上。

```text
G(!EmergencyStop -> allArmCommandsOff)
G(manualMode & EmergencyStop -> manualCommandMapOK)
G(actionActive & actionLimitReached -> R1(actionCommandOff))
G(singleStepActionDone & noNewStart -> noNextAction)
G(singleStepReady & startRise -> R1(exactNextAction))
A19 -> G(singleCycleStarted -> F(cycleDone))
G(singleCycleDone & noNewStart -> allArmCommandsOff)
G(continuousRunning & cycleDone & EmergencyStop -> R1(firstAction))
```

manualCommandMapOK对每个动作分别表示command=button & !对应limit；不存在相互矛盾的手动请求时按此求值。exactNextAction由独立序号决定。环境假设A19展开为`G(EmergencyStop) & G(actionActive -> F(actionLimitReached)) & G(singleCycleSelected)`，即整个该项实验不急停、模式固定，启动的动作最终得到正确反馈；不对永远缺少到位信号的环境要求最终完成。暂停、模式切换后的自动恢复策略未明确，不额外规定。

## Q20 五工位线（v2）

独立工序观察器按Feed→Wash→Weight→Firing→Output推进。各完成信号在对应停站阶段有效；传感器按工艺顺序出现。qualified为100<=weight<=200。`temperatureAndDepartureOK`为firingTemp=500+0.5*(weight-100)、MotorForward=TRUE、kick=FALSE。v2中的R1实际由逐扫描响应窗口检查，而非只删除原先的同拍断言。

```text
G(!(MotorForward & MotorReverse))
G(manualForwardOnly -> MotorForward & !MotorReverse)
G(manualReverseOnly -> MotorReverse & !MotorForward)
G(autoIdle & SensorFeed -> R1(MotorForward))
G(movingToWash & SensorWash -> R1(motorStopped))
G(waitingWash & washComplete -> R1(MotorForward))
G(movingToWeight & SensorWeight -> R1(motorStopped))
G(waitingWeight & weightComplete & qualified -> R1(temperatureAndDepartureOK))
G(waitingWeight & weightComplete & !qualified -> R1(kick))
G(movingToFiring & SensorFiring -> R1(motorStopped))
G(waitingFiring & firingComplete -> R1(MotorForward))
G(movingToOutput & SensorOutput -> R1(motorStopped & CompletionLight))
G(finishedProduct & !SensorOutput -> R1(!CompletionLight))
```

motorStopped为两个方向输出均FALSE。单拍kick、保持至产品离开或其他持续形式，只要在响应窗口内正确发出且不违反明确需求，不凭未规定的持续时间判错。当前6个场景覆盖手动互锁及99/100/150/200/201边界，全流程进入烧结、成品、亮灯、取走熄灯。5类已知故障负对照均被检出；当前检查仍不是模式切换与所有生产现场故障的穷举证明。
