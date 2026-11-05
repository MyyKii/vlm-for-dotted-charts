# Project Log — VLM-Based Visual Pattern Detection in Dotted Charts

**LMU Munich · Winter Semester 2026/27**

The [technical blueprint](blueprint.md) describes the intended research approach and architecture. **This log records what actually happened:** individual contributions, experimental findings, problems, team decisions, and the work agreed for the next meeting. It grows chronologically and serves as the source for university status updates.

## How We Use This Log

**One meeting = one work cycle.** The newest meeting is always at the bottom of the file. Its **last section is the task list for the next meeting**.

| When | Who | What to update |
| --- | --- | --- |
| **During a team meeting** | One note-taker, with team agreement | Add a new dated meeting entry at the bottom. Record decisions, their reasoning, problems requiring team input, and **assigned tasks at the very end**. |
| **Between meetings** | Each team member | Add a dated row under **Individual Work Updates** in the *latest meeting entry*, directly **above** its task list. Record concrete results and evidence; update the status of your assigned task. |
| **At the next meeting** | Everyone | Scroll to the bottom: review the previous meeting's tasks and the individual updates immediately above them. Discuss unresolved issues, then append the next meeting entry with new decisions and tasks. |
| **For university status updates** | Whoever presents | Use recent individual results, meeting decisions, challenges, and the latest task list. No additional status-summary section is required. |

**Keep it lightweight:** One row per meaningful result is enough. Link to commits, PRs, files, or experiment outputs instead of copying technical details. Do not rewrite old decisions; document changes and their reasons in the next meeting entry. Task owners may update **only the status** of previously assigned tasks as work progresses.

**Task status:** `Todo` · `In progress` · `Blocked` · `Done`. **Decision status:** `Decided` · `Open` · `Revisit`. Use stable references such as `T-01` (task) and `D-01` (decision).

## Template — New Meeting Entry

*Copy the following block to the **end of the Meeting History** when a new meeting starts. Keep the task table as the final section. Individual contributors add rows to the update table between meetings.*

```markdown
### YYYY-MM-DD — Meeting Title

**Participants:** …
**Note-taker:** …

#### Decisions and Reasoning

| ID | Topic | Decision / current conclusion | Reasoning / evidence | Status |
| --- | --- | --- | --- | --- |
| D-XX | … | … | … | Decided / Open / Revisit |

#### Problems and Open Questions (if relevant)

| Problem / question | What was tried or discussed | Result / next investigation |
| --- | --- | --- |
| … | … | … |

#### Individual Work Updates — Until the Next Meeting

*Each person adds a dated row here as work is completed. State what was learned or produced, not just what was attempted.*

| Date | Contributor | Task | Result / finding | Evidence | Blocker / next action |
| --- | --- | --- | --- | --- | --- |
| YYYY-MM-DD | … | T-XX | … | Commit / PR / file / experiment | … |

#### Tasks Until the Next Meeting

**Next meeting:** YYYY-MM-DD (or TBD)

| ID | Task / expected result | Owner | Due | Status |
| --- | --- | --- | --- | --- |
| T-XX | … | … | … | Todo |
```

---

## Meeting History

### 2026-11-06 — Initial Project Planning

**Status:** Meeting scheduled; no decisions or assignments confirmed yet.
**Participants:** To record
**Note-taker:** To assign

#### Decisions and Reasoning

*Use these initial questions as discussion prompts. They do **not** prescribe the outcome. Record the actual decision and why it was made, or leave it `Open` with a concrete follow-up task.*

| ID | Topic / questions to resolve | Decision / current conclusion | Reasoning / evidence | Status |
| --- | --- | --- | --- | --- |
| D-01 | **Datasets:** Which synthetic or real event logs should we start with? How will related chart variants stay in the same data split? | TBD | TBD | Open |
| D-02 | **Patterns and labeling:** Which first pattern(s)? Controlled injection, manual labeling, or hybrid? How do we validate bounding boxes, including ambiguous and negative examples? | TBD | TBD | Open |
| D-03 | **Training data:** Full charts, crops, or both? Multiple views of the same log? Should metadata, log data, plotting code, or explanation traces be included, and what risks ground-truth leakage? Have we found better approaches in the literature? | TBD | TBD | Open |
| D-04 | **Training and compute:** Which GPUs/clusters can we use? Who verifies access? What is the smallest zero-shot and QLoRA smoke test (initially Qwen2.5-VL-3B)? | TBD | TBD | Open |
| D-05 | **Evaluation and first milestone:** Which baselines and metrics are feasible? How will we assess localization ambiguity and generalization to real logs? What should the first end-to-end demonstration include? | TBD | TBD | Open |

#### Problems and Open Questions (if relevant)

*Add only problems that need a shared decision, investigation, or change in approach. Individual troubleshooting belongs in the work updates below.*

| Problem / question | What was tried or discussed | Result / next investigation |
| --- | --- | --- |
| — | — | — |

#### Individual Work Updates — Until the Next Meeting

*Each contributor adds updates **here**, above the task list, as work is completed. The first line captures the preparation already reported before the initial meeting; confirm its contributor and update the evidence when a commit or PR exists.*

| Date | Contributor | Task | Result / finding | Evidence | Blocker / next action |
| --- | --- | --- | --- | --- | --- |
| 2026-11-05 | To confirm | Project setup | Prepared repository structure, initial documentation, dependencies, and a proposed separation between source code (`src/`) and datasets/artifacts (`data/`). | `README.md`, `.gitignore`, `pyproject.toml`, `requirements.txt`, `docs/blueprint.md`; branch `chore/project-setup` | Team review and integration pending. |

#### Tasks Until the Next Meeting

**Next meeting:** TBD — agree on the date on 2026-11-06.
**The following tasks are suggestions, not commitments.** Confirm scope, owner, and deadline during the meeting; remove or replace anything that is not agreed.

| ID | Task / expected result | Owner | Due | Status |
| --- | --- | --- | --- | --- |
| T-01 | Compare candidate event logs and recommend a starting dataset and split strategy. | TBD | TBD | Proposed |
| T-02 | Propose one initial visual pattern and a checkable ground-truth annotation method. | TBD | TBD | Proposed |
| T-03 | Render one Dotted Chart and verify the annotation in final image coordinates. | TBD | TBD | Proposed |
| T-04 | Confirm GPU access and run a minimal Qwen2.5-VL zero-shot inference. | TBD | TBD | Proposed |
| T-05 | Investigate a minimal QLoRA training setup and document resource requirements. | TBD | TBD | Proposed |
