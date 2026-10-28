; benchmark generated from python API
(set-info :status unknown)
(declare-fun P_FAULT_base_0_$valid () Bool)
(declare-fun P_FAULT_base_0_ACKRISING () Bool)
(declare-fun P_FAULT_base_0_ACKPREV () Bool)
(declare-fun P_FAULT_base_0_ALARM () Bool)
(declare-fun P_FAULT_input_0_ACKNOWLEDGE () Bool)
(declare-fun P_FAULT_input_0_FAULT () Bool)
(assert
 (let (($x849 (not P_FAULT_base_0_$valid)))
 (and (= P_FAULT_base_0_ALARM false) (= P_FAULT_base_0_ACKPREV false) (= P_FAULT_base_0_ACKRISING false) $x849)))
(assert
 (let (($x881 (not P_FAULT_base_0_ACKPREV)))
(let (($x829 (and P_FAULT_input_0_ACKNOWLEDGE $x881)))
(let (($x853 (ite P_FAULT_input_0_FAULT true (ite $x829 false P_FAULT_base_0_ALARM))))
(let (($x851 (and (= P_FAULT_input_0_FAULT true))))
(let (($x864 (=> $x851 (and (= $x853 true)))))
(not $x864)))))))
(check-sat)
