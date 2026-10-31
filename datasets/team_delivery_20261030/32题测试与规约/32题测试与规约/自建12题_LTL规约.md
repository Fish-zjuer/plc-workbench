# 自建12题 LTL规约

本文件及同目录 `自建12题_LTL规约.json` 是本次交付的权威 LTL 草案，共12题、85条性质。`自建题库_溯源与评测资料.json` 内的 `ltl_properties` 仅保留历史资料：CUSTOM_01～07为空数组，CUSTOM_08～12为早期草案。新旧草案可能采用不同观察约定，不得直接拼接或混用。以下公式尚未针对目标验证器完成语法转换或实际验证，因此不代表形式化证明已经完成。

# 统一的观察约定

本文件是需求层 LTL 草稿，使用明确数学定义的观察器原子命题，不是 PLCVerif/Z3 的原生输入语法；没有声称完成形式化证明。
一次观测 O_t 同时包含本轮调用前的输入 inputs_t 和本轮调用后的输出 outputs_t。
pre.y 表示本轮调用前保存的输出/状态；从第二次调用起通常等于上一轮 post.y。首次调用的 pre 状态按题目规定初始化。
G p 表示每次观测都满足 p；X p 表示下一轮观测满足 p；F p 表示最终某轮满足 p；U 表示直到。
当前输入触发本轮输出的规则不加 X。涉及上一轮的状态以 pre 或独立观察器表示，不能直接用下一轮输入替代。
initial 专指第一次调用前的初始化检查，与正常 O_t 观测分开。初始输出允许在第一次调用后依输入改变。
R1(p) := p | X(p)，仅用于题面/既有公共测试允许当拍或下一拍响应的工序输出，不能用于放宽急停、互锁等同拍要求。
rise(x) := x_t & !x_(t-1)，首拍历史仅在题目明确时取 FALSE；未明确的首扫历史不评分。
数学表达式先求值为布尔原子命题，再由 LTL 组合。有限数组、掩码上的量词需按实际实例逐项展开；它们不是未定义的模型自报变量。
所有实数输入限定有限值；数值公式是精确数学约束，实际测试按文件中的数值容差比较。测试通过不等于普遍成立。

## CUSTOM_01 电梯方向保持与满载屏蔽目标调度

输入域：CurrentFloor∈1..6，Direction∈{-1,0,1}；数组下界为1、长度6。
E={i | CabReq[i] OR (HallReq[i] AND NOT FullLoad)}；输入数组只读。
令f=CurrentFloor。独立数学选择器T：Enable为FALSE或E为空时T=f；否则f∈E时T=f；
Direction=1且存在i>f时T=min{i∈E:i>f}；Direction=-1且存在i<f时T=max{i∈E:i<f}；
其他情况T为E中使(abs(i-f),i)按字典序最小的楼层。对应方向无请求时转向另一侧最近请求。
selectedOK := TargetFloor=T AND NextDirection=sign(T-f)。requestArraysPreserved表示调用前后两输入数组完全相同。
本题不保存请求队列，不要求最终完成运输；HasTarget不是电机命令。

```text
G(HasTarget <-> (Enable & nonempty(E)))
G(selectedOK)
G((!Enable | empty(E)) -> (!HasTarget & TargetFloor=CurrentFloor & NextDirection=0))
G((Enable & CurrentFloor_in_E) -> (HasTarget & TargetFloor=CurrentFloor & NextDirection=0))
G(HasTarget -> targetInE)
G(requestArraysPreserved)
```

## CUSTOM_02 工业 HMI 访问权限与参数写入控制

V := SessionValid AND Role∈{1,2,3}。AllowedPages(1)={1,2}，AllowedPages(2)={1,2,4}，AllowedPages(3)={1,2,3,4}，其他角色为空集。
view := V AND Page∈AllowedPages(Role)。write := SessionValid AND Role∈{2,3} AND Page=4。
accept := WriteReq AND write AND 0<=WriteValue<=100。所有LREAL输入有限。
parameterUpdated := ParamValue=WriteValue；parameterHeld := ParamValue=pre.ParamValue；初始pre.ParamValue=0。
Accepted/Denied为本轮结果，WriteReq为调用方提供的单扫描请求；本题不替上游做身份认证。

```text
G(ViewAllowed <-> view)
G(WriteAllowed <-> write)
G(Accepted <-> accept)
G(Denied <-> (WriteReq & !accept))
G(accept -> parameterUpdated)
G(!accept -> parameterHeld)
G(!(Accepted & Denied))
```

## CUSTOM_03 远程闸门站报文新鲜度与远程写入恢复

独立观察器保存known、seq、age、fault，初始分别FALSE、0、0、TRUE；它不是候选ST的内部变量。
validTiming := 1<=DtMs<=1000 AND 1<=TimeoutMs<=60000。每轮按下列完整转移生成观察器期望：
Reset最高优先：known=FALSE、seq=0、age=0、fault=TRUE，fresh=FALSE，err=FALSE，忽略其余输入。
否则若参数非法：known/seq/age保持，fault=TRUE，fresh=FALSE，err=TRUE。
否则fresh := FrameValid AND (!pre.known OR FrameSeq!=pre.seq)；fresh时known=TRUE、seq=FrameSeq、age=0；
无fresh时known/seq保持，age=min(60000,pre.age+DtMs)。fault从pre.fault开始，age>=TimeoutMs时置位，fresh AND Ack时清除。
序号只比较不相等，4294967295到0也是新帧，不是防重放认证。
monitorMatch := Fresh=fresh AND AgeMs=age AND CommFault=fault AND Error=err。
permit := !Reset AND !err AND !fault AND age<TimeoutMs；ageHeld := AgeMs=pre.age。
historyHeld := known=pre.known AND seq=pre.seq，为观察器转移定义；不要求读取ST私有历史。

```text
G(monitorMatch)
G(RemoteWritePermit <-> permit)
G(Reset -> (!Fresh & AgeMs=0 & CommFault & !RemoteWritePermit & !Error))
G((!Reset & !validTiming) -> (Error & CommFault & !Fresh & !RemoteWritePermit & ageHeld))
G((!Reset & validTiming & !fresh) -> (AgeMs=min(60000,pre.age+DtMs)))
G((!Reset & validTiming & fresh & Ack) -> (!CommFault & RemoteWritePermit))
G((!Reset & validTiming & pre.fault & !(fresh & Ack)) -> CommFault)
```

## CUSTOM_04 收放卷卷径估算与转速补偿

PI=3.141592653589793，CoreD=76，MaxD=140，h=0.135，Lmax=PI*(140^2-76^2)/(4*h)。
独立观察器初始initialized=FALSE、length=0、diameter=76。init := !pre.initialized OR Reset。
valid := -15<=SpeedMpm<=15 AND 0<=EncoderDelta<=1000000 AND (!init OR 76<=InitialD<=140)，输入均有限。
valid AND init时length=PI*(InitialD^2-76^2)/(4*h)，diameter=InitialD，rpm=0，hit=FALSE，initialized=TRUE；忽略脉冲。
valid AND !init时raw=pre.length+(Receiving?1:-1)*EncoderDelta*PI*50/1024，length=clamp(raw,0,Lmax)，
diameter=sqrt(76^2+4*h*length/PI)，rpm=clamp(SpeedMpm*1000*50/(PI*diameter),-6000,6000)，hit=(raw<0 OR raw>Lmax)。
!valid时length/diameter/initialized保持，rpm=0，hit=FALSE；不是无条件Reset优先于输入校验。
geometryMatch表示StoredLength/ Diameter/MotorRPM/LimitHit分别等于上述独立期望。
长度和直径测试绝对容差0.001mm，RPM为0.01；LTL数学定义精确，测试容差不改变限幅严格边界。

```text
G(Error <-> !valid)
G(geometryMatch)
G((!valid) -> (MotorRPM=0 & !LimitHit & StoredLength=pre.length & Diameter=pre.diameter))
G((valid & init) -> (Diameter=InitialD & MotorRPM=0 & !LimitHit))
G((valid & !init) -> (LimitHit <-> (raw<0 | raw>Lmax)))
G(0<=StoredLength & StoredLength<=Lmax & 76<=Diameter & Diameter<=140)
G(-6000<=MotorRPM & MotorRPM<=6000)
```

## CUSTOM_05 轨道巡检车按里程触发图像采集

独立观察器保存first、prevEnable、origin、spacing、lastDistance、k、issued、missed、err；初始first=TRUE，其余计数0、err=FALSE。
init := first OR Reset OR (Enable AND !pre.prevEnable)。validInit := DistanceMm>=0 AND SpacingMm>0，实数有限。
init且validInit：锁存本轮origin=DistanceMm和spacing=SpacingMm，lastDistance=DistanceMm，k/issued/missed=0，err=FALSE，本轮pulse=FALSE。
init且非法：err=TRUE，计数和原点保持，pulse=FALSE。
非init时，disabled或pre.err为TRUE则计数保持、pulse=FALSE、err保持。
非init且Enable且!pre.err：若DistanceMm<pre.lastDistance或位置非法，则锁存err且计数保持；
否则newK=floor((DistanceMm-pre.origin)/pre.spacing)，d=newK-pre.k，pulse=(d>0 AND !CameraBusy)，
issued=pre.issued+int(pulse)，missed=pre.missed+d-int(pulse)，k=newK，lastDistance=DistanceMm。
每轮无论是否故障均更新prevEnable=Enable，first=FALSE。段内跨点总数<=1e9。
captureMatch表示CapturePulse/CaptureCount/MissedCount/Error分别等于上述期望。
validRun表示非init、Enable、无既有或本轮位置错误。连续两轮pulse均TRUE合法，不能额外要求脉冲之间插入FALSE。

```text
G(captureMatch)
G((init & validInit) -> (!CapturePulse & CaptureCount=0 & MissedCount=0 & !Error))
G(!Enable -> !CapturePulse)
G((validRun & d=0) -> (!CapturePulse & CaptureCount=pre.issued & MissedCount=pre.missed))
G((validRun & d>0 & !CameraBusy) -> (CapturePulse & CaptureCount=pre.issued+1 & MissedCount=pre.missed+d-1))
G((validRun & CameraBusy) -> (!CapturePulse & CaptureCount=pre.issued & MissedCount=pre.missed+d))
G((pre.err & !(init & validInit)) -> Error)
```

## CUSTOM_06 压缩空气母管压力的用气前馈调节

独立观察器积分I初始0。valid := PressureKpa∈[0,1000] AND AirUseFlow∈[0,90] AND Kp∈[0,1] AND Ki∈[0,0.1] AND DtSec∈[0.001,1]，均有限。
Reset最高优先：I=0，u=0，sat=FALSE，err=FALSE。
否则!Enable：I保持，u=0，sat=FALSE，err=FALSE。
否则!valid：I保持，u=0，sat=FALSE，err=TRUE。
合法使能：e=500-PressureKpa，FF=2*AirUseFlow，Ic=pre.I+Ki*e*DtSec，Uc=FF+Kp*e+Ic；
reject := (Uc>100 AND e>0) OR (Uc<0 AND e<0)，I=(reject?pre.I:Ic)，U=FF+Kp*e+I，u=clamp(U,0,100)，sat=(U<0 OR U>100)，err=FALSE。
pressureMatch := Integral=I AND CapacityPct=u AND Saturated=sat AND Error=err。|I|<=1e9为运行域假设；不模拟压力物理演化。
饱和判断使用最终U，不能用被拒绝积分的Uc代替。

```text
G(pressureMatch)
G(Reset -> (Integral=0 & CapacityPct=0 & !Saturated & !Error))
G((!Reset & !Enable) -> (Integral=pre.I & CapacityPct=0 & !Saturated & !Error))
G((!Reset & Enable & !valid) -> (Integral=pre.I & CapacityPct=0 & !Saturated & Error))
G((!Reset & Enable & valid & reject) -> (Integral=pre.I))
G((!Reset & Enable & valid) -> (Saturated <-> (U<0 | U>100)))
G(0<=CapacityPct & CapacityPct<=100)
```

## CUSTOM_07 矿石破碎给料与抽尘风量交叉限幅

active := Enable AND !Trip。valid表示FeedDemand、FeedActual、ExtractionCapacity三个有限LREAL均在[0,100]。
feedOK := FeedSP=min(FeedDemand,ExtractionCapacity)。extractionOK := ExtractionSP=max(FeedDemand,FeedActual)。
两个反馈必须来自实际能力，不能使用对方的设定值代替。Trip和禁用优先于参数错误。

```text
G(!active -> (FeedSP=0 & ExtractionSP=0 & !Error))
G((active & !valid) -> (FeedSP=0 & ExtractionSP=0 & Error))
G((active & valid) -> (feedOK & extractionOK & !Error))
G((active & valid) -> (FeedSP<=ExtractionCapacity & ExtractionSP>=FeedActual))
G(0<=FeedSP & FeedSP<=100 & 0<=ExtractionSP & ExtractionSP<=100)
```

## CUSTOM_08 桥式起重机双侧传动测速一致性校验

V := 0<=LeftSpeed10<=100 AND 0<=RightSpeed10<=100 AND 0<ReferenceSpeed10<=100。
R := abs(LeftSpeed10-RightSpeed10)<=1 AND abs(LeftSpeed10+RightSpeed10-13*ReferenceSpeed10)<=2，只在V真时求值。
差值、乘法采用足够宽的整数。极值输入先检查量程，不能在INT中先计算再校验。
初始调用前三个输出均FALSE；第一次调用后的输出按当前输入计算。

```text
G(SyncOK <-> (V & R))
G(SyncBad <-> (V & !R))
G(Invalid <-> !V)
G(!(SyncOK & SyncBad) & !(SyncOK & Invalid) & !(SyncBad & Invalid))
G(SyncOK | SyncBad | Invalid)
```

## CUSTOM_09 在线光谱仪维护后标定状态与测量许可控制

独立状态S初始0（等待标定），1就绪、2维护。每轮从pre.S决定且最多转换一次：
S=(Maintenance?2:(pre.S=2?0:(pre.S=0 AND CalibDone?1:pre.S)))。
Maintenance优先；退出维护的同轮即使CalibDone为TRUE仍进入0，下一轮完成电平持续TRUE则允许转入1。
stateMatch := State=S；输出映射使用本轮更新后的State。
调用前初始CalibReq=TRUE、MaintLamp=FALSE、MeasurePermit=FALSE。没有新增CalibDone上升沿要求。

```text
G(stateMatch)
G(Maintenance -> State=2)
G((!Maintenance & pre.S=2) -> State=0)
G((!Maintenance & pre.S=0 & CalibDone) -> State=1)
G((!Maintenance & pre.S=0 & !CalibDone) -> State=0)
G((!Maintenance & pre.S=1) -> State=1)
G(CalibReq <-> State=0)
G(MaintLamp <-> State=2)
G(MeasurePermit <-> (MeasureReq & State=1))
G(State=0 | State=1 | State=2)
```

## CUSTOM_10 仓库盘点请求的挂起、派发与取消控制

独立观察器preButton、pending初始FALSE。rise := RequestBtn AND !pre.preButton；request := pre.pending OR rise；canServe := ServiceReady AND !Busy。
本轮pending := !Cancel AND request AND !canServe；dispatch := !Cancel AND request AND canServe。
每轮都更新preButton=本轮RequestBtn，包括取消期间。按钮持续TRUE不形成第二个上升沿。
pendingMatch := Pending=pending。此处请求只有一位，不是FIFO；Dispatched不表示盘点完成。
活性只在最终出现取消或可服务扫描的环境条件下要求最终结束等待；不能在永久Busy的环境中要求无条件完成。
A_service := G(Pending -> F(Cancel | canServe))，为环境公平性假设，不是候选程序的输出保证。

```text
G(pendingMatch)
G(Dispatched <-> (!Cancel & request & canServe))
G(RequestLamp <-> Pending)
G(Cancel -> (!Pending & !Dispatched & !RequestLamp))
G((!Cancel & request & Busy) -> (Pending & !Dispatched))
G(!request -> (!Pending & !Dispatched))
G(!(Pending & Dispatched))
A_service -> G(Pending -> F(Cancel | Dispatched))
```

## CUSTOM_11 车辆地磅三路称重一致性投票

对AB、AC、BC分别计算：组成该对的两路都在0..20000kg且绝对差<=200kg，才是候选一致对；某一路坏值不能否决另外两路好值。
候选按(差值,次序)最小选择，次序AB<AC<BC，掩码分别3、5、6。V表示存在候选；M为选中掩码，无候选时M=0。
W为选中两路的LREAL平均，允许0.5kg；无候选时W=0。O := V AND W>10000。
voteMatch := PairMask=M AND VotedKg=W；三路为独立整车总重，不做三路相加或直接平均三路。
ReleaseReq、BarrierReady关闭仅影响许可，不影响融合。初始调用前所有输出0/FALSE；每次调用后按本轮计算。

```text
G(voteMatch)
G(LoadFault <-> !V)
G(Overload <-> O)
G(ReleasePermit <-> (V & ReleaseReq & BarrierReady & !O))
G(!V -> (PairMask=0 & VotedKg=0 & LoadFault & !Overload & !ReleasePermit))
G(V -> (PairMask=3 | PairMask=5 | PairMask=6))
G(!(LoadFault & Overload))
```

## CUSTOM_12 海洋监测浮标的辅助负载功率预算

V := 0<=BudgetW<=200；B := MandatorySensor AND BudgetW<40。
允许集合A由NeedSensor OR MandatorySensor、NeedHeater、NeedRadio分别决定比特1、2、4。
对m=0..7，p(m)=40*[m&1!=0]+70*[m&2!=0]+60*[m&4!=0]；s(m)=7*[m&1!=0]+10*[m&2!=0]+9*[m&4!=0]。
feasible(m) := (m无A以外的比特) AND p(m)<=BudgetW AND (!MandatorySensor OR m&1!=0)。
合法且非B时可行集合非空（至少空集或传感单元），M=按(-s(m),p(m),m)字典序最小的可行掩码。
disabled := !Enable；invalid := Enable AND !V；shortage := Enable AND V AND B；normal := Enable AND V AND !B。
前三种分支M=0、功率/分数0、三个负载关闭；Error仅invalid为TRUE，BudgetShortage仅shortage为TRUE。
maskMapOK表示SensorOn、HeaterOn、RadioOn与SelectedMask比特1/2/4逐一等价。
optimalChoiceOK := SelectedMask=M AND PowerW=p(M) AND Score=s(M)。有限集合定义可完整展开8个选择条件，不按单项分数或性价比贪心。

```text
G(Error <-> invalid)
G(BudgetShortage <-> shortage)
G((disabled | invalid | shortage) -> (SelectedMask=0 & PowerW=0 & Score=0 & !SensorOn & !HeaterOn & !RadioOn))
G(normal -> optimalChoiceOK)
G(maskMapOK)
G((Enable & V) -> PowerW<=BudgetW)
G((normal & MandatorySensor) -> SensorOn)
G((normal & !NeedHeater) -> !HeaterOn)
G((normal & !NeedRadio) -> !RadioOn)
```
