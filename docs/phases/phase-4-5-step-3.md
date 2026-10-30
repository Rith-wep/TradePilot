# Phase 4.5, Step 3: Workflow Separation

**Status:** Complete  
**Checkpoint:** `a57b267 refactor(workflows): separate real-data readiness`

## Result

Real-data research orchestration moved from
`tradepilot.data.readiness_pipeline` to
`tradepilot.workflows.real_data_readiness`. The old data path is a documented
compatibility shim. Callers use the workflow package while data-domain modules
no longer own indicator, strategy, or report orchestration.

Focused tests verify that the legacy and canonical import paths produce
identical evidence. CLI commands, dataset/report identities, strategy formulas,
and output behavior remain compatible.

## Main files

```text
research/src/tradepilot/workflows/real_data_readiness.py
research/src/tradepilot/data/readiness_pipeline.py
research/src/tradepilot/data/readiness_cli.py
research/tests/test_readiness_workflow_compatibility.py
```

## Verification

Compatibility and full regression gates passed before the checkpoint. The
later Phase 4.5 final verification passed the complete 234-test suite, with two
credential-gated OANDA skips.

## Limitations

The compatibility shim intentionally creates one documented data-to-workflow
import exception until that public path can be retired through a versioned
migration.

## Next step

Extract genuinely shared indicator, strategy, and candidate-report workflow
construction.

