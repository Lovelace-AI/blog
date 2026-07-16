"""Topic specs and report archetypes for deep-research experiments."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import]
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal envs
    yaml = None


SCRIPT_DIR = Path(__file__).resolve().parent
TOPICS_DIR = SCRIPT_DIR / "topics"

@dataclass(frozen=True)
class Archetype:
    name: str
    report_kind: str
    sections: list[str]
    dimensions: list[tuple[str, str]]


ARCHETYPES: dict[str, Archetype] = {
    "strategic_alternatives": Archetype(
        name="strategic_alternatives",
        report_kind="investment banking strategic alternatives report",
        sections=[
            "Situation Overview",
            "Target Standalone Case",
            "Strategic Buyer Case",
            "Deal Feasibility",
            "Valuation",
            "Alternative Paths",
        ],
        dimensions=[
            ("financial_grounding", "specific cited financial figures from evidence"),
            (
                "target_specificity",
                "concrete evidence for the target's standalone case",
            ),
            ("buyer_logic", "evidence-backed strategic buyer rationale"),
            ("deal_feasibility", "regulatory, financing, and execution realism"),
            ("analytical_coherence", "conclusions follow from evidence"),
            ("citation_coverage", "material claims have inline citations"),
        ],
    ),
    "competitive_financial_profile": Archetype(
        name="competitive_financial_profile",
        report_kind="comparative equity research report",
        sections=[
            "Situation Overview",
            "Company A Financial Profile",
            "Company B Financial Profile",
            "Head-to-Head Comparison",
            "Risk Analysis",
            "Valuation",
        ],
        dimensions=[
            (
                "financial_grounding",
                "specific cited financial figures for both companies",
            ),
            ("company_a_specificity", "concrete evidence for company A"),
            ("company_b_specificity", "concrete evidence for company B"),
            ("risk_assessment", "evidence-backed risk and durability analysis"),
            (
                "analytical_coherence",
                "comparisons and conclusions follow from evidence",
            ),
            ("citation_coverage", "material claims have inline citations"),
        ],
    ),
    "single_company_investment_memo": Archetype(
        name="single_company_investment_memo",
        report_kind="single-company investment memo",
        sections=[
            "Situation Overview",
            "Business Model And Segments",
            "Financial Profile",
            "Growth Drivers",
            "Risk Factors",
            "Investment View",
        ],
        dimensions=[
            ("financial_grounding", "specific cited financial figures from evidence"),
            (
                "business_specificity",
                "specific evidence for business model and segments",
            ),
            (
                "growth_specificity",
                "evidence-backed growth drivers and operating signals",
            ),
            ("risk_assessment", "specific evidence-backed risks tied to the thesis"),
            ("analytical_coherence", "investment view follows from evidence"),
            ("citation_coverage", "material claims have inline citations"),
        ],
    ),
    "commodity_supply_chain_outlook": Archetype(
        name="commodity_supply_chain_outlook",
        report_kind="commodity supply chain and price outlook report",
        sections=[
            "Market Overview",
            "Supply Landscape",
            "Demand Landscape",
            "Key Producers And Market Participants",
            "Geopolitical And Macro Risk",
            "Price Outlook",
        ],
        dimensions=[
            (
                "supply_demand_grounding",
                "specific cited supply and demand data, production volumes, and inventory levels",
            ),
            (
                "producer_specificity",
                "concrete cited evidence about key producers, their capacity, and recent actions",
            ),
            (
                "risk_assessment",
                "evidence-backed geopolitical, regulatory, and macro risks with specific named actors",
            ),
            (
                "market_dynamics",
                "cited evidence for price drivers, market structure, and historical price context",
            ),
            (
                "analytical_coherence",
                "price outlook follows logically from the supply/demand/risk evidence",
            ),
            ("citation_coverage", "material claims have inline citations"),
        ],
    ),
}


@dataclass(frozen=True)
class SeedEntity:
    """A topic seed entity.

    ``flavors`` optionally narrows entity resolution (e.g. ``industry`` or
    ``commodity`` versus the default ``organization``). String-only YAML seeds
    remain valid and default to organization.
    """

    name: str
    flavors: tuple[str, ...] = ("organization",)


@dataclass(frozen=True)
class TopicSpec:
    slug: str
    archetype: str
    question: str
    seed_entities: list[SeedEntity]
    roles: dict[str, str] = field(default_factory=dict)
    market_theme: str = ""

    @property
    def archetype_config(self) -> Archetype:
        return ARCHETYPES[self.archetype]

    @property
    def seed_names(self) -> list[str]:
        return [seed.name for seed in self.seed_entities]


def _normalize_seed_entities(raw_seeds: Any) -> list[SeedEntity]:
    """Accept string seeds or ``{name, flavors}`` mappings from topic YAML."""
    if not isinstance(raw_seeds, list) or not raw_seeds:
        raise ValueError("seed_entities must be a non-empty list")
    seeds: list[SeedEntity] = []
    for item in raw_seeds:
        if isinstance(item, str):
            name = item.strip()
            if not name:
                raise ValueError("seed_entities entries must be non-empty strings")
            seeds.append(SeedEntity(name=name))
            continue
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if not name:
                raise ValueError(f"seed mapping missing name: {item!r}")
            flavors_raw = item.get("flavors")
            if flavors_raw is None and item.get("flavor") is not None:
                flavors_raw = [item.get("flavor")]
            if flavors_raw is None:
                flavors = ("organization",)
            elif isinstance(flavors_raw, str):
                text = flavors_raw.strip()
                if text.startswith("[") and text.endswith("]"):
                    inner = text[1:-1].strip()
                    flavors = tuple(
                        part.strip().strip("'\"")
                        for part in inner.split(",")
                        if part.strip()
                    )
                else:
                    flavors = (text,)
            elif isinstance(flavors_raw, list) and flavors_raw:
                flavors = tuple(str(f).strip() for f in flavors_raw if str(f).strip())
            else:
                raise ValueError(f"invalid flavors for seed {name!r}: {flavors_raw!r}")
            if not flavors:
                raise ValueError(f"seed {name!r} has empty flavors")
            seeds.append(SeedEntity(name=name, flavors=flavors))
            continue
        raise ValueError(f"unsupported seed_entities entry: {item!r}")
    return seeds


def load_topic_spec(slug: str, topics_dir: Path = TOPICS_DIR) -> TopicSpec:
    path = topics_dir / f"{slug}.yaml"
    if not path.exists():
        available = ", ".join(list_topic_slugs(topics_dir))
        raise FileNotFoundError(f"topic not found: {slug!r}; available: {available}")
    raw = _load_yaml_mapping(path)
    if raw["archetype"] not in ARCHETYPES:
        raise ValueError(f"unknown archetype {raw['archetype']!r} in {path}")
    return TopicSpec(
        slug=raw["slug"],
        archetype=raw["archetype"],
        question=raw["question"],
        roles=raw.get("roles", {}) or {},
        market_theme=raw.get("market_theme", "") or "",
        seed_entities=_normalize_seed_entities(raw["seed_entities"]),
    )


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    """Load a topic YAML file without requiring PyYAML in minimal envs."""
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text)

    data: dict[str, Any] = {}
    current_key: str | None = None
    current_list_item: dict[str, Any] | None = None
    current_list_subkey: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" ") and ":" in line:
            if (
                current_key is not None
                and current_list_item is not None
                and isinstance(data.get(current_key), list)
            ):
                data[current_key].append(current_list_item)
                current_list_item = None
                current_list_subkey = None
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            current_key = key
            if value:
                data[key] = _unquote(value)
            else:
                data[key] = [] if key == "seed_entities" else {}
            continue
        if current_key is None:
            continue
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))
        if stripped.startswith("- "):
            if (
                current_list_item is not None
                and isinstance(data.get(current_key), list)
            ):
                data[current_key].append(current_list_item)
                current_list_item = None
                current_list_subkey = None
            if not isinstance(data[current_key], list):
                data[current_key] = []
            item_body = stripped[2:].strip()
            if ":" in item_body and not item_body.startswith(("http://", "https://")):
                ikey, ivalue = item_body.split(":", 1)
                current_list_item = {ikey.strip(): _unquote(ivalue.strip())}
                current_list_subkey = None
            else:
                data[current_key].append(_unquote(item_body))
                current_list_item = None
                current_list_subkey = None
            continue
        if current_list_item is not None and ":" in stripped and indent >= 4:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value:
                current_list_item[key] = _unquote(value)
                current_list_subkey = None
            else:
                current_list_item[key] = []
                current_list_subkey = key
            continue
        if (
            current_list_item is not None
            and current_list_subkey is not None
            and stripped.startswith("- ")
            and indent >= 6
        ):
            sub = current_list_item.setdefault(current_list_subkey, [])
            if not isinstance(sub, list):
                sub = []
                current_list_item[current_list_subkey] = sub
            sub.append(_unquote(stripped[2:].strip()))
            continue
        if ":" in stripped and current_list_item is None:
            key, value = stripped.split(":", 1)
            if not isinstance(data[current_key], dict):
                data[current_key] = {}
            data[current_key][key.strip()] = _unquote(value.strip())
    if (
        current_key is not None
        and current_list_item is not None
        and isinstance(data.get(current_key), list)
    ):
        data[current_key].append(current_list_item)
    return data


def _unquote(value: str) -> str:
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def list_topic_slugs(topics_dir: Path = TOPICS_DIR) -> list[str]:
    return sorted(path.stem for path in topics_dir.glob("*.yaml"))


def slug_dir(slug: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", slug.lower()).strip("-")


def topic_output_dir(repo_root: Path, spec: TopicSpec) -> Path:
    return repo_root / "tmp/deep-research-review" / slug_dir(spec.slug)


def topic_graph_dir(repo_root: Path, spec: TopicSpec) -> Path:
    return (
        repo_root / "tmp/deep-research-comparison" / f"{slug_dir(spec.slug)}_edgar_2hop"
    )


def required_sections(spec: TopicSpec) -> list[tuple[str, list[str]]]:
    return [
        (section, [_section_pattern(section)])
        for section in spec.archetype_config.sections
    ]


def _section_pattern(section: str) -> str:
    words = [re.escape(part) for part in section.lower().split()]
    return ".*".join(words)


def outline_text(spec: TopicSpec) -> str:
    lines = [f"# {spec.question}", "", "## Required Entities"]
    for role, entity in spec.roles.items():
        lines.append(f"- **{role.replace('_', ' ').title()}**: {entity}")
    role_values = set(spec.roles.values())
    for seed in spec.seed_entities:
        if seed.name in role_values:
            continue
        flavor_note = ""
        if seed.flavors != ("organization",):
            flavor_note = f" [{', '.join(seed.flavors)}]"
        lines.append(f"- {seed.name}{flavor_note}")
    if spec.market_theme:
        lines.extend(["", f"Market/theme: {spec.market_theme}"])
    lines.extend(["", "## Required Sections"])
    for idx, section in enumerate(spec.archetype_config.sections, start=1):
        lines.append(f"### {idx}. {section}")
        lines.append(f"- Gather evidence relevant to {section.lower()}.")
    return "\n".join(lines)


def prompt_text(spec: TopicSpec) -> str:
    return (
        "Use the attached topic outline to produce a comprehensive investment "
        f"research report.\n\nThe topic is: {spec.question}\n\n"
        "Use only evidence supplied by the retrieval pipeline. Focus on the "
        "named entities and the report structure in the outline."
    )


def report_instructions(spec: TopicSpec) -> str:
    archetype = spec.archetype_config
    sections = "\n".join(
        f"## {idx}. {section}"
        for idx, section in enumerate(archetype.sections, start=1)
    )
    return f"""\
Write a comprehensive, deeply analytical {archetype.report_kind}.
This is a full research document — not a summary.

FORMAT REQUIREMENTS:
1. TABLES: Include 3-5 tables appropriate to the topic. Each table row should cite sources.
2. BULLETS: Outside tables, each bullet should state one material fact and end with its citation.
3. Do not group multiple unrelated facts into one bullet or end a paragraph with a single citation.
4. Label unsupported claims [DATA GAP].
5. DEPTH: Each required section must contain at least 2 substantive paragraphs or 5+ cited bullets.
6. ANALYSIS: Include explicit financial, business-model, growth-driver, and risk-analysis subsections where relevant.
7. NO SHORTCUTS: Do not write an executive summary in place of the full report. If evidence is thin, still write the section and label gaps precisely.
8. GAP DISCIPLINE: Judge and write from the presented evidence. Do not create gaps for analyst consensus, management guidance, or speculative forward estimates unless the topic explicitly asks for them.

REQUIRED SECTIONS — use these EXACT headings:
{sections}
"""


def judge_system(spec: TopicSpec) -> str:
    archetype = spec.archetype_config
    dims = "\n\n".join(
        f"{idx}. {name} (1-10)\n"
        f"   {description}.\n"
        "   10 = exceptional fact use: the report uses the most relevant available facts "
        "for this dimension, quantifies the important points, connects facts directly to "
        "the thesis, and leaves no obvious missing fact category unaddressed.\n"
        "   8-9 = strong fact use: relevant facts are cited and mostly complete, but one "
        "important fact category, comparison, quantification, or caveat is thin or missing.\n"
        "   6-7 = adequate fact use: some relevant facts are used, but the dimension is "
        "materially incomplete, under-quantified, or relies on less relevant facts while "
        "better available facts are not used.\n"
        "   3-5 = weak fact use: facts are sparse, poorly matched to the dimension, mostly "
        "background/presentation, or miss several relevant available fact categories.\n"
        "   1-2 = missing, unsupported, factually misleading, or contradicted by evidence."
        for idx, (name, description) in enumerate(archetype.dimensions, start=1)
    )
    json_fields = "\n".join(f'  "{name}": N,' for name, _ in archetype.dimensions)
    return f"""\
You are a senior research quality reviewer evaluating a {archetype.report_kind}
on the question:

  "{spec.question}"

Score the report on SIX dimensions using 1-10:

{dims}

Evaluation guidance:
- Score the report primarily on the relevance, completeness, and correct use of
  facts presented in the report. Do not score based on prose polish, formatting,
  or whether the report gives the analyst useful process guidance.
- Do not award high scores for citation density alone. The cited facts must be
  the right facts for the dimension being scored.
- Penalize reports that over-index on one fact type while neglecting other
  relevant available facts, such as business, growth, risk, deal, competitive,
  operating, ownership, regulatory, or market evidence needed by the archetype.
- Penalize important missing fact categories. A report should lose points when
  a material fact type is absent, even if the surrounding prose is polished.
- Penalize facts that are included but not relevant to the section or thesis.
- Penalize unsupported confident claims more than honest uncertainty.
- Do not penalize missing analyst consensus, management guidance, or speculative
  forward estimates unless the topic explicitly requires them, but do penalize
  missing evidence that is plainly relevant and available in the report.
- Reward explicit [DATA GAP] labels only when they identify a specific missing
  fact category that matters to the dimension. Do not reward broad gap lists or
  generic caveats.
- Use the full 1-10 scale. Reserve an all-10 scorecard for rare reports that would
  require little factual revision before being sent to a decision-maker.

Return ONLY valid JSON (no markdown, no explanation outside the JSON):
{{
{json_fields}
  "overall_verdict": "pass" | "fail",
  "reason": "<one sentence summary of the report's strongest and weakest points>"
}}

Pass threshold: mean score >= 9 AND no individual score < 8.
"""
