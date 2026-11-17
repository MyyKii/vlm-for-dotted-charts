# Repository Instructions — VLM-Based Visual Pattern Detection in Dotted Charts

These instructions apply to the entire repository and are shared by coding assistants.

Before changing code, inspect the relevant implementation, tests, `pyproject.toml`, and, when applicable, `README.md`, `makefile`/`Makefile`, `docs/`, and any task-specific implementation plan. Read any more specific `AGENTS.md` files in affected subdirectories.

Treat the checked-in implementation and tool configuration as the source of truth for **current behavior**. The blueprint and implementation plans describe intended behavior; if they conflict with the existing code or these rules, identify the conflict rather than silently assuming either is correct.

## Research objective

This LMU research project investigates whether a fine-tuned Vision-Language Model (VLM) can **detect, localize, and explain visual patterns in Process Mining Dotted Charts**.

- **Data generation:** Load real or synthetic event logs, introduce controlled patterns (initially temporal gaps, batching, case delays/outliers, and workload spikes), and retain traceable ground truth.

- **Visualization and annotations:** Generate Dotted Charts with PM4Py where suitable or a deterministic custom renderer when necessary for accurate coordinate mapping; diversify views and produce verified pattern-instance labels and image-space bounding boxes.

- **VLM approach:** Evaluate **Qwen3.5-9B** as the primary fine-tuning candidate, with larger models considered depending on GPU availability. Investigate supervised fine-tuning with **QLoRA**, using zero-shot Qwen3.5-9B as the main baseline and Qwen3-VL-8B-Instruct as an optional comparison model.

- **Evaluation:** Compare detection, localization, and evidence-based explanations on held-out charts and independent event logs using suitable classification and spatial metrics.

The target is **visual pattern recognition**, not proof of an operational root cause. A visible gap, for example, does not by itself demonstrate a system outage. Keep research comparisons fair and reproducible without assuming that a synthetic pattern is automatically visible or unambiguous.

## Project structure and changes

Prefer existing modules and APIs. The paths below describe responsibilities, and some components are still planned. **Do not create placeholder directories or move working code solely to match this list.**

| Location | Responsibility |
| --- | --- |
| `src/data/` | Event-log loading, preprocessing, validation, controlled pattern injection, and provenance |
| `src/data/event_logs/` (planned) | Config, loader, preprocessing, validation, and Parquet storage for XES/CSV event logs |
| `src/rendering/` | PM4Py or deterministic custom Dotted Chart rendering, visualization variants, coordinate mapping, and annotation checks |
| `src/training/` | Model-agnostic VLM dataset formatting, Qwen3.5-9B inference, QLoRA training, model-specific processors, and output parsing |
| `src/evaluation/` | Dataset splits, baselines, matching and localization metrics, and result analysis |
| `scripts/` (when needed) | Thin command-line entry points calling reusable code in `src/` |
| `tests/` | Fast, deterministic unit and integration tests, including small tracked fixtures and expected annotations |
| `docs/` | Blueprint, implementation plans, technical documentation, and `docs/change_logs/` |
| `data/raw/` | Unmodified source event logs (XES/CSV); separate from the Python `src/data/` code |
| `data/processed/` | Standardized and injected event logs in Parquet format (`.parquet`), plus provenance and injection metadata (`.json`) |
| `data/generated/charts/` | Generated Dotted Chart images (`.png`) and rendering metadata (`.json`) |
| `data/generated/annotations/` | Ground-truth labels and bounding boxes (`.json`); model-specific training manifests (`.jsonl` where applicable) |
| `outputs/`, `models/`, `checkpoints/` (when needed) | Local experiments, models, and training artifacts excluded from Git |

- Make the smallest coherent change; preserve established public APIs and directory conventions unless the task requires otherwise.

- Avoid parallel implementations, unrelated refactors, unnecessary dependencies, and new frameworks.

- Keep event-log processing, pattern injection, rendering, annotations, training, and evaluation independently testable.

- When implementing a task with a documented step-by-step plan, **follow its stages in order**. After each **completed logical implementation stage**, add and run focused tests under `tests/`, fix failures, and only then advance. Do not declare a stage complete without satisfying its acceptance criteria; documentation-only edits do not require new code tests.

## Python conventions

- Use the Python version, dependencies, Ruff rules, and test configuration declared in `pyproject.toml`; do not assume a different version or formatting policy.

- Use `snake_case` for functions, variables, and modules; `PascalCase` for classes; and `UPPER_SNAKE_CASE` for constants.

- Add type hints to new or changed public interfaces; document non-obvious data schemas, coordinate conventions, shapes, and side effects.

- Prefer `pathlib.Path`, explicit validation, informative exceptions, and small functions with clear responsibilities.

- Avoid hard-coded machine-specific paths, hidden mutable global state, `sys.path` workarounds, broad exception suppression, and unexpected input mutation.

- Keep reusable logic in `src/`, not in scripts or notebooks. Update `pyproject.toml` for dependencies; do not create a competing `requirements.txt` unless explicitly requested.

- Follow Ruff formatting and linting without unrelated formatting-only changes.

## Event-log, pattern, and annotation contracts

- Use **PM4Py and Pandas** for event-log processing. Support standard event-log columns `case:concept:name`, `concept:name`, and `time:timestamp`; map other source column names explicitly without discarding additional useful attributes.

- Preserve original files under `data/raw/`. Do not rewrite or silently repair them. Record source identity, configuration, transformations, and relevant software versions for derived data.

- Use **Parquet (`.parquet`) as the preferred internal storage format** for standardized and pattern-injected event logs under `data/processed/`. Read original XES/CSV files without changing them; preserve stable case/event IDs, additional event attributes, timestamp values, and a documented time-zone convention through Parquet round trips. Validate schema and event counts when writing and reloading.

- Store **injection manifests, provenance, and rendering/annotation metadata as JSON (`.json`)**, generated Dotted Charts as PNG (`.png`), and model-specific instruction datasets as JSONL (`.jsonl`) when appropriate. Keep binary data such as images as referenced files rather than embedding them in JSONL by default. Record the Parquet schema/storage version and the source-to-derived-file relationship; use `pyarrow` or another explicitly declared compatible Parquet engine.

- Keep case IDs and event identities stable across loading, filtering, injection, sorting, and rendering. Where source logs lack event IDs, create a documented, stable derived identifier. Preserve original row/order information for equal timestamps.

- Handle timestamps and time zones explicitly. Reject invalid or ambiguous values rather than silently inventing timestamps; document the time-zone assumptions for naive values.

- Validate required columns, event counts, missing values, and timestamp consistency. Sorting events chronologically does not prove the underlying process behavior is valid.

- Pattern injection must record its **type, parameters, seed, source log, affected cases/events, and time interval**, as applicable. Preserve within-case ordering and process dependencies where feasible. **Intentional violations are permitted for visual pattern synthesis** when their purpose, affected events, plausibility, and validation are documented. Distinguish behavioral deviations from recording errors; do not accidentally introduce unexplained inconsistencies.

- Prioritize **visual plausibility, pattern diversity, and annotation accuracy** over strict process consistency for this visual-recognition task, while recording the trade-off. Never assume an injected pattern is visible, or that an unmodified chart has no naturally occurring patterns. Define visibility checks and a negative-example policy explicitly.

- Support **zero, one, or multiple pattern instances** per chart. Give each instance a stable ID, class label, bounding box (when localizable), and explicit visibility status (e.g., visible, partially visible, not visible, ambiguous). Exclude or specially mark instances that are insufficiently visible; do not fabricate confident boxes for unlocalizable or clipped patterns.

- Preserve a verifiable mapping among **source log → modified log → rendered chart → annotation → VLM training sample**. Use unique chart/sample IDs and explicit provenance metadata; do not rely on filenames or row positions alone.

- Record chart dimensions, plotted attributes, case sorting, time range, styling, and every crop/resize transformation. For any bounding box, specify its coordinate space and order (e.g., `[xmin, ymin, xmax, ymax]`).

- Prefer PM4Py for event-log processing and Dotted Chart generation when suitable. The classic PM4Py Dotted Chart renderer uses Graphviz/Neato; **do not assume** it provides Matplotlib `ax.transData` or usable event-to-pixel mappings. If accurate mappings are unavailable, use a **deterministic custom renderer** (e.g., Matplotlib) with explicit coordinate tracking. Make layout, style, and any random color assignment reproducible and record their settings. Validate boxes against final exported images with overlays and automated boundary tests.

- Keep **model-independent ground truth** in original chart pixel coordinates separate from model-specific targets. **Qwen3.5-9B** uses normalized `[0, 1000]` coordinates for 2D bounding boxes, relative to the specific input image. Pure resizing preserves normalized coordinates, while **cropping or padding requires coordinate adjustments**. Implement and test coordinate conversions, including box order, clipping, crop offsets, and round-trip overlays. Ensure compatibility with optional comparison models and never mix coordinate spaces.

- Keep injection metadata and other ground-truth information out of image-only model inputs. Explanations must describe visible evidence rather than inventing operational causes.

## Model selection, visual preprocessing, and fine-tuning

- **Primary candidate:** `Qwen/Qwen3.5-9B` is the preferred model for fine-tuning experiments. Larger models may be considered if GPU resources permit. Keep model IDs and processor settings configurable rather than hard-coding a single model throughout the pipeline.

- **Optional comparison:** Use zero-shot Qwen3.5-9B as the primary baseline to measure fine-tuning improvements. Qwen3-VL-8B-Instruct may serve as an additional comparison model when scientifically useful.

- **Hardware gating:** Verify the **available GPU model, VRAM, CUDA compatibility, and job limits** before selecting a training configuration. Run a small **multimodal QLoRA smoke test** at the intended image resolution and batch size; measure peak VRAM, runtime, and gradient flow. Do not assume that a particular model configuration fits without testing.

- **Architecture and input resolution:** Qwen3.5 supports multimodal image understanding, but dense Dotted Charts and tiny event markers may still pose challenges. Preserve chart aspect ratios, record original dimensions and effective processor resolution, and verify that relevant patterns remain visible after preprocessing. Compare full-chart inputs with cropped views where appropriate.

- **Pixel budget:** Make image-resolution or `max_pixels` settings explicit and configurable after verifying the exact processor API. Values such as `1024 * 1024` pixels are **candidate limits only**. A pixel cap may discard small dots; compute/memory usage depends on the resulting visual tokens and other sequence/training settings, not on an unverified simple quadratic rule in input pixels.

- **Fine-tuning stack:** Use the dependencies and interfaces that are actually installed and validated. Hugging Face **Transformers/PEFT/TRL with 4-bit QLoRA** remains the baseline stack. **Unsloth** or **LLaMA-Factory** are optional alternatives after verifying support for **Qwen3.5-9B**, multimodal supervised fine-tuning, the image processor, GPU/CUDA compatibility, and dataset format. Do not assume performance or memory improvements without benchmarking.

- **Trainable modules:** Start with a small, verified adapter configuration, inspect which language, vision, and multimodal-projector parameters actually receive gradients, and record the selection. **Do not assume that vision-encoder/projector LoRA is automatically attached or universally required.** Compare frozen vision components against selectively trainable vision/projector modules when hardware and research goals permit; check for overfitting and memory costs.

- **Quantization and precision:** Validate `bitsandbytes` 4-bit support on the target GPU/CUDA stack, use supported `bf16`/`fp16` choices, and treat gradient checkpointing and optimized attention kernels as conditional optimizations. A small CPU or Mac environment can test data and output formatting, but cannot substitute for the planned CUDA QLoRA smoke test.

- **Grounding contracts:** For **Qwen3.5-9B**, document and test `bbox_2d = [xmin, ymin, xmax, ymax]` normalized to `[0, 1000]` **for each input view/crop**. Normalized boxes remain unchanged under pure resizing but must be recalculated for cropping, padding, or changes in framing. Keep original-image pixel coordinates as canonical ground truth. Implement and validate coordinate conversions, including box order, clipping, crop offsets, and bidirectional overlay tests before training. Verify coordinate conventions separately for optional comparison models.

- **Fair model comparisons:** Compare candidates on the same held-out examples, prompt/output schema, annotation policy, image/view policy, and evaluation code. Report actual peak VRAM, preprocessing resolution, latency, cost, localization scores, and explanation quality. Model size and generic benchmark scores do **not** establish superior Dotted-Chart localization.

Reference documentation (verify current revisions before implementation): [Qwen3.5-9B model](https://huggingface.co/Qwen/Qwen3.5-9B), [Qwen3.5 Transformers documentation](https://huggingface.co/docs/transformers/model_doc/qwen3_5), [Unsloth Qwen3.5 fine-tuning](https://unsloth.ai/docs/models/qwen3.5/fine-tune), [Unsloth vision fine-tuning](https://unsloth.ai/docs/basics/vision-fine-tuning).

## Experiments, comparability, and caching

- Fix and record seeds for sampling, injection, rendering variants, splits, and training where feasible. A seed alone does not guarantee deterministic GPU execution.

- Assign train/validation/test splits by the **highest shared provenance level** available (e.g., original dataset, underlying process, or source log). Logs derived from the same process—including monthly extracts—must not inadvertently cross splits, nor may their injected variants, crops, or renderings. Record provenance grouping and any limitations in establishing independence.

- Do not use held-out evaluation logs or charts to tune prompts, pattern definitions, annotation rules, or hyperparameters. Prefer at least one independent event log for generalization testing where feasible.

- For direct comparisons, hold the evaluation examples, ground-truth policies, metrics, and relevant inference settings constant. Vary one experimental factor at a time when drawing causal conclusions.

- Record the effective configuration: source-log identifiers/hashes, injected patterns and parameters, image/rendering and crop settings, annotation schema/version, split policy, prompt version, **model family/checkpoint and processor revision, effective pixel budget and box-coordinate convention**, LoRA targets/precision/quantization, actual GPU/VRAM measurements, seeds, library versions, and output paths.

- Reuse cached charts, annotations, and model outputs only when **all content-affecting inputs and settings** are compatible. Incompatible or legacy cache entries must be regenerated explicitly rather than silently reused.

- Keep quick smoke tests and exploratory checks separate from final evaluation. Report detection precision/recall/F1 and localization metrics (e.g., IoU with clearly defined matching/thresholds), including false positives and class-specific ambiguity; explanation quality requires its own assessment.

- Prefer small CPU-friendly subsets and lightweight fixtures while developing; scale to large datasets, QLoRA training, and expensive benchmarking only when necessary and authorized.

## MLflow Experiment Tracking

- Use **MLflow** for tracking meaningful VLM training and evaluation experiments, enabling reproducibility and systematic comparison of models, datasets, and training strategies. Do not require MLflow for ordinary data-processing operations or quick unit tests.

- Integrate **MLflow directly into the VLM training and evaluation pipeline** while keeping training and evaluation functional when tracking is disabled or unavailable.

- Prefer native Hugging Face Trainer integration (`report_to="mlflow"`) when supported for automatic logging of training metrics and parameters.

- Use the MLflow Tracking API for project-specific metrics (e.g., Detection F1, Bounding Box IoU), evaluation artifacts, and dataset metadata. **Avoid logging the same metric twice.**

- Make the tracking URI, experiment name, and tracking state configurable. Support local tracking during development and a shared tracking server for team experiments when available.

- Organize experiments consistently: use one run per distinct training configuration, with meaningful run names, tags, and the corresponding Git commit. Link separately executed evaluations to their training run or model artifact.

### Parameters and Metrics

- **Model & training:** Log model/checkpoint identifiers, processor versions, LoRA configuration and target modules, quantization, learning rate, batch size, gradient accumulation, epochs, seeds, effective image resolution, and relevant hardware information.

- **Dataset:** Record dataset version, source-log provenance, split configuration, pattern injection strategy and distribution, rendering settings, visibility policy, and annotation schema.

- **Training metrics:** Track training/validation loss, learning rate, and relevant runtime or memory statistics.

- **Evaluation metrics:** Log detection Precision/Recall/F1, localization IoU, false-positive rates, and available explanation-quality metrics. Include per-pattern results, evaluation thresholds, matching criteria, and dataset versions.

### Artifacts and Reproducibility

- Store effective experiment configurations, evaluation summaries, and representative prediction visualizations with ground-truth and predicted bounding boxes.

- Save model checkpoints or LoRA adapters selectively according to storage limits. Do not automatically upload full base-model weights or large datasets.

- Link locally stored checkpoints and evaluation results to their corresponding **MLflow run IDs**. Record external artifact paths where applicable.

- Keep local MLflow databases and artifacts outside Git. Never log credentials, sensitive event-log contents, or restricted datasets.

- Ensure tracking failures are reported clearly and do not silently discard experiment results. Preserve results locally when possible, even if tracking is unavailable.

- Keep unit tests independent of remote MLflow services.

- Preserve consistent evaluation datasets, metrics, annotation conventions, and thresholds across runs to enable fair comparisons.

## Testing and tool commands

- Use pytest for tests and Ruff for formatting and linting, as configured in `pyproject.toml`.

- **After every completed logical implementation stage**, add and execute focused tests under `tests/` before continuing. Include happy paths, invalid inputs, deterministic behavior, and integration boundaries where relevant. Documentation-only changes require review, not invented or unnecessary runtime tests.

- Pay special attention to **Parquet serialization/round trips** (event IDs, schema, timestamps, time zones, and event counts), event identity and timestamp handling, pattern reproducibility, **model-specific box conversions and processor transformations**, annotation/coordinate accuracy, split leakage, and cache validity.

- Keep normal tests fast, deterministic, offline, and CPU-only. **Small synthetic event logs, Dotted Charts, and expected annotations under `tests/fixtures/` may be tracked in Git**; large datasets and generated experimental outputs must not be. Use temporary directories and mocks for network, large models, GPU inference, and downloads.

- Prefer non-mutating verification when reviewing changes, if tools are installed:

```bash
ruff format --check .
ruff check .
python -m pytest
```

- Inspect the actual `makefile`/`Makefile` before invoking targets: some targets apply fixes or formatting and modify files. Review `git diff` afterward. Never claim a check passed unless it actually ran successfully.

## Documentation, Git, and execution safeguards

- Create a **new, separate Markdown change log** in `docs/change_logs/` for each **meaningful completed logical change** to code, tests, CLI, dependencies, configuration, data contracts, or architecture. **Minor editorial documentation edits** (typos, wording, formatting, small link fixes) do not require a separate log; substantial technical documentation changes do. Do not use the shared Project Log as an agent change log.

- A logical change may touch several files: write **one log per cohesive change**, not one per file. For independent changes, use separate entries. Read-only analysis does not require an entry, and creating the entry does not itself trigger another entry.

- Name entries `YYYY-MM-DDTHH-MM-SSZ_<short-kebab-case-summary>.md` with the **UTC completion timestamp**. Do not overwrite an existing entry; append a unique suffix if needed.

- Each entry must briefly document **what changed, why, affected files/modules, checks and results** (including checks not run), and **known limitations/follow-ups**. Preserve old entries as an audit trail; never fabricate test results.

- Update the relevant README, implementation plan, or technical documentation when data contracts, CLIs, public APIs, or experimentally important assumptions change. Distinguish planned features from implemented ones.

- **GitHub Issues** are currently the source of truth for task assignments, status, technical discussion, and detailed findings. Reference relevant Issues and PRs where available; if the repository is moved to GitLab, use its Issues and Merge Requests instead. The **Project Log** (in the team wiki or its designated location) is maintained at team meetings for research conclusions and decisions, **not** for per-commit activity or agent change logs.

- Follow existing GitHub Issue, branch, pull-request, and Conventional Commit conventions. Do not commit, push, switch branches, or rewrite Git history unless explicitly requested.

- Do not commit raw or derived research datasets, bulk generated charts/annotations, model weights, checkpoints, large outputs, or credentials. **Small, non-sensitive test fixtures and expected annotation examples in `tests/` are explicitly allowed.** Respect `.gitignore` and preserve tracked `.gitkeep` placeholders.

- Do not edit source event logs, delete user data, fetch large datasets or checkpoints, or launch expensive GPU/full-dataset work without clear authorization.

- After each change, concisely report what changed, why, which checks ran and passed/failed, and any remaining limitations or assumptions.