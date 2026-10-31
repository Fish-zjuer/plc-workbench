# Web experiment update (2026-10-31)

The web runner now supports per-model inference controls (DeepSeek thinking toggle/effort, Qwen toggle/budget, explicit custom JSON), shared between self and Codex and saved in the campaign snapshot. Recognized DeepSeek/Qwen models initially select nonthinking in the UI. Unsupported controls produce validation errors rather than silently selecting another model.

Local validation requires the verified PLC-R4 backend. Run `python -m plc_agent.backend_r4 activate` after building it as described in README.md. CODESYS vendor compilation remains separate and real; PUBLIC_18 VARIANT/PV compatibility is still not resolved for the vendor template.

Imported struct scenarios now load their caller-provided initial data even after task IDs are namespaced. Custom floating point tolerances remain identical before/after import. No expected test data changes.

Transient model failures have at most three actual requests, all counted toward the 24-request budget. Returned usage is retained even on rejected/truncated responses. The UI shows known token amounts and missing-call counts instead of hiding the entire sum. Unknown usage is never reported as zero.

CODESYS execution timeouts retain stdout, stderr and last worker stage; only execution timeout is retried once in a fresh directory using identical source/config. Compiler rejection is not retried. Both outcomes are retained. Six source versions and 1800 seconds per task remain unchanged.

A fresh self-only validation can use a frozen task snapshot from the local campaign directory:

```powershell
python -m experiments.self_transport_validation --tasks-file agent_data/campaigns/<campaign-id>/tasks.json --output reports/new-validation --workers 4 --timeout 600 --deepseek-nonthinking
```

Both models start from empty output. No selected historical candidates or successful retries are substituted into a fresh score. Configuration and backend fingerprints are saved. Existing incomplete trials are rejected on continuation to prevent budget reset.

Local credentials, CODESYS paths/templates, imported banks and generated experiment evidence are not part of this code update. Current experiments must finish before restarting the web server to load new backend code.
