"""Command-line validator for private D0-D2/D8 JSON evidence."""
from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

from .deployment import (
    HostReadinessEvidence, OperationsHandoffEvidence, PaperDeploymentEvidence,
    ReleaseEvidence, evaluate_d0, evaluate_d1, evaluate_d2, evaluate_d8,
)

GATES = {
    "D0": (ReleaseEvidence, evaluate_d0),
    "D1": (HostReadinessEvidence, evaluate_d1),
    "D2": (PaperDeploymentEvidence, evaluate_d2),
    "D8": (OperationsHandoffEvidence, evaluate_d8),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate XenAlgo deployment evidence without side effects.")
    parser.add_argument("gate", choices=GATES)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    evidence_type, evaluator = GATES[args.gate]
    payload = json.loads(args.evidence.read_text(encoding="utf-8"))
    report = evaluator(evidence_type(**payload))
    print(json.dumps(dataclasses.asdict(report) | {"passed": report.passed}, indent=2))
    raise SystemExit(0 if report.passed else 2)


if __name__ == "__main__":
    main()
