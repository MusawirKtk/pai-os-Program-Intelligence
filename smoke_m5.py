"""Evaluate a local JSON fixture without network, Vault, or database writes."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from pai_program_intelligence.eligibility import evaluate_eligibility  # noqa: E402
from pai_program_intelligence.schemas import (  # noqa: E402
    ApplicantScope,
    Requirement,
    RequirementType,
    VerificationStatus,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=REPO_ROOT / "examples" / "m5_demo.json",
        help="Local JSON with program_id, public requirements, and task-scoped context",
    )
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    requirements = tuple(
        Requirement(
            requirement_id=item["requirement_id"],
            type=RequirementType(item["type"]),
            raw_text=item["raw_text"],
            required=item["required"],
            verification_status=VerificationStatus(item["verification_status"]),
            source_id=item["source_id"],
            applies_to=ApplicantScope(**item.get("applies_to", {})),
            normalized=item.get("normalized", {}),
        )
        for item in payload["requirements"]
    )
    result = evaluate_eligibility(payload["program_id"], requirements, payload["context"])
    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
