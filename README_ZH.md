# Training Coach Ops

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Agent Skill](https://img.shields.io/badge/Agent%20Skill-Codex-blue.svg)](SKILL.md)
[![Python](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org/)

[English](README.md) | 中文

**Agent Skill** — 面向多学员的体能与力量训练运营流程，覆盖结构化建档、训练计划版本管理、每日反馈、周度复盘和带安全审批的计划调整。

## 能做什么

- 为多个学员建立相互隔离的档案和计划。
- 以只追加事实日志保留每日反馈和原始来源。
- 按 ID、姓名或别名解析学员，出现歧义时停止。
- 分析周体重、执行率、训练量、恢复情况和疼痛信号。
- 生成每日教练发送内容和周度复盘。
- 对计划调整进行版本控制，高风险变化必须审批。
- 在迁移或批量操作后校验工作区完整性。

## 安全边界

本 Skill 只支持一般训练和生活方式管理，不诊断、不调整处方药、不制定伤病康复处方。疼痛或紧急风险信号会停止自动进阶，并要求教练、医疗或其他适当专业人员复核。详见 [references/safety-boundaries.md](references/safety-boundaries.md)。

## 架构

Skill 与学员数据工作区有意解耦：

- 本仓库只保存通用工作流、脚本、参考规则、模板和测试。
- 工作区保存私有的学员档案、计划、原始反馈、日志、复盘和导出文件。
- Skill 不记录最近使用的工作区，也不包含示例学员数据。

工作流执行时才解析工作区：用户提供的绝对路径 → 当前目录中的 `clients/index.json` → `TRAINING_COACH_WORKSPACE` → 最后询问一次。

## 目录结构

```text
training-coach-ops/
├── SKILL.md
├── agents/openai.yaml
├── assets/templates/
├── references/
├── scripts/
└── tests/
```

## 安装

克隆到 Codex Skill 目录：

```bash
git clone https://github.com/tzwkb/training-coach-ops.git ~/.codex/skills/training-coach-ops
```

使用共享 Agent Skills 目录约定时：

```bash
git clone https://github.com/tzwkb/training-coach-ops.git ~/.config/agents/skills/training-coach-ops
```

运行时只依赖 Python 标准库。

## 典型请求

- “给新学员建档并生成首个计划。”
- “导入今天的反馈，并保留原始消息。”
- “生成这个学员今天的教练发送内容。”
- “复盘最近一周，列出数据缺口和安全信号。”
- “准备计划调整，并说明哪些变化需要审批。”

Agent 会按照 [SKILL.md](SKILL.md) 中定义的 `onboard`、`ingest`、`daily`、`weekly-review`、`adjust-plan` 和 `validate` 工作流处理。

## 验证

在仓库根目录运行完整回归测试：

```bash
PYTHONPATH=scripts python3 -m unittest discover -s tests -v
```

本机存在 Codex `skill-creator` 时，可继续校验 Skill 包：

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```

## 隐私

不要把训练工作区、学员档案、原始反馈、日志、导出文件、凭据或医疗信息提交到本仓库。应将这些数据保存在独立的私有位置，仅在执行任务时传入绝对路径。

## 许可证

MIT
