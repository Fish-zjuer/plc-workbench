# Agent Architecture

These three slides fit between the testing section and the results section. The narration takes about 85–95 seconds.

## Slide 1 — Agent Harness Design

Our harness separates the author from the evaluator. The self agent uses host-controlled checks and compact repair prompts. The Codex baseline edits files and calls the same checker. Both use one frozen task contract, identical expected-output rules and a shared Trial budget. Source hashes avoid repeated checks on unchanged code, and vendor calls enter a queue.

## Slide 2 — Repair Feedback and the LTL Gate

The return path contains compilation and functional-test diagnostics. Once all scenarios pass, the candidate enters the bounded LTL checker. A formal counterexample changes the outcome to formal_blocked and ends the run with a trace for review. Other formal statuses stay in the record. Trial also stops at success, the request, version or time limit, no progress, or an infrastructure failure.

## Slide 3 — Assignment Metrics and Harness Evidence

We report the metrics requested in the assignment. First and final compilation rates use all planned tasks. Scenario pass rate uses all declared scenarios. Task pass rate counts runs marked finite_pass, including their final stop conditions. Optional formal results retain the bound and property statuses. Requests, tokens and elapsed time quantify resource use. The next section presents the measured results.

## Evidence for the presentation

The feedback policy follows dataset_formal.attach and the repair loops in dataset_workflow.run and tia_workflow.run. The existing TIA verification regression checks that a functional failure reaches the next author prompt and a formal block stops further model calls.

The five design areas follow the course assignment. Task organization, context and tools appear on Slide 1. Repair and termination appear on Slide 2. Slide 3 gives the required evaluation metrics and their denominators.
