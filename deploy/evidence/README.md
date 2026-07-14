# Deployment evidence workspace

Copy the JSON templates in this directory to the deployment host's private evidence
directory and replace every placeholder with observed, non-secret evidence. Do not commit
filled host identifiers, IP addresses, account details, tokens, or approval records.

The repository evaluators are deliberately fail-closed. Synthetic examples prove only that
the evaluator works; they cannot pass D1-D8. D3-D7 require elapsed market sessions and
operator approvals described in `docs/DEPLOYMENT_PLAN.md`.

Gate mapping:

- D0-D2 and D8: `xenalgo.deployment`
- D3 and permanent-host readiness: `xenalgo.phase32`
- D4: `xenalgo.phase33`
- D5/D6: `xenalgo.phase34` (`require_activation=False` for D5)
- D7: `xenalgo.phase35`

Filled evidence belongs under `Diary/deployment/` (gitignored), with an off-box copy that
excludes `.xenalgo-secrets/` and `.env`.
