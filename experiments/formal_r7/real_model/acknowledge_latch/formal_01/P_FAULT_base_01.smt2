; benchmark generated from python API
(set-info :status unknown)
(declare-fun P_FAULT_base_0_$valid () Bool)
(declare-fun P_FAULT_base_0_ACKRISING () Bool)
(declare-fun P_FAULT_base_0_PREVACK () Bool)
(declare-fun P_FAULT_base_0_ALARM () Bool)
(declare-fun P_FAULT_input_0_ACKNOWLEDGE () Bool)
(declare-fun P_FAULT_input_0_FAULT () Bool)
(assert
 (let (($x882 (not P_FAULT_base_0_$valid)))
 (and (= P_FAULT_base_0_ALARM false) (= P_FAULT_base_0_PREVACK false) (= P_FAULT_base_0_ACKRISING false) $x882)))
(assert
 (let (($x858 (not P_FAULT_base_0_PREVACK)))
(let (($x909 (and P_FAULT_input_0_ACKNOWLEDGE $x858)))
(let (($x874 (ite P_FAULT_input_0_FAULT true (ite $x909 false P_FAULT_base_0_ALARM))))
(let (($x910 (and (= P_FAULT_input_0_FAULT true))))
(let (($x871 (=> $x910 (and (= $x874 true)))))
(not $x871)))))))
(check-sat)
