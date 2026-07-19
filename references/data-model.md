# 数据模型

## 事实源

- `clients/index.json`：学员 ID、显示名、别名、状态和目录。
- `clients/<id>/profile.json`：稳定档案和当前状态。
- `clients/<id>/plans/current.json`：唯一生效计划。
- `clients/<id>/plans/archive/`：只读历史版本。
- `clients/<id>/logs/daily.jsonl`：只追加的每日事实记录。
- `reviews/` 和 `exports/`：可重新生成的分析与交付物，不是事实源。

## 确认状态

- `confirmed`：用户、教练或明确来源直接提供。
- `inferred`：根据上下文推断，仍需保留来源。
- `needs_review`：信息矛盾、不完整或解析不确定。

同日同字段合并时使用 `confirmed > inferred > needs_review`；同级取 `recorded_at` 较晚记录。永远保留原始行。

## 每日记录

必填字段：`record_id`、`client_id`、`date`、带时区的 `recorded_at`、`source`、`confidence`、`metrics`。

可用指标包括体重、腰臀围、训练是否计划及完成、饮食执行率、步数、睡眠、疲劳、疼痛、生理状态、动作工作组和安全事件。没有提供的字段保持缺失或 `null`，不能写成零。

动作工作组建议结构：

```json
{
  "exercise_id": "mon-goblet-squat",
  "category": "compound",
  "rep_range": [8, 12],
  "sets": [
    {"weight_kg": 20, "reps": 12, "rpe": 8, "qualified": true}
  ]
}
```

`qualified` 表示动作质量达到计划标准，不表示医学安全认证。
