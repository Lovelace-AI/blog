#!/usr/bin/env python3
"""Public benchmark harness for the blog supplement.

This file intentionally omits the private retrieval adapter used for the
structured-evidence reports. It preserves the public experiment shape:

1. optional retrieval planning over broad evidence categories,
2. evidence curation into a sectioned dossier,
3. report synthesis from that dossier,
4. LLM judging with a fixed rubric,
5. a no-context baseline.

The committed reports and usage files are the reproducible artifacts for the
blog post. To plug in a public or internal retrieval backend, implement the
`RetrievalAdapter` protocol below and pass a prepared evidence dossier to
`run_structured_report`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Protocol

SCRIPT_DIR = Path(__file__).resolve().parent
REPORTS_DIR = SCRIPT_DIR / "reports"
NO_CONTEXT_MODEL = "gemini-3-flash-preview"
DEFAULT_SYNTHESIS_MODEL = "gemini-3.1-flash-lite-preview"
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_NUM_CTX = 131072

sys.path.insert(0, str(SCRIPT_DIR))
from judge import evaluate_report, judge_inputs_for_topic  # noqa: E402
from topic_spec import (  # noqa: E402
    list_topic_slugs,
    load_topic_spec,
    outline_text as build_topic_outline,
    prompt_text as build_topic_prompt,
    report_instructions as build_report_instructions,
)


class RetrievalAdapter(Protocol):
    """Public shape for a retrieval backend used by the structured track."""

    def plan(self, topic: str, outline: str) -> list[dict[str, Any]]:
        """Return backend-specific calls after injecting private tool declarations."""

    def retrieve(self, plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return evidence records with text and optional citation/source fields."""


PLANNER_PROMPT_TEMPLATE = """\
You are planning evidence retrieval for an investment research report.

Topic:
{topic}

Required outline:
{outline}

Available retrieval tools:
{tool_declarations}

Use the tool declarations above to produce a high-recall retrieval plan. Do not
write the report. Return only JSON in the private call format expected by the
retrieval adapter.
"""

PUBLIC_TOOL_DECLARATION_PLACEHOLDER = """\
<private tool declarations injected here>

Each declaration normally includes:
- tool name
- short docstring
- argument schema
- constraints on when to use the tool
- citation/provenance guarantees for returned evidence
"""


def build_planner_prompt(topic: str, outline: str, tool_declarations: str) -> str:
    """Build the planner prompt after private tool declarations are injected."""
    return PLANNER_PROMPT_TEMPLATE.format(
        topic=topic,
        outline=outline,
        tool_declarations=tool_declarations,
    )


def run_planner_stub(topic: str, outline: str, adapter: RetrievalAdapter) -> list[dict[str, Any]]:
    """Show where the planner LLM call happens in the private pipeline.

    The public supplement intentionally does not include the real tool
    declarations or call schema. In the private pipeline, this function:

    1. renders `build_planner_prompt(...)` with backend-specific tool docs,
    2. sends that prompt to the planner LLM,
    3. parses the returned JSON call list,
    4. passes those calls to `adapter.retrieve(...)`.
    """
    prompt = build_planner_prompt(
        topic,
        outline,
        PUBLIC_TOOL_DECLARATION_PLACEHOLDER,
    )
    del prompt  # Public stub only; private code sends this to the planner LLM.
    return adapter.plan(topic, outline)


def run_retrieval_stub(plan: list[dict[str, Any]], adapter: RetrievalAdapter) -> list[dict[str, Any]]:
    """Show where planned tool calls are executed by the retrieval adapter."""
    return adapter.retrieve(plan)


CURATOR_PROMPT = """\
Create a concise evidence dossier organized by the required report headings.

Rules:
- Use each required heading exactly once.
- Select only evidence records that directly support that section.
- Prefer source-backed facts over unsupported background.
- Preserve citation labels supplied with each evidence record.
- Do not write the final report.
"""


SYNTHESIS_SYSTEM = """\
You are a senior investment banking analyst. Write a comprehensive strategic
alternatives report using ONLY the evidence provided. Every material claim must
be cited with numbered citations from the evidence block, e.g. "Revenue was
$8.2B [12]". Include a final "Bibliography" section that preserves the
numbered source mappings from the evidence. Do not use prior knowledge. Label
unsupported claims [DATA GAP].
"""


REPORT_STYLE_GUIDE = """\
STYLE GUIDE:
- Write in polished investment-memo prose. Use bullets sparingly for discrete
  takeaways, not as the default shape for analysis.
- Prefer compact Markdown tables for repeated numeric series, quarterly/annual
  financials, peer comparisons, stock snapshots, and other structured evidence.
  Follow each table with prose that explains the trend, inflection points, and
  relevance to the thesis.
- Do not list one sentence per quarter/year when a table would communicate the
  evidence more clearly.
- Keep tables focused: include the period, metric, value, and citation; avoid
  oversized tables that crowd out interpretation.
- Every table must be introduced by a short prose setup and followed by
  analytical prose. Do not let tables replace judgment.
- The conclusion / Investment View should not end with a list of data gaps.
  Lead with the supported thesis, the evidence that drives it, and the practical
  implication for the investor. Mention at most 1-2 decision-critical data gaps
  after the thesis, and only if they materially change confidence.
"""


SYNTHESIS_BODY = """\
{prompt}

Attached topic outline:
```markdown
{outline}
```

---
EVIDENCE ({n_items} items from {n_sources} distinct sources):

{evidence}

---
{instructions}
{style_guide}
LENGTH: Minimum {min_words} words. This is a hard floor, not a target.
STRUCTURE: Use every required heading, and write a fully developed section under each heading.
DEPTH: Include enough cited bullets/tables that the report reads like a complete investment memo, not a summary.
CITATIONS: Use numbered citations like [1], [2], etc. from the evidence when
available. Do not cite remaining fNNNN markers; those are uncited context facts.
Include the Bibliography section from the evidence.
"""


def model_slug(model: str) -> str:
    """Return a filesystem-safe short model slug for output artifacts."""
    return (
        model.replace("gemini-", "")
        .replace("-preview", "")
        .replace(".", "-")
        .replace("/", "-")
    )


def usage_dict(usage: Any) -> dict[str, int]:
    """Return a stable token usage dict from google-genai usage metadata."""
    if usage is None:
        return {"input_tokens": 0, "output_tokens": 0, "thought_tokens": 0, "total_tokens": 0}
    input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
    output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
    thought_tokens = int(getattr(usage, "thoughts_token_count", 0) or 0)
    total_tokens = int(getattr(usage, "total_token_count", 0) or 0)
    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens + thought_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "thought_tokens": thought_tokens,
        "total_tokens": total_tokens,
    }


def is_ollama_model(model: str) -> bool:
    """Treat colon-delimited or non-Gemini model names as local Ollama models."""
    return ":" in model or not model.startswith("gemini")


class OllamaUsage:
    """Minimal usage object compatible with usage_dict()."""

    def __init__(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_token_count = prompt_tokens
        self.candidates_token_count = completion_tokens
        self.thoughts_token_count = 0
        self.total_token_count = prompt_tokens + completion_tokens


def ollama_chat_url() -> str:
    """Return the native Ollama chat endpoint for OLLAMA_BASE_URL."""
    parsed = urllib.parse.urlsplit(OLLAMA_BASE_URL)
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, f"{path}/api/chat", parsed.query, parsed.fragment)
    )


def generate_ollama_content(
    *,
    model: str,
    system_instruction: str,
    prompt: str,
    temperature: float,
    max_output_tokens: int,
) -> tuple[str, dict[str, int]]:
    """Call a local Ollama /api/chat server and return text plus token usage."""
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "num_ctx": OLLAMA_NUM_CTX,
            "num_predict": max_output_tokens,
            "temperature": temperature,
        },
    }
    request = urllib.request.Request(
        ollama_chat_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=1800) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama chat failed with HTTP {exc.code}: {body}") from exc

    text = ((data.get("message") or {}).get("content") or "")
    usage = OllamaUsage(
        prompt_tokens=int(data.get("prompt_eval_count") or 0),
        completion_tokens=int(data.get("eval_count") or 0),
    )
    return text, usage_dict(usage)


def build_genai_client() -> Any:
    """Build a Gemini client from the caller's configured environment."""
    import google.genai as genai  # type: ignore[import]

    use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true")
    if use_vertex:
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
        return genai.Client(vertexai=True)
    api_key = os.environ.get("GEMINI_API_KEY", "")
    return genai.Client(api_key=api_key) if api_key else genai.Client()


def generate_content(
    *,
    model: str,
    system_instruction: str,
    prompt: str,
    temperature: float = 0.3,
    max_output_tokens: int = 32768,
    thinking_level: str | None = None,
) -> tuple[str, dict[str, int], float]:
    """Call Gemini or local Ollama once and return text, usage, and elapsed seconds."""
    if is_ollama_model(model):
        start = time.monotonic()
        text, usage = generate_ollama_content(
            model=model,
            system_instruction=system_instruction,
            prompt=prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        return text, usage, round(time.monotonic() - start, 1)

    from google.genai import types  # type: ignore[import]

    client = build_genai_client()
    thinking_config = None
    if thinking_level:
        thinking_config = types.ThinkingConfig(
            thinking_level=getattr(types.ThinkingLevel, thinking_level.upper())
        )
    start = time.monotonic()
    response = client.models.generate_content(
        model=model,
        contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            thinking_config=thinking_config,
        ),
    )
    return response.text or "", usage_dict(response.usage_metadata), round(time.monotonic() - start, 1)


def judge_report(topic_slug: str, report: str) -> dict[str, Any]:
    """Run the fixed benchmark judge for one report."""
    spec = load_topic_spec(topic_slug)
    sections, judge_system = judge_inputs_for_topic(spec)
    return evaluate_report(
        report,
        run_llm_judge=True,
        required_sections=sections,
        judge_system=judge_system,
    )


def output_dir(topic_slug: str) -> Path:
    """Return the local artifact output directory for one topic."""
    path = SCRIPT_DIR / "tmp" / topic_slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def topic_prompt(topic_slug: str) -> tuple[str, str, str]:
    """Return prompt, outline, and report instructions for one topic."""
    spec = load_topic_spec(topic_slug)
    return build_topic_prompt(spec), build_topic_outline(spec), build_report_instructions(spec)


def no_context_prompt(topic_slug: str, min_words: int) -> str:
    """Prompt for the no-context baseline."""
    prompt, outline, instructions = topic_prompt(topic_slug)
    return f"""\
{prompt}

Attached topic outline:
```markdown
{outline}
```

{instructions}

No additional context, retrieval output, or source evidence has been provided.
Do not use tools. Write the best report you can from the model's own knowledge
only. If a factual claim is not supported by a provided source, mark it
[UNCITED].

LENGTH: Minimum {min_words} words. This is a hard floor, not a target.
"""


def structured_report_prompt(
    topic_slug: str,
    evidence_dossier: str,
    min_words: int,
    n_items: int | None = None,
    n_sources: int | None = None,
) -> str:
    """Prompt for report synthesis from a prepared evidence dossier."""
    prompt, outline, instructions = topic_prompt(topic_slug)
    return SYNTHESIS_BODY.format(
        prompt=prompt,
        outline=outline,
        evidence=evidence_dossier,
        n_items=n_items if n_items is not None else evidence_dossier.count("\n- ["),
        n_sources=n_sources if n_sources is not None else 0,
        instructions=instructions,
        style_guide=REPORT_STYLE_GUIDE,
        min_words=min_words,
    )


def run_no_context(topic_slug: str, model: str, min_words: int) -> None:
    """Generate and judge a no-context report."""
    prompt = no_context_prompt(topic_slug, min_words)
    report, usage, elapsed = generate_content(
        model=model,
        system_instruction=(
            "You are a senior investment banking analyst. No external context "
            "or tools are available for this run."
        ),
        prompt=prompt,
    )
    verdict = judge_report(topic_slug, report)
    out_dir = output_dir(topic_slug)
    prefix = f"GEMINI_{model_slug(model).upper().replace('-', '_')}_NOCONTEXT"
    write_artifacts(
        out_dir=out_dir,
        prefix=prefix,
        datasource="no-context",
        model=model,
        report=report,
        usage=usage,
        elapsed=elapsed,
        verdict=verdict,
    )


def run_structured_report(
    topic_slug: str,
    evidence_file: Path,
    model: str,
    min_words: int,
    n_items: int | None,
    n_sources: int | None,
) -> None:
    """Generate and judge a report from a prepared, public evidence dossier."""
    # In the private pipeline, this evidence file is produced before synthesis by:
    #
    #   1. rendering PLANNER_PROMPT_TEMPLATE with backend-specific tool declarations,
    #   2. sending that prompt to the planner LLM,
    #   3. executing the returned private call list through the retrieval adapter,
    #   4. passing the retrieved evidence records to the curator LLM with CURATOR_PROMPT,
    #   5. writing the curator's sectioned dossier to disk.
    #
    # The public supplement omits the private tool declarations, call schema, and
    # retrieval adapter. Supplying --evidence-file starts from the dossier boundary.
    evidence_dossier = evidence_file.read_text(encoding="utf-8")
    prompt = structured_report_prompt(topic_slug, evidence_dossier, min_words, n_items, n_sources)
    report, usage, elapsed = generate_content(
        model=model,
        system_instruction=SYNTHESIS_SYSTEM,
        prompt=prompt,
        thinking_level="low",
    )
    verdict = judge_report(topic_slug, report)
    out_dir = output_dir(topic_slug)
    prefix = f"STRUCTURED_{model_slug(model).upper().replace('-', '_')}"
    write_artifacts(
        out_dir=out_dir,
        prefix=prefix,
        datasource="structured-evidence",
        model=model,
        report=report,
        usage=usage,
        elapsed=elapsed,
        verdict=verdict,
    )


def rejudge_saved_report(topic_slug: str, report_path: Path) -> None:
    """Run the judge over an existing report artifact."""
    report = report_path.read_text(encoding="utf-8")
    verdict = judge_report(topic_slug, report)
    print(json.dumps(verdict, indent=2))


def write_artifacts(
    *,
    out_dir: Path,
    prefix: str,
    datasource: str,
    model: str,
    report: str,
    usage: dict[str, int],
    elapsed: float,
    verdict: dict[str, Any],
) -> None:
    """Write report and usage artifacts."""
    report_path = out_dir / f"{prefix}_REPORT.md"
    usage_path = out_dir / f"{prefix}_REPORT.usage.json"
    report_path.write_text(report + "\n", encoding="utf-8")
    usage_path.write_text(
        json.dumps(
            {
                "datasource": datasource,
                "model": model,
                "passed": bool(verdict.get("passed")),
                "report_words": len(report.split()),
                "elapsed_s": elapsed,
                "usage": usage,
                "verdict": verdict,
            },
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    score = ((verdict.get("criteria") or {}).get("llm_scorecard") or {}).get("mean_score", 0)
    print(f"Report: {report_path}")
    print(f"Usage:  {usage_path}")
    print(f"Passed: {bool(verdict.get('passed'))} | mean score: {score}")


def main() -> None:
    global OLLAMA_BASE_URL, OLLAMA_NUM_CTX

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["no-context", "structured-report", "rejudge"],
        required=True,
    )
    parser.add_argument(
        "--topic",
        choices=list_topic_slugs() + ["all"],
        default="marvell-broadcom",
    )
    parser.add_argument("--model", default=NO_CONTEXT_MODEL)
    parser.add_argument("--min-words", type=int, default=4000)
    parser.add_argument("--n-items", type=int)
    parser.add_argument("--n-sources", type=int)
    parser.add_argument("--evidence-file", type=Path)
    parser.add_argument("--report-file", type=Path)
    parser.add_argument(
        "--ollama-url",
        default=OLLAMA_BASE_URL,
        help=f"Base URL for local Ollama models (default: {OLLAMA_BASE_URL}).",
    )
    parser.add_argument(
        "--ollama-num-ctx",
        type=int,
        default=OLLAMA_NUM_CTX,
        help=f"Context window requested for local Ollama models (default: {OLLAMA_NUM_CTX}).",
    )
    args = parser.parse_args()

    OLLAMA_BASE_URL = args.ollama_url
    OLLAMA_NUM_CTX = args.ollama_num_ctx

    topics = list_topic_slugs() if args.topic == "all" else [args.topic]
    for topic_slug in topics:
        if args.mode == "no-context":
            run_no_context(topic_slug, args.model, args.min_words)
        elif args.mode == "structured-report":
            if not args.evidence_file:
                raise SystemExit("--evidence-file is required for --mode structured-report")
            run_structured_report(
                topic_slug,
                args.evidence_file,
                args.model,
                args.min_words,
                args.n_items,
                args.n_sources,
            )
        elif args.mode == "rejudge":
            if not args.report_file:
                raise SystemExit("--report-file is required for --mode rejudge")
            rejudge_saved_report(topic_slug, args.report_file)


if __name__ == "__main__":
    main()
