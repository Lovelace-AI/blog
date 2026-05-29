#!/usr/bin/env python3
"""Re-run the LLM judge over saved public report artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from judge import evaluate_report, judge_inputs_for_topic
from topic_spec import list_topic_slugs, load_topic_spec

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_REPORT_ROOT = SCRIPT_DIR / "reports"

DATASOURCE_DIRS = {
    "deep-research": "deep-research",
    "structured-retrieval": "yg-3-1-flash-lite",
    "no-context": "no-context",
}


def _usage_path(report_root: Path, datasource: str, slug: str) -> Path:
    return report_root / "usage" / DATASOURCE_DIRS[datasource] / f"{slug}.usage.json"


def rejudge_report(slug: str, datasource: str, report_root: Path) -> dict:
    report_path = report_root / DATASOURCE_DIRS[datasource] / f"{slug}.md"
    usage_path = _usage_path(report_root, datasource, slug)
    if not report_path.exists():
        return {"topic": slug, "datasource": datasource, "missing": str(report_path)}

    spec = load_topic_spec(slug)
    judge_sections, judge_system = judge_inputs_for_topic(spec)
    verdict = evaluate_report(
        report_path.read_text(encoding="utf-8"),
        run_llm_judge=True,
        required_sections=judge_sections,
        judge_system=judge_system,
    )

    usage = {}
    if usage_path.exists():
        usage = json.loads(usage_path.read_text(encoding="utf-8"))
    usage["passed"] = bool(verdict.get("passed", False))
    usage["verdict"] = verdict
    usage["rejudged_with_modified_judge"] = True
    usage["judge_scale"] = "1-10"
    usage["rejudge_model"] = (
        (verdict.get("criteria") or {}).get("llm_scorecard") or {}
    ).get("model", "")
    usage_path.write_text(json.dumps(usage, indent=2) + "\n", encoding="utf-8")

    llm = (verdict.get("criteria") or {}).get("llm_scorecard") or {}
    return {
        "topic": slug,
        "datasource": datasource,
        "passed": verdict.get("passed"),
        "mean_score": llm.get("mean_score", 0),
        "scores": llm.get("scores", {}),
        "usage_path": str(usage_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--datasource",
        choices=["deep-research", "structured-retrieval", "no-context", "all"],
        default="all",
        help="Which saved report set to rejudge.",
    )
    parser.add_argument(
        "--topic",
        action="append",
        choices=list_topic_slugs(),
        help="Topic slug to rejudge. Can be passed multiple times; defaults to all.",
    )
    parser.add_argument(
        "--report-root",
        type=Path,
        default=DEFAULT_REPORT_ROOT,
        help="Root containing committed report artifact directories.",
    )
    args = parser.parse_args()

    datasources = (
        list(DATASOURCE_DIRS) if args.datasource == "all" else [args.datasource]
    )
    topics = args.topic or list_topic_slugs()
    for datasource in datasources:
        for slug in topics:
            result = rejudge_report(slug, datasource, args.report_root)
            if "missing" in result:
                print(
                    f"[skip] {datasource}/{slug}: missing {result['missing']}",
                    flush=True,
                )
                continue
            scores = result.get("scores") or {}
            score_str = ", ".join(f"{key}={value}" for key, value in scores.items())
            print(
                f"[judge] {datasource}/{slug}: "
                f"passed={result['passed']} mean={result['mean_score']} {score_str}",
                flush=True,
            )


if __name__ == "__main__":
    main()
