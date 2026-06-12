# Yottagraph vs. Gemini Deep Research — Benchmark

Compare two research pipelines on investment banking research questions:

- **Structured retrieval** — Yottagraph facts retrieved from a private
  structured-data backend, curated and synthesized by Gemini. This is the
  Yottagraph track used for the current results tables below.
- **`--datasource deep-research`** — Gemini Deep Research Max via the Interactions API.
- **No context** — Gemini 3 Flash with only the topic prompt and report
  outline, without retrieval or tool context.

Both pipelines are evaluated by a 6-dimension LLM judge (`judge.py`).

## Reproducibility Note

The committed reports and usage files under `reports/` are the reproducible
artifacts for this supplement. The private structured-retrieval backend used to
generate the Yottagraph evidence dossiers is not included in this public repo.

As a result:

- You can rejudge the committed reports with the public judge.
- You can run the no-context Gemini baseline.
- You can synthesize and judge a report from a prepared evidence dossier that
  you supply.
- You cannot regenerate the structured-retrieval Yottagraph reports end-to-end
  from this repo alone.

`run_direct.py` preserves the public prompt structure for planning, curation,
writing, no-context generation, and judging, but it omits the backend-specific
retrieval adapter, private tool declarations, and executable retrieval calls.

## Research Topics

Topics are YAML specs in `topics/`. Each spec declares a question, seed
entities, and one of three report archetypes:

- `strategic_alternatives` — target standalone case versus strategic buyer case.
- `competitive_financial_profile` — two-company financial comparison for a market/theme.
- `single_company_investment_memo` — one-company diligence memo.

## Report Archetypes

`topic_spec.py` defines the report archetypes, required sections, judge
dimensions, and core financial properties used by the benchmark.

### `strategic_alternatives`

Investment-banking strategic alternatives report for a target company and a
potential buyer.

Required sections:

1. Situation Overview
2. Target Standalone Case
3. Strategic Buyer Case
4. Deal Feasibility
5. Valuation
6. Alternative Paths

Judge dimensions:

- `financial_grounding`
- `target_specificity`
- `buyer_logic`
- `deal_feasibility`
- `analytical_coherence`
- `citation_coverage`

### `competitive_financial_profile`

Comparative equity research report for two companies in the same market or
theme.

Required sections:

1. Situation Overview
2. Company A Financial Profile
3. Company B Financial Profile
4. Head-to-Head Comparison
5. Risk Analysis
6. Valuation

Judge dimensions:

- `financial_grounding`
- `company_a_specificity`
- `company_b_specificity`
- `risk_assessment`
- `analytical_coherence`
- `citation_coverage`

### `single_company_investment_memo`

Single-company investment memo.

Required sections:

1. Situation Overview
2. Business Model And Segments
3. Financial Profile
4. Growth Drivers
5. Risk Factors
6. Investment View

Judge dimensions:

- `financial_grounding`
- `business_specificity`
- `growth_specificity`
- `risk_assessment`
- `analytical_coherence`
- `citation_coverage`

Available topics:

| Topic | Archetype | Sector |
|---|---|---|
| `marvell-broadcom` | strategic alternatives | semiconductors |
| `cvs-cigna` | strategic alternatives | healthcare |
| `kroger-albertsons` | strategic alternatives | consumer staples / grocery |
| `hasbro-mattel` | strategic alternatives | consumer products |
| `nvidia-amd` | competitive financial profile | semiconductors |
| `coca-cola-pepsico` | competitive financial profile | consumer staples |
| `visa-mastercard` | competitive financial profile | payments |
| `exxon-chevron` | competitive financial profile | energy |
| `costco` | single-company investment memo | retail |
| `caterpillar` | single-company investment memo | industrials |
| `jpmorgan` | single-company investment memo | banking |
| `unitedhealth` | single-company investment memo | healthcare |

## Reproducing the Public Artifacts

The committed artifacts under `reports/` are the reproducible supplement for
the blog post. The public runner preserves the prompt structure used for
planning, curation, writing, no-context generation, and judging, but it does
not include the private retrieval adapter or backend-specific tool schema.
For a concrete prompt-by-prompt example, see
[`prompt-walkthrough-marvell-broadcom.md`](prompt-walkthrough-marvell-broadcom.md).
For a small public evidence dossier that can be supplied to the structured
report mode, see
[`evidence-dossiers/marvell-broadcom.md`](evidence-dossiers/marvell-broadcom.md).

```bash
# Rejudge saved report artifacts with the current rubric.
python yottagraph-deep-research/rejudge_reports.py --datasource all

# Synthesize from the included public evidence dossier.
python yottagraph-deep-research/run_direct.py \
    --mode structured-report \
    --topic marvell-broadcom \
    --evidence-file yottagraph-deep-research/evidence-dossiers/marvell-broadcom.md

# Run the no-context baseline with a configured Gemini client.
python yottagraph-deep-research/run_direct.py \
    --mode no-context --topic costco --model gemini-3-flash-preview
```

## Structured Retrieval Notes

The private structured-retrieval pipeline used broad evidence categories rather
than web search. At a high level, the planner could request company filings,
governance and ownership facts, business segments, product information,
industry context, market data, legal and regulatory risk, recent events, and
commercial relationships. Retrieved facts were normalized into compact evidence
records with source labels, then curated into a sectioned dossier before report
generation.

## Yottagraph Research Agent Flow

The Yottagraph run is a lightweight research-agent pipeline that separates
retrieval, curation, and writing:

1. **Resolve entities** — topic seed names are matched to canonical company
   entities.
2. **Plan retrieval** — a Gemini 3.1 Flash Lite planner chooses high-recall
   evidence categories relevant to the report archetype.
3. **Retrieve facts** — the structured backend returns deterministic evidence
   records for the requested categories.
4. **Curate evidence** — a Gemini 3.1 Flash Lite curator receives the retrieved
   fact catalog with source labels and evidence text. It writes a sectioned
   Markdown evidence dossier and selects only the facts needed for each required
   report section.
5. **Synthesize report** — a Gemini 3.1 Flash Lite writer receives the curated
   dossier and produces the final report with inline citations and explicit
   diligence gaps.
6. **Judge quality** — a Gemini 3 Flash judge scores the report on the
   topic-specific, fact-focused 1-10 rubric. Usage is recorded for planner,
   curator, synthesis, and judge phases.

The model names are configured in `run_direct.py`; the Flash Lite report set
summarized below uses `gemini-3.1-flash-lite-preview` for Yottagraph planning,
curation, and synthesis, and `gemini-3-flash-preview` for judging. The Gemma 4
31B report set uses `gemma4:12b` for planning and curation and
`gemma4:31b-it-q8_0` for synthesis via local Ollama.

## Report Artifacts

Committed final report artifacts live under `reports/`:

- `reports/deep-research/` — Gemini Deep Research Max reports for all 12 topics.
- `reports/yg-3-1-flash-lite/` — live Yottagraph reports for all 12 topics,
  generated with `gemini-3.1-flash-lite-preview`.
- `reports/yg-gemma4-31b/` — live Yottagraph reports for all 12 topics,
  generated with `gemma4:12b` for planning/curation and `gemma4:31b-it-q8_0`
  for synthesis.
- `reports/no-context/` — Gemini 3 Flash reports generated with only the topic
  prompt/outline and no retrieval or tool context.
- `reports/usage/deep-research/`, `reports/usage/yg-3-1-flash-lite/`, and
  `reports/usage/yg-gemma4-31b/` — final usage and judge JSONs for each
  committed report, with no-context usage under `reports/usage/no-context/`.

Additional local run artifacts such as plans, facts, evidence, curation files,
raw Deep Research responses, and usage JSONs are written under ignored
`tmp/deep-research-review/<topic>/` on the machine that ran the experiment.

## Current Results

The tables below summarize the latest local artifacts available when this README
was updated. Scores are LLM judge mean scores on a **1-10** scale using the
fact-focused rubric in `topic_spec.py`. Deep Research token counts are `usage.total_tokens` from `DEEP_RESEARCH_RAW_iter1.json`, including tool-use and thought tokens.
The YG tables report recorded pipeline tokens for planner, curator, and
synthesis phases, excluding the single-pass judge. This section compares
**Gemini Deep Research Max** against completed **Live Yottagraph** reports using
Gemini 3.1 Flash Lite Preview and local Gemma 4 31B synthesis.

### Gemini Deep Research Max

| Topic | Mean score | Tokens | Words |
|---|---:|---:|---:|
| `marvell-broadcom` | 9.50 | 1,807,010 | 5,595 |
| `cvs-cigna` | 9.83 | 2,032,702 | 5,672 |
| `kroger-albertsons` | 9.83 | 2,005,955 | 5,994 |
| `hasbro-mattel` | 10.00 | 2,053,195 | 5,003 |
| `nvidia-amd` | 10.00 | 1,794,219 | 6,887 |
| `coca-cola-pepsico` | 9.83 | 2,587,739 | 4,540 |
| `visa-mastercard` | 10.00 | 2,383,845 | 5,583 |
| `exxon-chevron` | 9.83 | 2,203,646 | 5,902 |
| `costco` | 9.67 | 5,614,134 | 8,190 |
| `caterpillar` | 10.00 | 2,569,206 | 5,831 |
| `jpmorgan` | 10.00 | 1,898,747 | 5,431 |
| `unitedhealth` | 10.00 | 1,948,882 | 5,351 |
| **Average** | **9.87** | **2,408,273** | **5,832** |

### Live Yottagraph / Gemini 3.1 Flash Lite Preview

| Topic | Mean score | Tokens | Words | Words excl. bibliography |
|---|---:|---:|---:|---:|
| `marvell-broadcom` | 9.67 | 92,667 | 3,469 | 1,920 |
| `cvs-cigna` | 9.67 | 92,202 | 3,090 | 2,112 |
| `kroger-albertsons` | 9.83 | 98,368 | 3,265 | 2,400 |
| `hasbro-mattel` | 9.33 | 207,155 | 3,155 | 2,195 |
| `nvidia-amd` | 9.83 | 89,826 | 4,624 | 3,185 |
| `coca-cola-pepsico` | 9.83 | 230,832 | 7,682 | 2,072 |
| `visa-mastercard` | 9.33 | 82,657 | 3,351 | 2,341 |
| `exxon-chevron` | 9.83 | 109,203 | 2,999 | 2,204 |
| `costco` | 9.83 | 142,255 | 2,951 | 2,426 |
| `caterpillar` | 9.83 | 84,754 | 3,246 | 2,421 |
| `jpmorgan` | 9.17 | 80,295 | 4,468 | 2,500 |
| `unitedhealth` | 9.83 | 85,186 | 3,578 | 2,506 |
| **Average** | **9.67** | **116,283** | **3,823** | **2,357** |

Excluding bibliographies, YG reports average **2,357** body words versus
**5,832** words for Deep Research, making the YG report bodies about **2.5x
shorter**.

Across the YG runs, recorded non-judge LLM tokens total **1,395,400**:
planner **61,932** (**4.4%**), curator **783,916** (**56.2%**), and
synthesis **549,552** (**39.4%**).

### Live Yottagraph / Gemma 4 31B (local Ollama)

Planning and curation: `gemma4:12b` (11.9B, Q4_K_M, 262K context, local
Ollama). Synthesis: `gemma4:31b-it-q8_0` (31.3B, Q8_0, 262K context, local
Ollama). All 12 topics passed the judge on the first or second iteration.

| Topic | Mean score | Tokens | Words | Words excl. bibliography |
|---|---:|---:|---:|---:|
| `marvell-broadcom` | 9.83 | 106,742 | 4,609 | 3,215 |
| `cvs-cigna` | 9.83 | 116,245 | 5,638 | 3,722 |
| `kroger-albertsons` | 10.00 | 110,572 | 3,918 | 3,109 |
| `hasbro-mattel` | 10.00 | 125,498 | 5,431 | 3,447 |
| `nvidia-amd` | 9.83 | 127,385 | 5,809 | 3,694 |
| `coca-cola-pepsico` | 10.00 | 127,459 | 4,707 | 3,158 |
| `visa-mastercard` | 9.83 | 107,451 | 4,733 | 2,940 |
| `exxon-chevron` | 9.83 | 114,270 | 5,229 | 3,188 |
| `costco` | 9.83 | 102,813 | 4,765 | 2,944 |
| `caterpillar` | 10.00 | 106,272 | 4,450 | 2,701 |
| `jpmorgan` | 9.50 | 123,127 | 4,685 | 3,098 |
| `unitedhealth` | 9.50 | 109,750 | 5,367 | 3,152 |
| **Average** | **9.83** | **114,799** | **4,945** | **3,197** |

Latency for the Gemma 4 local runs is driven mostly by synthesis on the 31B
model over local Ollama:

| Topic | Total latency | Synthesis LLM latency |
|---|---:|---:|
| `marvell-broadcom` | 973.1s | 631.0s |
| `cvs-cigna` | 1,303.8s | 864.3s |
| `kroger-albertsons` | 1,106.9s | 564.9s |
| `hasbro-mattel` | 1,500.6s | 947.4s |
| `nvidia-amd` | 1,477.9s | 978.1s |
| `coca-cola-pepsico` | 1,420.9s | 782.9s |
| `visa-mastercard` | 1,197.1s | 786.7s |
| `exxon-chevron` | 1,330.1s | 904.0s |
| `costco` | 1,189.3s | 835.9s |
| `caterpillar` | 1,199.0s | 735.7s |
| `jpmorgan` | 1,531.8s | 870.1s |
| `unitedhealth` | 1,350.7s | 928.4s |
| **Average** | **1,298.4s** | **819.1s** |

Gemma 4 31B local runs average **~22 minutes** total, versus **~4.8 minutes**
for Flash Lite (API) and **~17 minutes** for Deep Research Max. Synthesis
accounts for roughly **63%** of wall-clock time.

### Flash Lite Latency Breakdown

YG Flash Lite total latency is wall-clock runtime for the full YG pipeline,
including planning, structured retrieval, evidence formatting, curation,
synthesis, judging, and artifact writes. YG Flash Lite LLM-only latency is the
sum of recorded LLM phase elapsed times in the usage JSONs; the current
artifacts record curation and synthesis elapsed time, while planner and judge
elapsed time were not persisted separately. Deep Research total latency is the
wall-clock latency reported by the Deep Research run.

| Topic | YG total latency | YG LLM-only latency | Deep Research total latency |
|---|---:|---:|---:|
| `marvell-broadcom` | 231.7s | 71.9s | 862.2s |
| `cvs-cigna` | 417.6s | 193.9s | 1169.5s |
| `kroger-albertsons` | 316.4s | 99.4s | 998.7s |
| `hasbro-mattel` | 406.9s | 145.8s | 1059.8s |
| `nvidia-amd` | 228.6s | 79.3s | 1078.4s |
| `coca-cola-pepsico` | 369.0s | 136.7s | 955.4s |
| `visa-mastercard` | 271.5s | 63.1s | 907.6s |
| `exxon-chevron` | 314.3s | 74.0s | 955.0s |
| `costco` | 220.2s | 100.6s | 1567.6s |
| `caterpillar` | 220.1s | 69.3s | 862.3s |
| `jpmorgan` | 231.2s | 75.4s | 961.2s |
| `unitedhealth` | 201.8s | 76.1s | 809.4s |
| **Average** | **285.8s** | **98.8s** | **1015.6s** |

On average, YG total latency is **3.6x faster** than Deep Research, while YG
LLM-only latency is **10.3x faster** than Deep Research.

### Flash Lite Estimated Cost Reduction

Cost estimates use published Gemini API prices available at the time of the
experiment:

- Deep Research Max: Gemini 3.1 Pro rates, estimated at $2.00 / 1M input-like
  tokens and $12.00 / 1M output-like tokens. The estimate treats
  `total_tool_use_tokens` as input/context work and `total_thought_tokens` as
  output-priced generation.
- YG Flash Lite: Gemini 3.1 Flash Lite Preview rates, estimated at $0.25 / 1M
  input tokens and $1.50 / 1M output or thought tokens. The YG estimate excludes
  the single-pass judge and includes planner, curator, and synthesis tokens.

| Topic | Deep Research cost | YG non-judge cost | Cost reduction |
|---|---:|---:|---:|
| `marvell-broadcom` | $5.64 | $0.050 | 113.7x |
| `cvs-cigna` | $6.60 | $0.047 | 141.0x |
| `kroger-albertsons` | $6.50 | $0.053 | 123.4x |
| `hasbro-mattel` | $6.40 | $0.106 | 60.5x |
| `nvidia-amd` | $6.01 | $0.052 | 116.0x |
| `coca-cola-pepsico` | $7.38 | $0.110 | 67.1x |
| `visa-mastercard` | $6.69 | $0.044 | 150.7x |
| `exxon-chevron` | $6.43 | $0.056 | 113.8x |
| `costco` | $14.79 | $0.065 | 228.2x |
| `caterpillar` | $7.16 | $0.048 | 148.8x |
| `jpmorgan` | $5.93 | $0.047 | 125.2x |
| `unitedhealth` | $5.96 | $0.049 | 122.7x |
| **Average** | **$7.12** | **$0.061** | **117.7x** |

## Takeaways

- Deep Research Max and YG Gemma 4 31B are effectively matched under the
  stricter 1-10 judge: **9.87** for Deep Research versus **9.83** for YG Gemma
  4 31B, with YG Flash Lite at **9.67**.
- The YG Gemma 4 31B run matches Deep Research quality while running entirely
  on local open-weight models with no API cost for synthesis.
- The YG pipeline uses structured retrieval, entity matching, section-aware
  evidence curation, source-backed citations, and model-specific output
  filenames.
- The Flash Lite YG run completed all 12 topics. All reports are committed under
  `reports/yg-3-1-flash-lite/`. The Gemma 4 31B reports are committed under
  `reports/yg-gemma4-31b/`.
- YG Flash Lite matches or exceeds Deep Research on several topics while using
  far fewer model tokens in the recorded pipeline. Remaining gaps are concentrated
  in archetype-sensitive dimensions such as deal feasibility and comparative
  company-specific depth.
- On the completed comparison set, the estimated YG Flash Lite cost reduction is
  roughly 61x-228x excluding the single-pass judge, and latency reduction is
  roughly 2.6x-7.1x versus Deep Research Max.

## No-Context Gemini 3 Flash Baseline

This baseline uses `gemini-3-flash-preview` with only the topic prompt,
outline, and report instructions. It does not use Yottagraph retrieval, Deep
Research, Google Search grounding, or any supplied evidence context.

| Topic | Mean score | Result | Words | Latency | Citation score |
|---|---:|---|---:|---:|---:|
| `caterpillar` | 6.17 | fail | 3,671 | 44.5s | 1 |
| `coca-cola-pepsico` | 4.17 | fail | 3,493 | 59.0s | 1 |
| `costco` | 9.00 | pass | 4,040 | 46.1s | 8 |
| `cvs-cigna` | 4.67 | fail | 3,987 | 63.9s | 1 |
| `exxon-chevron` | 6.17 | fail | 4,461 | 65.7s | 1 |
| `hasbro-mattel` | 5.83 | fail | 3,310 | 54.1s | 1 |
| `jpmorgan` | 7.17 | fail | 3,913 | 49.8s | 1 |
| `kroger-albertsons` | 6.83 | fail | 4,156 | 65.2s | 1 |
| `marvell-broadcom` | 4.67 | fail | 4,267 | 50.6s | 1 |
| `nvidia-amd` | 4.67 | fail | 4,116 | 63.2s | 1 |
| `unitedhealth` | 6.00 | fail | 3,935 | 71.6s | 1 |
| `visa-mastercard` | 7.33 | fail | 3,476 | 47.7s | 1 |
| **Average** | **6.06** | **1 / 12 pass** | **3,902** | **56.8s** | **1.58** |

Takeaway: without supplied evidence or search tools, Gemini 3 Flash can produce
plausible report structure and some recognizable company-specific analysis, but
it mostly fails the fact-focused judge because material claims are uncited. The
single pass (`costco`) should be interpreted cautiously because the generated
report still had no cited lines in the automatic citation counter.
