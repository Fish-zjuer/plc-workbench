# Independent adversarial review

Reviewed only the supplied packet and the five candidate listings it contains. No compiler or existing outcome material was consulted.

## Finding

`ADV-001` is an **ambiguous-specification probe** for `moving_average`: a rising trigger edge during reset is acknowledged by the edge detector, while reset suppresses sampling. If trigger stays high after reset ends, no sample is taken. The packet requires trigger-edge sampling and reset behavior but does not define their precedence. The trace and expected outputs in `proposals.json` make this interaction directly testable; it should not be treated as a confirmed defect without deciding the intended precedence.

I found no other counterexample that could be stated as a violation of an explicit requirement from the supplied packet. In particular, the packet does not define first-scan edge history for `edges`, so its initial output must not be asserted as an error. I also did not infer extra IPv4 formatting restrictions such as rejecting leading zeroes, which the stated requirements do not impose.
