"""Predefined finite black-box checks for the twenty supplied public questions.

Written from requirements, independently of DeepSeek candidates. Sparse outputs
avoid judging unspecified details. No reference ST or candidate-derived oracle.
TIME input/output values below are milliseconds; the C++ bridge uses nanoseconds.
"""
from __future__ import annotations

import json
from pathlib import Path
import random
import re

from .config import ROOT

KNOWN = {"02": "edges", "06": "blower", "09": "moving_average", "14": "ipv4"}
BLOCKS = {"02": "EdgeDetection", "06": "BlowerControl", "09": "MovingAverage", "14": "IPv4Parser"}
UNSUPPORTED = {
    "07": "ARRAY OF STRUCT passed by VAR_IN_OUT: no validated native reference bridge in this test adapter",
    "08": "Open-bound ARRAY[*] OF STRUCT and per-array bounds: no validated native reference bridge",
    "17": "Recipe STRUCT and mutable caller-owned database: no validated native reference bridge",
    "18": "VARIANT scalar/array association and runtime type-dependent copying are not validated by this backend",
}


def questions():
    path = ROOT / "experiments/deepseek_20/questions.json"
    return json.loads(path.read_text(encoding="utf-8"))


def interface(question):
    inputs, outputs = {}, {}
    for direction, name, dtype in re.findall(r"^\| (Input|Output) \| `([^`]+)` \| `([^`]+)`", question["text"], re.M):
        target = inputs if direction == "Input" else outputs
        array = re.fullmatch(r"ARRAY\[(-?\d+)\.\.(-?\d+)\] OF (\w+)", dtype)
        if array:
            low, high, element = array.groups()
            target.update({f"{name}[{i}]": element for i in range(int(low), int(high) + 1)})
        else:
            target[name] = dtype
    return inputs, outputs


def block(question_id):
    return BLOCKS.get(question_id, "Q" + question_id)


def scenarios(question):
    ident = question["id"]
    if ident in KNOWN or ident in UNSUPPORTED:
        return []
    inputs, _ = interface(question)
    defaults = {k: 0 for k in inputs}
    cases = []
    def case(name, rows, base=None, invariants=None):
        merged = defaults | (base or {})
        trace = []
        for row in rows:
            if len(row) == 2:
                timestamp, changed = row; expected = {}
            else:
                timestamp, changed, expected = row
            trace.append({"time_ms": timestamp, "inputs": merged | changed, "expected": expected})
        cases.append({"name": name, "trace": trace, "invariants": invariants or []})
    if ident == "01":
        names = ["Pump_Motor", "Filling_Valve", "Capping_Machine", "Packing_Machine", "Completion_Light"]
        outputs = lambda active: {k: int(k == active) for k in names}
        case("full_cycle_and_waits", [(0, {}, outputs(None)), (10, {"bottleSensor": 1}),
             (20, {}, outputs("Pump_Motor")), (30, {"cleaningConfirmButton": 1}), (40, {}, outputs("Filling_Valve")),
             (50, {"fillingConfirmButton": 1}), (60, {}, outputs("Capping_Machine")),
             (70, {"cappingConfirmButton": 1}), (80, {}, outputs("Packing_Machine")),
             (90, {"packingConfirmButton": 1}), (100, {}, outputs("Completion_Light")),
             (110, {"finishedButton": 1}), (120, {}, outputs(None)), (130, {"bottleSensor": 1}),
             (140, {}, outputs("Pump_Motor"))])
        case("wrong_station_confirmations_do_not_skip", [(0, {}), (10, {"bottleSensor": 1}),
             (20, {"fillingConfirmButton": 1, "cappingConfirmButton": 1, "packingConfirmButton": 1}, outputs("Pump_Motor")),
             (30, {}, outputs("Pump_Motor"))])
    elif ident == "03":
        rows=[];high=low=False
        values=[5,11,10,9,8,7.5,-1,0,1,2,2.5,5]+[random.Random(923+i).randint(-5,15) for i in range(100)]
        for i,value in enumerate(values):
            if value>10: high=True
            elif value<8: high=False
            if value<0: low=True
            elif value>2: low=False
            rows.append((i*10,{"Value":value},{"hiAlarm":int(high),"loAlarm":int(low),"error":0,"status":0}))
        case("hysteresis_strict_boundaries",rows,{"hiLevel":10,"loLevel":0,"hystWindow":2})
        case("invalid_limits_priority",[(0,{}, {"error":1,"status":0x8001})],{"hiLevel":0,"loLevel":0,"hystWindow":10})
        case("invalid_hysteresis",[(0,{}, {"error":1,"status":0x8002})],{"hiLevel":10,"loLevel":0,"hystWindow":10})
    elif ident == "04":
        # CycleTime agrees with each actual invocation interval. Both a clock
        # timer and an input-interval accumulator see the same elapsed time.
        rows=[]
        runtime=0
        for t in range(0,361,10):
            changed={'CycleTime':0} if t==0 else {}
            if t==120:changed['PASTE_E_STOP_NC']=0
            if t==240:changed['VISCOSITY_OK']=0
            running=t in (100,110,230,350,360)
            runtime+=10 if running else 0
            rows.append((t,changed,{'VFD_RUN':int(running),'PUMP_RUNTIME_ACC':runtime,'PUMP_MAINT_DUE':0}))
        case("debounce_stop_reset_runtime",rows,
             {"VISCOSITY_OK":1,"PASTE_E_STOP_NC":1,"DebounceTime":100,"CycleTime":10})
        case('irregular_invocation_intervals',[(0,{'CycleTime':0},{'VFD_RUN':0,'PUMP_RUNTIME_ACC':0}),
             (35,{'CycleTime':35},{'VFD_RUN':0,'PUMP_RUNTIME_ACC':0}),
             (100,{'CycleTime':65},{'VFD_RUN':1,'PUMP_RUNTIME_ACC':65})],
             {'VISCOSITY_OK':1,'PASTE_E_STOP_NC':1,'DebounceTime':100,'CycleTime':0})
        # Large represented intervals test LTIME without billions of scan invocations.
        case("maintenance_is_informational",[(0,{'CycleTime':0},{'VFD_RUN':0,'PUMP_RUNTIME_ACC':0}),(1,{}, {"VFD_RUN":1,"PUMP_RUNTIME_ACC":1,"PUMP_MAINT_DUE":0}),
             (1800000001,{"CycleTime":1800000000},{"VFD_RUN":1,"PUMP_RUNTIME_ACC":1800000001,"PUMP_MAINT_DUE":1}),
             (1800000002,{"PASTE_E_STOP_NC":0},{"VFD_RUN":0,"PUMP_RUNTIME_ACC":1800000001,"PUMP_MAINT_DUE":1})],
             {"VISCOSITY_OK":1,"PASTE_E_STOP_NC":1,"DebounceTime":1,"CycleTime":1})
    elif ident == "05":
        case("startup_no_predebounce_and_estop",[(0,{}, {"Operator_Alert":0,"Weld_Soft_Start_Active":1}),
             (4999,{}, {"Operator_Alert":0,"Weld_Soft_Start_Active":1}), (5000,{}, {"Operator_Alert":0}),
             (5101,{}, {"Operator_Alert":1,"Weld_Soft_Start_Active":0}),
             (5110,{"Weld_E_Stop_NC":0},{"Operator_Alert":0}), (5120,{}, {"Operator_Alert":0}),
             (5219,{}, {"Operator_Alert":0}), (5220,{}, {"Operator_Alert":1}),
             (5230,{"Gap_Exceeded":0},{"Operator_Alert":0})], {"Gap_Exceeded":1,"Weld_E_Stop_NC":1,"DebounceTime":100})
    elif ident == "10":
        case("heating_and_cooldown",[(0,{}, {"HeaterOutput":1,"HeaterStatus":1}),
             (4999,{}, {"HeaterOutput":1}), (5001,{}, {"HeaterOutput":0,"OverheatProtection":1}),
             (7999,{}, {"HeaterOutput":0,"OverheatProtection":1}), (8010,{}, {"HeaterOutput":1,"OverheatProtection":0})],
             {"TemperatureSensorInput":20,"SetTemperature":30})
        for value in (-1,101,45):
            case(f"sensor_or_no_demand_{value}",[(0,{}, {"HeaterOutput":0,"HeaterStatus":0,"CurrentTemperature":value,"SetTempDisplay":30})],
                 {"TemperatureSensorInput":value,"SetTemperature":30})
    elif ident == "11":
        invariant=[{"not_both":["MotorForward","MotorReverse"]}]
        case("manual_interlock",[(0,{}),(10,{"ForwardButton":1},{"MotorForward":1,"MotorReverse":0}),
             (20,{"ReverseButton":1},{"MotorForward":0,"MotorReverse":1}), (30,{"ForwardButton":1,"ReverseButton":1}),
             (40,{}, {"MotorForward":0,"MotorReverse":0})], invariants=invariant)
        case("three_station_cycle",[(0,{"SensorA":1}), (10,{"SensorA":1,"ButtonA":1}), (20,{}, {"MotorForward":1}),
             (30,{"SensorB":1}), (40,{"SensorB":1},{"MotorForward":0}), (50,{"SensorB":1,"ButtonB":1}),
             (60,{}, {"MotorForward":1}), (70,{"SensorC":1}), (80,{"SensorC":1},{"MotorForward":0}),
             (90,{"SensorC":1,"ButtonC":1}), (100,{"SensorC":1},{"CompletionLight":1}),
             (110,{}), (120,{}, {"CompletionLight":0})], {"Mode":1}, invariant)
    elif ident == "12":
        # The hold is measured with CycleTime, so the trace must contain every
        # scan. Jumping from 20ms to 510ms gives the FB no elapsed time to count.
        rows=[]
        for t in range(0,521,10):
            changed={}; expected={}
            if t==0:
                expected={"THICKNESS_ALARM":0,"Slab_Fault_Counter":0,"Slab_Runtime_Accumulator":10}
            elif t==10:
                changed={"THICKNESS_FAULT":1,"FaultTimestamp":10}
                expected={"THICKNESS_ALARM":1,"Slab_Fault_Counter":1,"Slab_Fault_History[0]":10}
            elif t==20:
                changed={"THICKNESS_FAULT":0,"FaultTimestamp":0}
                expected={"THICKNESS_ALARM":1}
            elif 20<t<510:
                expected={"THICKNESS_ALARM":1}
            elif t==510:
                expected={"THICKNESS_ALARM":0}
            elif t==520:
                changed={"THICKNESS_SIGNAL_VALID":0,"THICKNESS_FAULT":1}
                expected={"THICKNESS_ALARM":0,"Slab_Fault_Counter":1}
            rows.append((t,changed,expected) if expected else (t,changed))
        case("hold_validity_and_runtime",rows,
             {"THICKNESS_SIGNAL_VALID":1,"CUTTING_RUN":1,"CycleTime":10})
        rows=[(0,{'CycleTime':0}, {"Slab_Fault_Counter":0})]
        history=[]
        for n in range(1,8):
            history=[n*100]+history[:4]
            rows.append((n*20,{"THICKNESS_FAULT":1,"FaultTimestamp":n*100,'CycleTime':20 if n==1 else 19},{"Slab_Fault_Counter":n,**{f"Slab_Fault_History[{j}]":v for j,v in enumerate(history)}}))
            rows.append((n*20+1,{}))
        case("history_retains_newest_five",rows,{"THICKNESS_SIGNAL_VALID":1,"CycleTime":1})
    elif ident == "13":
        for mode in range(4):
            for occupied in range(2):
                for saving in range(2):
                    adjustment=(4 if mode==3 else 0 if occupied else (3 if saving else 2) if mode==0 else 1 if mode==1 else 4)
                    case(f"setpoint_{mode}_{occupied}_{saving}",[(0,{}),(1,{}, {"TEMP_SETPOINT_ADJUST":adjustment})],
                         {"HVAC_MODE_SELECTOR":mode,"OCCUPANCY_DETECTED":occupied,"ENERGY_SAVING_MODE":saving})
        case("delay_and_night_reset",[(0,{}, {"SUPPLY_FAN_RUN":0}), (29999,{}, {"SUPPLY_FAN_RUN":0}),
             (30000,{}, {"SUPPLY_FAN_RUN":1}), (30001,{"HVAC_MODE_SELECTOR":3},{"SUPPLY_FAN_RUN":0}),
             (30002,{}, {"SUPPLY_FAN_RUN":0}), (60001,{}, {"SUPPLY_FAN_RUN":0}), (60002,{}, {"SUPPLY_FAN_RUN":1}),
             (60003,{"OCCUPANCY_DETECTED":0},{"SUPPLY_FAN_RUN":0})],{"OCCUPANCY_DETECTED":1})
    elif ident == "15":
        output=["valveARun","valveBRun","valveCRun","valveDRun","mixMotorRun"]
        buttons=["valveAStart","valveBStart","valveCStart","valveDStart","mixMotorStart"]
        for button,out in zip(buttons,output):
            case("manual_toggle_"+out,[(0,{}),(10,{button:1},{out:1}), (20,{button:1},{out:1}),
                 (30,{}, {out:1}), (40,{button:1},{out:0}), (50,{}), (60,{button:1},{out:1}),
                 (70,{"estop":0},{k:0 for k in output})],{"estop":1})
        case("automatic_three_materials",[(0,{}),(10,{"autoStart":1}), (20,{}, {"valveARun":1}),
             (30,{"levelSensor":50}), (40,{"levelSensor":50},{"valveARun":0,"valveBRun":1}),
             (50,{"levelSensor":80}), (60,{"levelSensor":80},{"valveBRun":0,"valveCRun":1}),
             (70,{"levelSensor":100}), (80,{"levelSensor":100},{"valveCRun":0,"mixMotorRun":1}),
             (90,{"levelSensor":100,"mixMotorComplete":1}), (100,{"levelSensor":100},{"mixMotorRun":0,"valveDRun":1}),
             (110,{"estop":0},{k:0 for k in output})],{"estop":1,"opeMode":1,"processMode":1})
    elif ident == "16":
        base={"processLength":4,**{f"processSequence[{i+1}]":v for i,v in enumerate([3,2,4,5,0,0,0,0])}}
        case("route_reverses_direction",[(0,{"sensor1":1}), (10,{"sensor1":1,"station1Start":1}),
             (20,{}, {"conveyorRight":1,"conveyorLeft":0}), (30,{"sensor3":1}), (40,{"sensor3":1},{"conveyorRight":0,"conveyorLeft":0}),
             (50,{"sensor3":1,"station3Complete":1}), (60,{}, {"conveyorLeft":1,"conveyorRight":0}),
             (70,{"sensor2":1}), (80,{"sensor2":1},{"conveyorLeft":0,"conveyorRight":0}),
             (90,{"sensor2":1,"station2Complete":1}), (100,{}, {"conveyorRight":1,"conveyorLeft":0}),
             (110,{"sensor4":1}), (120,{"sensor4":1},{"conveyorRight":0}), (130,{"sensor4":1,"station4Complete":1}),
             (140,{}, {"conveyorRight":1}), (150,{"sensor5":1}), (160,{"sensor5":1},{"conveyorRight":0,"conveyorLeft":0})],base,[{"not_both":["conveyorLeft","conveyorRight"]}])
    elif ident == "19":
        names=["Down","Up","Left","Right","Grip","Release"]
        outputs=["MoveDown","MoveUp","MoveLeft","MoveRight","ActivateGrip","ActivateRelease"]
        for action,out in zip(names,outputs):
            case("manual_limit_"+action,[(0,{}),(10,{action+"Button":1},{out:1}),
                 (20,{action+"Button":1,action+"LimitSwitch":1},{out:0}),
                 (30,{action+"Button":1},{out:1}), (40,{}, {out:0}),
                 (50,{action+"Button":1,"EmergencyStop":0},{k:0 for k in outputs})], {"ManualMode":1,"EmergencyStop":1})
        case("single_cycle_estop",[(0,{"UpLimitSwitch":1,"LeftLimitSwitch":1}),
             (10,{"Start":1,"UpLimitSwitch":1,"LeftLimitSwitch":1}), (20,{}, {"MoveDown":1}),
             (30,{"EmergencyStop":0},{k:0 for k in outputs})],{"SingleCycleMode":1,"EmergencyStop":1})
    elif ident == "20":
        from .q20_contract import scenarios as production_scenarios
        return production_scenarios()
    return cases


def protocol():
    return {"schema": "plc-bank-finite-tests-v3", "source": "Original finite checks plus Q20 response windows and invocation-consistent Q04/Q12 time traces; historical experiment protocols remain unchanged",
            "sampling": "Inputs applied at time_ms; outputs checked after invocation; fresh instance per scenario; TIME and LTIME transported in milliseconds",
            "numeric_tolerance": {"REAL_absolute_relative":1e-5,"LREAL_absolute_relative":1e-9},
            "scope": "Sparse finite examples and invariants only; not full behavioral correctness or formal proof. Generic struct/reference/VARIANT bridges excluded.",
            "questions": [{"id":q["id"],"block":block(q["id"]),"known_profile":KNOWN.get(q["id"]),
                           "unsupported_reason":UNSUPPORTED.get(q["id"]),"interface":interface(q),"scenarios":scenarios(q)} for q in questions()]}
