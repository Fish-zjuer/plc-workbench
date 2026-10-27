# Assumptions

- MotorControl begins with Motor FALSE through the CODESYS default initialization of a BOOL; a start request is accepted on the first execution unless either stop input is active.
- BlowerControl begins with its BOOL and UINT outputs at zero through their CODESYS defaults. The TON instance accumulates elapsed time while demand and the normally-closed E-stop status are both TRUE; loss of either resets it.
- EdgeDetection compares the first input sample against DWORD zero, so initially high bits are reported as rising edges. Its bit count is the number of set bits in the corresponding edge mask.

- MovingAverage gives reset priority after validating windowSize. A change to windowSize clears accumulated samples so averages never mix histories with different configured widths. Invalid windowSize reports status 16#8200 and does not sample.
- IPv4Parser accepts only a nonempty ASCII dotted-decimal string of at most 15 characters; leading zeroes within an octet are accepted because the prompt does not prohibit them.
