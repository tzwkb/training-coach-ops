# Training Coach Ops

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Agent Skill](https://img.shields.io/badge/Agent%20Skill-Codex-blue.svg)](SKILL.md)
[![Python](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org/)

English | [中文](README_ZH.md)

**Agent Skill** — Multi-client strength and conditioning operations with structured profiles, versioned training plans, daily feedback, weekly reviews, and safety-gated adjustments.

## What It Does

- Creates isolated profiles and plans for multiple clients.
- Preserves raw daily feedback in an append-only fact log.
- Resolves clients by ID, display name, or alias and stops on ambiguity.
- Calculates weekly weight, adherence, training-volume, recovery, and pain signals.
- Renders daily coaching messages and weekly review documents.
- Versions plan changes and requires approval for high-risk adjustments.
- Validates workspace integrity after migrations or bulk operations.

## Safety Boundary

This skill supports general training and lifestyle management. It does not diagnose conditions, change medication, or prescribe injury rehabilitation. Pain and urgent warning signs stop automated progression and require appropriate human or professional review. See [references/safety-boundaries.md](references/safety-boundaries.md).

## Architecture

The reusable skill and the client-data workspace are deliberately separate:

- This repository contains workflow instructions, scripts, references, templates, and generic tests.
- A workspace contains private client profiles, plans, raw feedback, logs, reviews, and exports.
- The skill never stores the last-used workspace and does not include example client data.

Workspace resolution happens only when a workflow runs: an explicit absolute path, then a current directory containing `clients/index.json`, then `TRAINING_COACH_WORKSPACE`, and finally one user prompt.

## Structure

```text
training-coach-ops/
├── SKILL.md
├── agents/openai.yaml
├── assets/templates/
├── references/
├── scripts/
└── tests/
```

## Installation

Clone the repository into your agent skills directory:

```bash
git clone https://github.com/tzwkb/training-coach-ops.git ~/.codex/skills/training-coach-ops
```

For agents using the shared skills convention:

```bash
git clone https://github.com/tzwkb/training-coach-ops.git ~/.config/agents/skills/training-coach-ops
```

The runtime uses only the Python standard library.

## Typical Requests

- “Create a profile and initial plan for a new client.”
- “Import today's feedback and preserve the original message.”
- “Generate this client's daily coaching message.”
- “Review the last week and identify data gaps or safety signals.”
- “Prepare a plan adjustment and show which changes require approval.”

The agent routes these requests through the `onboard`, `ingest`, `daily`, `weekly-review`, `adjust-plan`, and `validate` workflows defined in [SKILL.md](SKILL.md).

## Validation

Run the full regression suite from the repository root:

```bash
PYTHONPATH=scripts python3 -m unittest discover -s tests -v
```

Validate the Skill package with the Codex `skill-creator` validator when available:

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```

## Privacy

Do not commit a training workspace, client profiles, raw feedback, logs, exports, credentials, or medical information to this repository. Keep those in a separate private location and pass its absolute path only at execution time.

## License

MIT
