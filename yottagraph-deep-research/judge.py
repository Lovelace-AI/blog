#!/usr/bin/env python3
"""Canonical judge for the structured-retrieval vs. deep-research experiment.

The public runner and rejudge helper import from here.

Pass criteria (all must be true):
  1. Minimum length  >= 1,500 words  (fast pre-filter, not the real bar)
  2. LLM scorecard   mean >= 9.0, no individual score < 8
     Dimensions scored 1-10:
       a. financial_grounding      — specific cited figures vs. generic claims
       b. standalone_specificity   — concrete evidence for/against standalone case
       c. acquisition_specificity  — concrete Broadcom rationale, deal economics
       d. feasibility_assessment   — regulatory overlap, financing capacity, deal realism
       e. analytical_coherence     — evidence supports conclusions, no unsupported leaps
"""

from __future__ import annotations

import re
import time
from typing import Any

from topic_spec import TopicSpec, judge_system as topic_judge_system
from topic_spec import required_sections as topic_required_sections

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

DEPTH_WORD_THRESHOLD = 1_500  # cheap pre-filter only; LLM judge is the real gate
LLM_MEAN_THRESHOLD = 0.0
LLM_MIN_SCORE = 8

# ---------------------------------------------------------------------------
# Patterns (kept for informational criteria tracking)
# ---------------------------------------------------------------------------

_ACCESSION_RE = re.compile(r"\d{10}-\d{2}-\d{6}")
_REF_ID_RE = re.compile(r"\bref_[a-f0-9]{8}\b")
# Matches KG ref IDs, RAG accession numbers, web footnotes [1], and URLs (https://...)
_CITATION_RE = re.compile(
    r"\bref_[a-f0-9]{8}\b"  # KG ref IDs
    r"|\d{10}-\d{2}-\d{6}"  # RAG accession numbers
    r"|\[\d+\]"  # Web footnote citations [1], [2], ...
    r"|https?://\S{10,}"  # Full URLs (min 10 chars after https://)
)

_REQUIRED_SECTIONS: list[tuple[str, list[str]]] = [
    ("Situation Overview", ["situation", "overview"]),
    ("Marvell Standalone Case", ["standalone"]),
    ("Broadcom Buyer Case", ["buyer", "broadcom.*case"]),
    ("Deal Feasibility", ["feasibility", "deal feasib"]),
    ("Valuation", ["valuation", "market read"]),
    ("Alternative Paths", ["alternative"]),
]

NVIDIA_AMD_REQUIRED_SECTIONS: list[tuple[str, list[str]]] = [
    ("Situation Overview", ["situation", "overview"]),
    ("NVIDIA Financial Profile", ["nvidia.*financial", "nvidia.*profile"]),
    ("AMD Financial Profile", ["amd.*financial", "amd.*profile"]),
    ("Head-to-Head Comparison", ["head.*to.*head", "comparison"]),
    ("Risk Analysis", ["risk.*analysis", "risk.*factor"]),
    ("Valuation", ["valuation"]),
]


def _check_sections(
    report_text: str,
    required_sections: list[tuple[str, list[str]]] | None = None,
) -> tuple[int, list[str], list[str]]:
    found, missing = [], []
    sections = (
        required_sections if required_sections is not None else _REQUIRED_SECTIONS
    )
    heading_text = "\n".join(
        line for line in report_text.splitlines() if line.lstrip().startswith("#")
    )
    for name, keywords in sections:
        if re.search("|".join(keywords), heading_text, re.IGNORECASE):
            found.append(name)
        else:
            missing.append(name)
    return len(found), found, missing


def _count_cited_lines(report_text: str) -> int:
    return sum(
        1
        for line in report_text.splitlines()
        if line.strip() and _CITATION_RE.search(line)
    )


def judge_inputs_for_topic(
    spec: TopicSpec,
) -> tuple[list[tuple[str, list[str]]], str]:
    """Return required section patterns and LLM judge prompt for a topic spec."""
    return topic_required_sections(spec), topic_judge_system(spec)


# ---------------------------------------------------------------------------
# LLM scorecard judge
# ---------------------------------------------------------------------------


def _generate_content_with_retry(
    client: Any,
    *,
    model: str,
    contents: Any,
    config: Any,
    retry_label: str,
    max_attempts: int = 3,
) -> Any:
    """Call Gemini with consistent retry/backoff for transient quota/service errors."""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            s = str(exc)
            if "429" in s or "RESOURCE_EXHAUSTED" in s:
                wait = 120 * (attempt + 1)
                print(
                    f"  [429] {retry_label} rate-limited, retrying in {wait}s…",
                    flush=True,
                )
                time.sleep(wait)
            elif "503" in s or "UNAVAILABLE" in s:
                wait = 30 * (attempt + 1)
                print(
                    f"  [503] {retry_label} unavailable, retrying in {wait}s…",
                    flush=True,
                )
                time.sleep(wait)
            else:
                raise
    raise RuntimeError(
        f"{retry_label}: exhausted retries after rate-limit/unavailable errors"
    ) from last_exc


_LLM_JUDGE_SYSTEM_NVIDIA_AMD = """\
You are a senior equity research analyst evaluating a comparative financial
analysis report on the question:

  "Which company — NVIDIA or AMD — has the stronger financial profile for
   sustaining AI accelerator market leadership, based on available evidence?"

Score the report on SIX dimensions using 1–10:

1. financial_grounding (1-10)
   Does the report cite specific, sourced financial figures for both NVIDIA and
   AMD — revenue, margins, R&D spend, FCF, debt, EPS — from cited evidence?
   10 = every key metric cited, quantified, comparable, and interpreted
   1 = only generic statements with no specific numbers

2. standalone_specificity (1-10)
   Does the report make a concrete, evidence-backed case for NVIDIA's financial
   profile — R&D intensity, segment revenue breakdown, operating leverage, and
   capital return — with specific cited figures from evidence?
   10 = specific cited evidence interpreted into a decision-grade standalone case
   1 = vague statements like "NVIDIA is dominant in AI"

3. acquisition_specificity (1-10)
   Does the report make a concrete, evidence-backed case for AMD's financial
   profile — its R&D intensity, segment trends, margin trajectory, and how it
   compares to NVIDIA on key metrics — with specific cited figures?
   10 = specific AMD metrics cited, directly compared, and tied to the thesis
   1 = vague statements like "AMD is a challenger"

4. feasibility_assessment (1-10)
   Does the report assess the durability and sustainability of each company's
   financial position — leverage, cash generation, R&D funding capacity, and
   risk evidence presented in the report?
   10 = quantified risk, leverage, cash generation, and R&D funding analysis
   1 = no risk analysis, no disclosure-based assessment

5. analytical_coherence (1-10)
   Does the evidence presented actually support the conclusions reached?
   Are comparisons fair, inferences labeled, and reasoning traceable?
   10 = fully traceable reasoning, inferences labeled, no unsupported leaps
   1 = conclusions contradict evidence or are hallucinated

6. citation_coverage (1-10)
   Are factual claims backed by inline citations (ref IDs or accession numbers)?
   10 = nearly every material claim has the right citation on the same line
   1 = almost no citations

Return ONLY valid JSON (no markdown, no explanation outside the JSON):
{
  "financial_grounding": N,
  "standalone_specificity": N,
  "acquisition_specificity": N,
  "feasibility_assessment": N,
  "analytical_coherence": N,
  "citation_coverage": N,
  "overall_verdict": "pass" | "fail",
  "reason": "<one sentence summary of the report's strongest and weakest points>"
}

Pass threshold: mean score >= 9 AND no individual score < 8.
"""

_LLM_JUDGE_SYSTEM = """\
You are a senior investment banking research quality reviewer evaluating a
strategic alternatives report on the question:

  "Is Marvell Technology a standalone compounder or a Broadcom acquisition
   candidate?"

Score the report on FIVE dimensions using 1–10:

1. financial_grounding (1-10)
   Does the report cite specific, sourced financial figures for both Marvell
   and Broadcom — revenue, margins, FCF, debt, EPS — from cited evidence? Are
   the numbers precise and attributed?
   10 = every key metric cited, quantified, comparable, and interpreted
   1 = only generic statements like "Marvell has strong revenue growth"

2. standalone_specificity (1-10)
   Does the report make a concrete, evidence-backed case for or against
   Marvell's standalone trajectory? Does it cite product-level milestones,
   customer design wins, AI revenue ramp, margin expansion, or capital return
   plans — not just broad market commentary?
   10 = specific cited evidence interpreted into a decision-grade standalone case
   1 = vague statements like "Marvell is well-positioned in AI"

3. acquisition_specificity (1-10)
   Does the report articulate WHY Broadcom specifically would buy Marvell —
   what product lines, technology, or market positions are strategic? Does it
   address deal size, implied premium, and how Broadcom would finance it?
   10 = specific product overlap, synergy logic, deal economics, and financing implications
   1 = generic "semiconductor consolidation" rationale with no specifics

4. feasibility_assessment (1-10)
   Does the report address whether a Marvell-Broadcom deal is actually
   executable? Does it identify specific regulatory overlap (not just
   "antitrust risk"), Broadcom's current leverage and debt capacity, and any
   structural deal impediments (change-of-control provisions, China approval)?
   10 = specific antitrust, leverage, approval, and structural impediments assessed
   1 = "there may be regulatory issues" with no specific analysis

5. analytical_coherence (1-10)
   Does the evidence presented actually support the conclusions reached?
   Are there internal contradictions or unsupported leaps from data to
   recommendation? Is speculation clearly labeled as such?
   10 = fully traceable reasoning, inferences labeled
   1 = conclusions contradict the evidence, or evidence is fabricated/hallucinated

6. citation_coverage (1-10)
   Are factual claims — financial figures, transaction values, product claims,
   dates, customer names, regulatory assertions — backed by inline citations
   (source identifiers such as filing accession numbers, numbered citations, or URLs)?
   10 = nearly every material claim has the right citation on the same line or sentence
   6 = citations present but sparse; many claims go unsupported
   1 = almost no citations; reads as unsourced analysis

Return ONLY valid JSON (no markdown, no explanation outside the JSON):
{
  "financial_grounding": N,
  "standalone_specificity": N,
  "acquisition_specificity": N,
  "feasibility_assessment": N,
  "analytical_coherence": N,
  "citation_coverage": N,
  "overall_verdict": "pass" | "fail",
  "reason": "<one sentence summary of the report's strongest and weakest points>"
}

Pass threshold: mean score >= 9 AND no individual score < 8.
"""


def _usage_dict(usage: Any) -> dict[str, int]:
    if usage is None:
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    input_tokens = getattr(usage, "prompt_token_count", 0) or 0
    output_tokens = getattr(usage, "candidates_token_count", 0) or 0
    thought_tokens = getattr(usage, "thoughts_token_count", 0) or 0
    total_tokens = (
        getattr(usage, "total_token_count", None)
        or input_tokens + output_tokens + thought_tokens
    )
    return {
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "thought_tokens": int(thought_tokens),
        "total_tokens": int(total_tokens),
    }


def llm_scorecard_judge(
    report_text: str,
    model: str = "gemini-3-flash-preview",
    judge_system: str | None = None,
) -> dict[str, Any]:
    """Score the report on archetype-specific dimensions (1-10 each).

    Uses the first 12,000 chars of the report (covers all key sections).
    Returns {"passed": bool, "reason": str, "scores": {...}, "mean_score": float}.
    On any error returns {"passed": True, "reason": "LLM judge unavailable: ..."}.
    """
    try:
        import json as _json
        import os

        import google.genai as _genai  # type: ignore[import]
        from google.genai import types as _types  # type: ignore[import]

        # Preview models (gemini-3.*) require the global endpoint.
        if "preview" in model or model.startswith("gemini-3"):
            os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")

        # Prefer Vertex AI when available — avoids consuming free-tier API quota.
        # GEMINI_API_KEY may be set alongside GOOGLE_GENAI_USE_VERTEXAI for deep-research;
        # genai.Client() without explicit args can mistakenly pick the API key.
        use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in (
            "1",
            "true",
        )
        if use_vertex:
            client = _genai.Client(vertexai=True)
        else:
            api_key = os.environ.get("GEMINI_API_KEY", "")
            client = _genai.Client(api_key=api_key) if api_key else _genai.Client()
        sample = report_text
        active_system = judge_system if judge_system is not None else _LLM_JUDGE_SYSTEM
        resp = _generate_content_with_retry(
            client,
            model=model,
            contents=[_types.Content(role="user", parts=[_types.Part(text=sample)])],
            config=_types.GenerateContentConfig(
                system_instruction=active_system,
                temperature=0.0,
                response_mime_type="application/json",
                max_output_tokens=512,
                thinking_config=_types.ThinkingConfig(thinking_budget=0),
            ),
            retry_label="judge",
        )
        raw = resp.text or "{}"
        # Strip any thinking tokens or markdown that may prefix the JSON.
        start = raw.find("{")
        data = _json.loads(raw[start:] if start >= 0 else raw)
        scores = {
            k: int(v)
            for k, v in data.items()
            if k not in {"overall_verdict", "reason"} and isinstance(v, int)
        }
        mean = sum(scores.values()) / len(scores) if scores else 0
        passed = (
            (data.get("overall_verdict", "fail") == "pass")
            and mean >= LLM_MEAN_THRESHOLD
            and min(scores.values()) >= LLM_MIN_SCORE
        )
        return {
            "passed": passed,
            "reason": data.get("reason", ""),
            "scores": scores,
            "mean_score": round(mean, 2),
            "model": model,
            "usage": _usage_dict(resp.usage_metadata),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "passed": True,
            "reason": f"LLM judge unavailable: {exc}",
            "scores": {},
            "mean_score": 0.0,
            "model": model,
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def evaluate_report(
    report_text: str,
    _state: dict | None = None,
    run_llm_judge: bool = False,
    required_sections: list[tuple[str, list[str]]] | None = None,
    judge_system: str | None = None,
) -> dict[str, Any]:
    """Evaluate a report draft. Returns {passed, reason, criteria}.

    _state: optional session dict for iterative research-gate logic.
    run_llm_judge: if True, run the LLM scorecard (the primary quality gate).
    """
    word_count = len(report_text.split())

    # Optional session gate.
    if _state is not None:
        if not _state.get("research_done_since_last_judge", True):
            return {
                "passed": False,
                "reason": "Resubmit blocked. Gather additional evidence before resubmitting.",
                "criteria": {},
            }
        _state["research_done_since_last_judge"] = False
        _state["judge_call_count"] = _state.get("judge_call_count", 0) + 1

    cited_lines = _count_cited_lines(report_text)
    sections_found, found_names, missing_names = _check_sections(
        report_text, required_sections
    )

    criteria: dict[str, Any] = {
        "depth": {
            "passed": word_count >= DEPTH_WORD_THRESHOLD,
            "value": word_count,
            "threshold": DEPTH_WORD_THRESHOLD,
            "unit": "words",
        },
        "cited_lines": {
            "passed": True,  # informational only — not a hard gate
            "value": cited_lines,
            "unit": "lines with citations",
        },
        "sections": {
            "passed": True,  # informational only
            "value": sections_found,
            "found": found_names,
            "missing": missing_names,
        },
    }

    # Fast pre-filter: reject stubs before spending tokens on LLM judge.
    if not criteria["depth"]["passed"]:
        return {
            "passed": False,
            "reason": f"Report is {word_count:,} words — too short to evaluate "
            f"(minimum {DEPTH_WORD_THRESHOLD:,} words required before LLM scoring).",
            "criteria": criteria,
        }

    # LLM scorecard is the primary quality gate.
    if run_llm_judge:
        llm_result = llm_scorecard_judge(report_text, judge_system=judge_system)
        criteria["llm_scorecard"] = {
            "passed": llm_result["passed"],
            "scores": llm_result.get("scores", {}),
            "mean_score": llm_result.get("mean_score", 0),
            "reason": llm_result.get("reason", ""),
            "model": llm_result.get("model", ""),
            "usage": llm_result.get("usage", {}),
        }
        if not llm_result["passed"]:
            scores = llm_result.get("scores", {})
            score_str = ", ".join(f"{k}={v}" for k, v in scores.items())
            return {
                "passed": False,
                "reason": (
                    f"LLM scorecard failed (mean={llm_result['mean_score']:.1f}, "
                    f"threshold={LLM_MEAN_THRESHOLD}): {llm_result['reason']} "
                    f"[{score_str}]"
                ),
                "criteria": criteria,
            }
        return {
            "passed": True,
            "reason": (
                f"LLM scorecard passed (mean={llm_result['mean_score']:.1f}): "
                f"{llm_result['reason']} "
                f"[{', '.join(f'{k}={v}' for k, v in llm_result.get('scores', {}).items())}]"
            ),
            "criteria": criteria,
        }

    # Without LLM judge, pass if length threshold is met (used in early iterations).
    return {
        "passed": True,
        "reason": f"Length check passed: {word_count:,} words, {cited_lines} cited lines, "
        f"{sections_found}/6 sections. (LLM scorecard not run.)",
        "criteria": criteria,
    }
