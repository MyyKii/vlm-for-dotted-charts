# VLM-Based Visual Pattern Detection in Dotted Charts

**LMU Munich · Winter Semester 2026/27 · Research project (work in progress)**

This project investigates whether fine-tuned **Vision-Language Models (VLMs)** can detect, localize, and explain visual patterns in **Process Mining Dotted Charts**. The planned approach uses **Qwen3.5-9B** with parameter-efficient **QLoRA** fine-tuning; larger models may be considered depending on GPU availability.

## Background and Research Goal

Event logs record activities, timestamps, and case identifiers from business processes. A **Dotted Chart** visualizes these events as points—typically with time on the horizontal axis, cases on the vertical axis, and colors representing activities. It makes temporal and operational patterns visible, including:

- **Temporal gaps:** Periods with unusually few or no recorded events.

- **Batching:** Multiple events occurring around the same time.

- **Case delays / outliers:** Cases with unexpectedly long intervals between activities.

- **Workload spikes:** Concentrations of activity within a short period.

Recognizing such patterns in a dense chart can require significant manual inspection. Our central research question is:

> Can a fine-tuned Vision-Language Model reliably detect, locate, and explain process anomalies and operational patterns in Process Mining Dotted Charts?

The initial focus is on **visual detection, localization (bounding boxes), and evidence-based interpretation**. A visual gap alone, for example, does not establish that a system outage occurred.

## Proposed Approach

1. **Event-log preparation:** Load synthetic or real logs (e.g., XES/CSV and BPI Challenge data) and store standardized event logs internally as Parquet.

2. **Pattern injection:** Programmatically introduce controlled temporal gaps, batches, or delays and record what changed.

3. **Chart generation and annotation:** Render Dotted Charts and map known patterns to bounding boxes in image coordinates.

4. **Training data preparation:** Convert annotated charts into image–instruction–response examples.

5. **VLM fine-tuning:** Prototype with **Qwen3.5-9B** and 4-bit QLoRA; consider larger models only after assessing GPU requirements.

6. **Inference and evaluation:** Predict patterns and bounding boxes on unseen charts; visualize results, measure detection/localization quality, and track experiments with MLflow.

We intend to compare performance against **zero-shot Qwen3.5-9B** (optionally Qwen3-VL-8B-Instruct as an additional baseline) and assess generalization from synthetic or modified logs to real-world data. Dataset choices, chart views, annotation conventions, and training settings are still under investigation.

## Repository Structure

The repository separates **source code (`src/`)** from **datasets and generated artifacts (`data/`)**. Source modules and tests are being implemented incrementally.
```text
vlm-for-dotted-charts/
├── docs/
│   ├── blueprint.md         # Research goals, architecture, and methodology
│   ├── project_log.md       # Progress, decisions, challenges, and tasks
│   └── change_logs/         # Technical change history
├── src/                     # Python source code
│   ├── data/                # Event-log processing and pattern injection
│   ├── evaluation/          # Model evaluation and result analysis
│   ├── rendering/           # Dotted Chart generation and coordinate mapping
│   └── training/            # VLM fine-tuning and training pipelines
├── data/                    # Datasets and generated artifacts
│   ├── raw/                 # Original event logs (XES, CSV)
│   ├── processed/           # Standardized/modified logs (Parquet) and metadata
│   └── generated/
│       ├── charts/          # Rendered Dotted Chart images (PNG)
│       └── annotations/     # Bounding boxes (JSON) and training labels (JSONL)
├── tests/                   # Automated tests
├── AGENTS.md                # Shared coding-agent instructions
├── CLAUDE.md                # Shared coding-agent instructions
├── .gitignore               # Files excluded from version control
├── makefile                 # Formatting, linting, testing, coverage
├── pyproject.toml           # Project metadata and tool configuration
└── README.md                # Project documentation
```

### Directory Overview

| Directory | Purpose |
|---|---|
| `docs/blueprint.md` | Overarching research objectives, conceptual architecture, methodology, and evaluation strategy. |
| `docs/project_log.md` | Living record of team progress, meetings, decisions, and next steps. |
| `docs/change_logs/` | Technical change logs for meaningful implementation and configuration changes. |
| `src/data/` | Code for loading, preprocessing, and injecting patterns into event logs. |
| `src/rendering/` | Code for generating Dotted Charts and mapping pattern locations to image coordinates. |
| `src/training/` | Code for preparing training inputs and fine-tuning Qwen3.5-9B. |
| `src/evaluation/` | Code for evaluating model predictions, localization accuracy, and generalization. |
| `data/raw/` | Original event logs, preserved without modification. |
| `data/processed/` | Standardized and pattern-injected event logs in Parquet format, with JSON metadata. |
| `data/generated/charts/` | Rendered Dotted Chart images used for VLM training and evaluation. |
| `data/generated/annotations/` | Ground-truth labels and bounding boxes (JSON), plus VLM instruction datasets (JSONL). |
| `tests/` | Automated tests for the processing, rendering, training, and evaluation components. |

**Documentation:** The [Technical Blueprint](docs/blueprint.md) defines the project's overarching research direction and conceptual approach. The [Project Log](docs/project_log.md) records team progress, research findings, decisions, and next steps discussed during team meetings.

**Data management:** The `src/` directory contains version-controlled Python code, while `data/` contains input datasets and generated artifacts. Large datasets, model weights, and training outputs are excluded from Git through `.gitignore`. The data directories can be populated locally or recreated by the pipeline.

## Getting Started

### 1. Prerequisites

- **Git** for version control.

- **Python 3.11** for the local development environment. The version used for GPU training must also be compatible with the cluster and ML dependencies.

- **pip** (version 25.1 or newer for dependency groups) to install dependencies from `pyproject.toml`.

- **GNU Make** to use the commands defined in `makefile` (optional; the tools can also be run directly).

- For GPU training: a compatible PyTorch/CUDA environment and access to suitable hardware. **CPU-only setup is sufficient for documentation, basic data processing, and unit tests**, but not practical for the planned large-model fine-tuning.

The current `pyproject.toml` identifies the project as `vlm-for-dotted-charts` and declares Python `>=3.11`.

### 2. Clone the Repository

Copy the HTTPS or SSH clone URL from the repository's hosting page:
```bash
git clone <REPOSITORY_URL>
cd vlm-for-dotted-charts
```

Replace `<REPOSITORY_URL>` with the actual URL. If the locally created directory has another name, change into that directory instead.

### 3. Create a Virtual Environment

From the repository root, create an isolated Python 3.11 environment:
```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

On Windows (PowerShell), activate it with `.venv\Scripts\Activate.ps1` instead.

Install the dependencies:
```bash
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install --group dev
```

Verify that the environment is active:
```bash
python --version
python -m pytest
```

If `tests/` does not yet contain test cases, pytest may report that no tests were collected.

> **GPU note:** A general `pip install -e .` does not guarantee a CUDA-enabled PyTorch build suitable for your GPU. Check the [official PyTorch installation selector](https://pytorch.org/get-started/locally/) and the target cluster configuration before starting GPU training.

### 4. Dependency and Tool Configuration

The repository uses `pyproject.toml` as its primary dependency and tool configuration:

**`pyproject.toml`** defines:

- `[project]`: Project name, Python compatibility, and runtime dependencies.

- `[dependency-groups]`: Development dependencies such as pytest, pytest-cov, and Ruff.

- `[tool.ruff]` and `[tool.pytest.ini_options]`: Formatting, linting, and test configuration.

Install runtime dependencies with `pip install -e .` and development tools with `pip install --group dev` (pip ≥25.1). Avoid maintaining a second, independent dependency list.

Dependencies are currently not fully pinned. Once the training stack works on the target GPUs, record compatible versions in a lockfile to improve reproducibility.

## Preparing Event Logs

Event-log preparation supports local `.xes`/`.csv` files and HTTP(S) downloads.
After the editable installation above, prepare a log from the repository root:

```bash
python scripts/prepare_event_log.py \
    --input data/raw/receipt.xes \
    --output data/processed/receipt.parquet
```

To download a source into `data/raw/` and prepare it through the same pipeline:

```bash
python scripts/prepare_event_log.py \
    --url "https://example.org/event_log.xes" \
    --output data/processed/event_log.parquet
```

Provide exactly one of `--input` or `--url`. The download uses the URL's filename;
use `--filename receipt.xes` (or a `.csv`/`.xes.gz` name) for endpoints without a
usable filename. Filenames must start with a letter, number, or underscore and
contain only letters/numbers/underscores, spaces, dots, and hyphens. Paths and
unsupported extensions are rejected. Downloads stream with timeouts and are
published only after completion; failed transfers leave no partial source files.
Existing downloads require `--overwrite`, which also permits replacing processed
outputs. The JSON metadata records `source_url` alongside the checksum of the
downloaded local file. Completed sources remain available if log validation fails.

Gzip-compressed XES downloads are extracted automatically. For example:

```bash
python scripts/prepare_event_log.py \
    --url "https://data.4tu.nl/file/533f66a4-8911-4ac7-8612-1235d65d1f37/3276db7f-8bee-4f2b-88ee-92dbffb5a893" \
    --filename BPI_Challenge_2012.xes.gz \
    --output data/processed/BPI_Challenge_2012.parquet \
    --dataset-id bpic2012
```

Both `BPI_Challenge_2012.xes.gz` and `BPI_Challenge_2012.xes` are retained under
`data/raw/`. The pipeline processes the extracted `.xes`, whose checksum is
recorded in metadata alongside the original URL. Both raw destinations require
`--overwrite` if either already exists. Failed downloads or extraction leave no
incomplete files and preserve existing files. Use the extracted `.xes` for later
local `--input` runs. Only gzip-compressed XES is extracted; other archive formats
and compressed CSV are unsupported.

For CSV files, map the source columns and specify the timezone of naive dates:

```bash
python scripts/prepare_event_log.py \
    --input data/raw/receipt.csv \
    --output data/processed/receipt.parquet \
    --case-id-column case_id \
    --activity-column activity \
    --timestamp-column timestamp \
    --source-timezone Europe/Berlin
```

Use `--csv-separator ';'` for semicolon-separated input and `--timestamp-format`
for non-ISO dates (for example, `'%d.%m.%Y %H:%M'`). Run
`python scripts/prepare_event_log.py --help` for all options. Failures return a
nonzero exit status; successful runs report event/case/activity counts, the UTC
time range, and both output paths.

The pipeline preserves raw files and optional event attributes, normalizes
timestamps to UTC, and orders events by case, time, and original source position.
Naive timestamps require an explicit source timezone; invalid dates and ambiguous
or nonexistent local times fail. Duplicated event combinations are reported and
retained. Existing outputs require `--overwrite`.

Outputs are **Parquet** and a same-stem **JSON** sidecar containing checksums,
configuration, counts, schema/storage version, and software versions. Source
`identity:id` values are preserved; otherwise `source-row:N` IDs are generated.
Pair event IDs with metadata's `source_sha256` across logs. `@@source_row` retains
the original zero-based order. Dataset IDs default to the source filename stem;
use `--dataset-id` and `--split-group-id` to associate related extracts with their
shared source group. This phase does not assign train/validation/test splits.

Reload a validated DataFrame for pattern injection or rendering:

```python
from data.event_logs.storage import load_processed_event_log

events = load_processed_event_log("data/processed/receipt.parquet")
```

Reloading verifies the sidecar, checksum, schema, event counts, and UTC timestamps.
Scalar optional attributes are supported; conversions that change values or
dtypes fail before outputs are published. See the
[Phase 1 event-log preparation documentation](docs/event_log_preparation.md)
for the reusable module interfaces and current limitations.

## Controlled Pattern Injection

Phase 2 creates deterministic Temporal Gap and Batching variants from Phase-1
Parquet/JSON inputs. For example:

```bash
python scripts/inject_patterns.py \
    --input data/processed/BPI_Challenge_2012.parquet \
    --preset gap_medium --sample-cases 500 --seed 42 \
    --output-root data/processed/injected
```

Each independent variant contains exactly `events.parquet`, `changes.parquet`,
and `manifest.json`, preserving source data and stable identities. Ordered JSON
recipes support nonconflicting injections; an empty recipe creates an unchanged
control. Candidate locations use event-log coordinates and require later visual
verification. See the [Phase 2 guide](docs/pattern_injection.md) for batching,
targets, recipes, schemas, loading, safeguards, and limitations.

## Rendering and Inspecting Dotted Charts

Phase 3 uses one Matplotlib Agg renderer for inspection and export. With the
project environment active, open a saved Phase-2 variant in Jupyter to compare
the validated baseline and modified views in memory.

```bash
python -m pip install --group notebook
jupyter lab notebooks/review_charts.ipynb
```

To export a clean pair, replace the variant directory with your saved path.

```bash
python scripts/render_charts.py \
    --variant data/processed/injected/bpic2012/gap_60c363dc8f11e86a \
    --view focused --injection-id inj_001 --region-id region_001 \
    --context-hours 12 --role both
```

Each chart gets a `chart.png` and `rendering.json` under `data/generated/charts`.
The metadata records the view, filters, source identity, and exported-image
geometry for Phase 4. See the [Phase 3 guide](docs/dotted_chart_rendering.md) for
view configurations, missing-baseline behavior, and coordinate mapping.

## Development Workflow

### Formatting, Linting, and Tests

Code quality tools are configured in `pyproject.toml`. After activating the virtual environment, run the following checks before committing:
```bash
ruff format --check .                    # Check formatting without changes
ruff check .                            # Check lint rules
python -m pytest                        # Run tests
python -m pytest --cov=. --cov-report=term-missing
```

The repository's `makefile` also provides shortcuts:
```bash
make ruff    # Format and auto-fix lint issues
make check   # Format, auto-fix, and run tests
make cov     # Run tests with coverage
```

**Note:** `make ruff` and `make check` run `ruff format` and `ruff check --fix`, so they **modify source files**. Review the diff before committing. The lowercase filename `makefile` is recognized automatically by GNU Make.

### Working Together

For experimental features and changes to shared code, use a dedicated branch. Reference the corresponding **GitHub Issue** (and task ID, if applicable) to link implementation work to its assignment.
```bash
git switch main
git pull
git switch -c feat/t-02-pattern-injection
```

Implement, test, commit, and push your work:
```bash
git add <CHANGED_FILES>
git commit -m "feat(data): add temporal gap injection (T-02)"
git push -u origin feat/t-02-pattern-injection
```

Then open a pull request for review or integration, referencing the relevant task (`T-XX`) and, where applicable, the underlying research decision (`D-XX`).

The team may allow small documentation or configuration fixes directly on `main`. However, **research decisions affecting datasets, annotation schemas, training strategies, or evaluation criteria must be discussed and documented in the Project Log**.

### Branch Naming Conventions

Use lowercase, descriptive branch names grouped by purpose. Include the corresponding task ID when available. Avoid personal names or ambiguous labels such as `name_test_123`.

**Format:** `<type>/<task-id>-<short-description>`

| Type | Purpose | Example |
|---|---|---|
| `feat` | New functionality | `feat/t-02-pattern-injection` |
| `fix` | Bug fixes | `fix/t-03-bbox-coordinate-mapping` |
| `chore` | Maintenance, tooling, or dependencies | `chore/update-dependencies` |
| `refactor` | Code restructuring without changing behavior | `refactor/t-01-event-log-parser` |
| `docs` | Documentation work | `docs/update-blueprint` |

Task IDs are optional for changes that are not associated with an assigned task.

### Commit Naming (Conventional Commits)

Follow the [Conventional Commits](https://www.conventionalcommits.org/) convention for a consistent and readable Git history.

**Format:** `<type>(<optional-scope>): <short imperative description> (T-XX)`

| Type | Description | Example |
|---|---|---|
| `feat` | A new feature | `feat(data): add temporal gap injection (T-02)` |
| `fix` | A bug fix | `fix(rendering): correct bounding box offsets (T-03)` |
| `docs` | Documentation only | `docs(blueprint): clarify annotation approach (D-02)` |
| `refactor` | Code restructuring without changing behavior | `refactor(data): simplify event log loading (T-01)` |
| `test` | Tests added or corrected | `test(rendering): add coordinate mapping tests (T-03)` |
| `chore` | Maintenance or dependency updates | `chore(deps): update development dependencies` |
| `ci` | CI/CD configuration | `ci: add pull request checks` |

**Commit message rules:**

1. Use the imperative mood (`add`, not `added` or `adds`).

2. Aim for a subject line of no more than 50–72 characters.

3. Start the description after the colon with a lowercase letter.

4. Do not end the subject line with a period.

5. Reference the relevant task to the issues when available.

6. Avoid vague messages such as `fixed stuff`.

## Current Priorities

1. Select suitable synthetic and real event logs.

2. Define initial pattern classes and ground-truth annotation rules.

3. Agree on a reproducible baseline Dotted Chart view and training-data interface.

4. Verify pixel-coordinate mapping after chart rendering and model image preprocessing.

5. Run zero-shot Qwen3.5-9B and a small QLoRA training smoke test on the available GPU infrastructure.

See [`docs/blueprint.md`](docs/blueprint.md) for the planned implementation phases, candidate training parameters, evaluation approach, and unresolved decisions.

Record agreed research or architecture decisions in [`docs/decisions.md`](docs/decisions.md).

## Further Reading

- [Qwen3-VL model and examples](https://github.com/QwenLM/Qwen3-VL)

- [Hugging Face TRL: SFTTrainer](https://huggingface.co/docs/trl/sft_trainer)

- [PM4Py](https://processintelligence.solutions/pm4py)
- [MLflow documentation](https://mlflow.org/docs/latest/)

- [PyTorch installation](https://pytorch.org/get-started/locally/)
