---
name: training-coach-ops
description: Use when managing multiple strength and conditioning clients, including onboarding, creating or updating a training plan, ingesting daily feedback, analyzing training trends, producing daily coaching messages or weekly reviews, and proposing evidence-based plan adjustments.
---

# Training Coach Ops

以结构化数据为事实源，使用脚本执行脆弱的写入、计算、版本和验证操作。不要把通用健身知识重复写入工作区。

## 解析工作区

不要在 Skill 加载时询问工作区。仅在执行具体工作流时按以下顺序解析：

1. 使用用户明确提供的绝对路径。
2. 否则使用当前目录包含 `clients/index.json` 的工作区。
3. 否则检查 `TRAINING_COACH_WORKSPACE` 指向的绝对目录。
4. 仍无法确定时，最后才询问用户一次。

选定后验证目录和 `clients/index.json`。显式路径无效时停止，不静默回退。不要把最近使用路径保存到 Skill 目录。

## 操作原则

1. 使用绝对工作区路径；不假定当前目录。
2. 先解析唯一学员，再读取或写入该学员目录。姓名或别名歧义时停止。
3. 只加载目标学员的档案、当前计划和完成任务所需的近期日志。
4. 保留原始反馈；未知信息写为 `null`，推断信息标记 `inferred` 或 `needs_review`。
5. 通过脚本追加日志、激活计划和生成报告。不要直接编辑 `daily.jsonl` 或覆盖 `current.json`。
6. 高风险调整需要批准。不要删除学员、日志、归档计划或原始来源。
7. 医学安全、疼痛、营养、恢复、训练处方或数值阈值相关结论必须通过主动联网检索核对权威来源；没有适用证据时不得自动执行。

开始前按任务读取：

- 字段、事实源或反馈解析：读 [references/data-model.md](references/data-model.md)。
- 自动进阶或计划变更：读 [references/adjustment-policy.md](references/adjustment-policy.md)。
- 疼痛、异常恢复或医疗边界：读 [references/safety-boundaries.md](references/safety-boundaries.md)。
- 生成训练、营养、恢复或安全建议：读权威证据政策 [references/evidence-policy.md](references/evidence-policy.md)。

## 权威证据门禁

涉及计划生成或修改、疼痛与恢复判断、营养建议、医学安全或任何精确阈值时，必须按 `evidence-policy.md` 主动检索、打开并核对直接来源。报告结论时同时给出适用人群、证据层级、直接链接和局限；来源不适用于当前学员时不得套用。单纯保存用户事实、解析路径、版本控制和确定性计算不需要科学文献。

## 工作流路由

### `onboard`

用于新学员建档和首个计划。

1. 运行 `scripts/client.py list --workspace <absolute-workspace>`，检查重复姓名和别名。
2. 读取数据模型，只收集完成首个计划所需的最少事实。
3. 将待确认档案写入临时 JSON，然后运行：

```bash
python3 <skill-dir>/scripts/client.py create --workspace <absolute-workspace> --id <client-id> --name <display-name> --profile <profile-json>
```

4. 按权威证据政策主动检索候选计划中的训练、营养和安全依据，记录适用人群、来源及局限。
5. 生成候选计划，先运行 `scripts/plan.py validate`。得到教练批准后，以 `--expected-version 0 --approved` 激活。

### `ingest`

用于聊天、表格或手工每日反馈。

1. 运行 `scripts/client.py get` 解析唯一学员。
2. 保留原始文本或源文件，只转换明确字段；不要把缺失记录当作未执行。
3. 生成符合数据模型的记录 JSON，然后运行：

```bash
python3 <skill-dir>/scripts/ingest.py --workspace <absolute-workspace> --client <client-id> --record <record-json> --raw <source-file>
```

4. 报告已写入字段、待复核字段和拒绝原因。不要静默修正非法数据。

### `daily`

用于生成教练当天发送内容。

1. 解析唯一学员并确认当前计划在有效日期内。
2. 运行：

```bash
python3 <skill-dir>/scripts/render.py daily --workspace <absolute-workspace> --client <client-id> --date <YYYY-MM-DD>
```

3. 若输出提示安全复核，不补充自行加量建议。

### `weekly-review`

用于周度趋势和下一步建议。

1. 运行 `scripts/analyze.py --workspace <absolute-workspace> --client <client-id> --end-date <YYYY-MM-DD>`。
2. 区分事实、数据缺口、解释和建议；不从缺失数据推断不执行。
3. 新增训练、恢复、营养或安全解释前，按权威证据政策主动联网核对；没有适用证据时标记 `needs_review`。
4. 运行 `scripts/render.py weekly` 保存周报。

### `adjust-plan`

用于进阶、减量或更改周期。

1. 读取调整政策和安全边界。
2. 主动联网检索并打开与拟调整内容直接相关的权威来源；记录来源、适用人群、证据层级和局限。
3. 从当前计划复制候选版本，只修改有适用证据支持的字段，并写明 `change_summary`；证据不足时不得伪造精确数字或自动调整。
4. 运行 `scripts/plan.py validate`。
5. 低风险进阶可按既定规则激活。热量、总组数、有氧总量、疼痛动作替换或周期阶段变化必须先取得教练批准，再运行：

```bash
python3 <skill-dir>/scripts/plan.py activate --workspace <absolute-workspace> --client <client-id> --candidate <candidate-json> --expected-version <current-version> --approved
```

6. 报告版本、差异、权威来源、适用性、局限和下一次复查条件。

### `validate`

用于迁移后、批量操作后或交付前检查。

```bash
python3 <skill-dir>/scripts/validate.py --workspace <absolute-workspace>
```

退出码非零或 `ok: false` 时停止后续写入，先修复具体错误。警告不等于错误，但必须在交付摘要中列出。
