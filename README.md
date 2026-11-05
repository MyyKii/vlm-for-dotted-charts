# VLM-Based Visual Pattern Detection in Dotted Charts

**LMU Munich · Winter Semester 2026/27 · Research project (work in progress)**

This project investigates whether fine-tuned **Vision-Language Models (VLMs)** can detect, localize, and explain visual patterns in **Process Mining Dotted Charts**. The planned approach uses **Qwen2.5-VL (3B/7B)** with parameter-efficient **QLoRA** fine-tuning.

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

1. **Event-log preparation:** Load synthetic or real logs (e.g., XES/CSV and BPI Challenge data).
2. **Pattern injection:** Programmatically introduce controlled temporal gaps, batches, or delays and record what changed.
3. **Chart generation and annotation:** Render Dotted Charts and map known patterns to bounding boxes in image coordinates.
4. **Training data preparation:** Convert annotated charts into image–instruction–response examples.
5. **VLM fine-tuning:** Prototype with Qwen2.5-VL-3B and 4-bit QLoRA; consider 7B after assessing GPU requirements.
6. **Inference and evaluation:** Predict patterns and bounding boxes on unseen charts; visualize results and measure detection/localization quality.

We intend to compare performance against **zero-shot Qwen2.5-VL** and assess generalization from synthetic or modified logs to real-world data. Dataset choices, chart views, annotation conventions, and training settings are still under investigation.

## Repository Structure

The repository separates **source code (`src/`)** from **datasets and generated artifacts (`data/`)**. Source modules and tests are being implemented incrementally.

```text
vlm-for-dotted-charts/
├── docs/
│   ├── blueprint.md         # Research goals, architecture, and methodology
│   └── project_log.md       # Progress, decisions, challenges, and tasks
├── src/                     # Python source code
│   ├── data/                # Event-log processing and pattern injection
│   ├── evaluation/          # Model evaluation and result analysis
│   ├── rendering/           # Dotted Chart generation and coordinate mapping
│   └── training/            # VLM fine-tuning and training pipelines
├── data/                    # Datasets and generated artifacts
│   ├── raw/                 # Original event logs (XES, CSV)
│   ├── processed/           # Cleaned and modified event logs
│   └── generated/
│       ├── charts/          # Rendered Dotted Chart images
│       └── annotations/     # Bounding boxes and training labels
├── tests/                   # Automated tests
├── .gitignore               # Files excluded from version control
├── makefile                 # Formatting, linting, testing, coverage
├── pyproject.toml           # Project metadata and tool configuration
├── README.md                # Project documentation
└── requirements.txt         # Python dependencies
```

### Directory Overview

| Directory | Purpose |
|---|---|
| `docs/blueprint.md` | Overarching research objectives, conceptual architecture, methodology, and evaluation strategy. |
| `docs/project_log.md` | Living record of individual progress, team meetings, decisions, encountered problems, and assigned next steps. |
| `src/data/` | Code for loading, preprocessing, and injecting patterns into event logs. |
| `src/rendering/` | Code for generating Dotted Charts and mapping pattern locations to image coordinates. |
| `src/training/` | Code for preparing training inputs and fine-tuning Qwen2.5-VL. |
| `src/evaluation/` | Code for evaluating model predictions, localization accuracy, and generalization. |
| `data/raw/` | Original event logs, preserved without modification. |
| `data/processed/` | Preprocessed event logs, including synthetically injected patterns. |
| `data/generated/charts/` | Rendered Dotted Chart images used for VLM training and evaluation. |
| `data/generated/annotations/` | Ground-truth labels, bounding boxes, and references to the corresponding chart images. |
| `tests/` | Automated tests for the processing, rendering, training, and evaluation components. |

**Documentation:** The [Technical Blueprint](docs/blueprint.md) defines the project's overarching research direction and conceptual approach. The [Project Log](docs/project_log.md) documents actual progress, findings, decisions, problems, and responsibilities throughout the project. Team members update the log as they complete work and during team meetings.

**Data management:** The `src/` directory contains version-controlled Python code, while `data/` contains input datasets and generated artifacts. Large datasets, model weights, and training outputs are excluded from Git through `.gitignore`. The data directories can be populated locally or recreated by the pipeline.

## Getting Started

### 1. Prerequisites

- **Git** for version control.
- **Python 3.11** for the local development environment. The version used for GPU training must also be compatible with the cluster and ML dependencies.
- **pip**, included with a standard Python installation, for installing packages from `requirements.txt`.
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
python -m pip install -r requirements.txt
```

Verify that the environment is active:

```bash
python --version
python -m pytest
```

If `tests/` does not yet contain test cases, pytest may report that no tests were collected.

> **GPU note:** A general `pip install -r requirements.txt` does not guarantee a CUDA-enabled PyTorch build suitable for your GPU. Check the [official PyTorch installation selector](https://pytorch.org/get-started/locally/) and the target cluster configuration before starting GPU training.

### 4. Dependency and Tool Configuration

The repository currently uses **both** `pyproject.toml` and `requirements.txt`:

**`pyproject.toml`** defines:

- `[project]`: Project name, Python compatibility, and runtime dependencies.
- `[dependency-groups]`: Development dependencies such as pytest, pytest-cov, and Ruff.
- `[tool.ruff]` and `[tool.pytest.ini_options]`: Formatting, linting, and test configuration.

**`requirements.txt`** contains the packages installed by pip, including runtime and development dependencies. The team must keep its package list consistent with `pyproject.toml` whenever dependencies are added or removed.

There is currently **no `uv.lock`**. Package versions are not pinned in the provided requirements file, so installations at different times may resolve different versions. Once the training stack works on the target GPUs, record and pin compatible versions to improve reproducibility.

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

For experimental features and changes to shared code, use a dedicated branch. Whenever possible, reference the corresponding **task ID (`T-XX`)** from the [Project Log](docs/project_log.md) to link implementation work to its assigned task.

```bash
git switch main
git pull
git switch -c feat/T-02-pattern-injection
```

Implement, test, commit, and push your work:

```bash
git add <CHANGED_FILES>
git commit -m "feat(data): add temporal gap injection (T-02)"
git push -u origin feat/T-02-pattern-injection
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
5. Reference the relevant task ID (`T-XX`) when available. Use a decision ID (`D-XX`) when the change directly implements or documents a research decision.
6. Avoid vague messages such as `fixed stuff`.

**Project Log integration:**

- **Task IDs (`T-XX`)** identify assigned work and connect branches, commits, pull requests, and individual progress updates.
- **Decision IDs (`D-XX`)** reference research or architectural decisions and their rationale.
- After completing meaningful work, update the corresponding progress entry in `docs/project_log.md` with the outcome and relevant commit or pull request.
- Decisions and new task assignments are recorded during team meetings, preserving the project's development history.

This allows the team to trace **why a change was made, who worked on it, and which task or decision it relates to**.

## Current Priorities

1. Select suitable synthetic and real event logs.
2. Define initial pattern classes and ground-truth annotation rules.
3. Agree on a reproducible baseline Dotted Chart view and training-data interface.
4. Verify pixel-coordinate mapping after chart rendering and model image preprocessing.
5. Run zero-shot Qwen2.5-VL and a small QLoRA training smoke test on the available GPU infrastructure.

See [`docs/blueprint.md`](docs/blueprint.md) for the planned implementation phases, candidate training parameters, evaluation approach, and unresolved decisions.
Record agreed research or architecture decisions in [`docs/decisions.md`](docs/decisions.md).

## Further Reading

- [Qwen2.5-VL model and examples](https://github.com/QwenLM/Qwen2.5-VL)
- [Hugging Face TRL: SFTTrainer](https://huggingface.co/docs/trl/sft_trainer)
- [PM4Py](https://processintelligence.solutions/pm4py)
- [PyTorch installation](https://pytorch.org/get-started/locally/)
