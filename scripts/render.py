from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from analyze import analyze_week
from client import resolve_client
from common import atomic_write_text, load_json


def _format_value(value: Any) -> str:
    if value is None:
        return "无数据"
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, list):
        if len(value) == 2 and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
            return f"{value[0]}–{value[1]}"
        return "、".join(str(item) for item in value) if value else "无"
    return str(value)


def render_daily(root: Path, client_query: str, target_date: date) -> Path:
    client = resolve_client(root, client_query)
    base = root.resolve() / client["directory"]
    plan = load_json(base / "plans/current.json")
    if plan["client_id"] != client["id"]:
        raise ValueError("client_id mismatch in current plan")
    day_name = target_date.strftime("%A").lower()
    day_plan = next((item for item in plan["schedule"] if item.get("day", "").lower() == day_name), None)
    analysis = analyze_week(root, client["id"], target_date)

    lines = [f"# {client['display_name']}｜{target_date.isoformat()} 教练发送", ""]
    if analysis["recommendation"] == "safety_review":
        lines.extend(["> 暂停常规加量：存在疼痛或安全信号，需要教练复核。", ""])
    lines.append("## 今日训练")
    if day_plan is None or day_plan.get("type") == "rest":
        lines.append("休息或按计划进行轻松活动，不补做漏课。")
    else:
        lines.append(day_plan.get("title") or day_plan.get("type", "训练"))
        lines.append("")
        for workout in day_plan.get("workouts", []):
            reps = workout.get("reps")
            rep_text = f"{reps[0]}–{reps[1]}" if isinstance(reps, list) and len(reps) == 2 else _format_value(reps)
            lines.append(
                f"- {workout.get('name', workout['id'])}：{workout.get('sets', 0)} 组 × {rep_text} 次，"
                f"RPE {_format_value(workout.get('rpe'))}，休息 {_format_value(workout.get('rest_seconds'))} 秒"
            )
    nutrition = plan.get("nutrition", {})
    lines.extend(
        [
            "",
            "## 饮食框架",
            f"- 热量：{_format_value(nutrition.get('calories'))} kcal",
            f"- 蛋白质：{_format_value(nutrition.get('protein_g'))} g",
            "",
            "## 活动与恢复",
            f"- 周有氧目标：{_format_value(plan.get('cardio', {}).get('weekly_minutes'))} 分钟",
            "- 完成后记录重量、次数、RPE、睡眠和疼痛评分。",
            "",
            "## 安全提醒",
            "出现胸痛、晕厥或严重呼吸困难时立即停止并寻求紧急医疗帮助；关节锐痛、麻木或放射痛需要教练复核。",
            "",
        ]
    )
    output = base / "exports/daily" / f"{target_date.isoformat()}.md"
    atomic_write_text(output, "\n".join(lines))
    return output


def render_weekly(root: Path, client_query: str, end_date: date) -> Path:
    client = resolve_client(root, client_query)
    base = root.resolve() / client["directory"]
    analysis = analyze_week(root, client["id"], end_date)
    flags = analysis["flags"]
    lines = [
        f"# {client['display_name']}｜截至 {end_date.isoformat()} 周报",
        "",
        "## 事实",
        f"- 七日平均体重：{_format_value(analysis['weight']['average_kg'])} kg",
        f"- 体重记录天数：{analysis['weight']['days_present']}/7",
        f"- 训练完成率：{_format_value(analysis['adherence']['training_rate'])}",
        f"- 训练记录覆盖率：{_format_value(analysis['adherence']['training_coverage'])}",
        f"- 平均睡眠：{_format_value(analysis['recovery']['average_sleep_hours'])} 小时",
        f"- 最大疼痛：{_format_value(analysis['recovery']['max_pain'])}/10",
        "",
        "## 数据缺口",
    ]
    if "insufficient_data" in flags:
        lines.append("- 数据不足：本周有效体重记录少于 4 天，不能据此判断体重趋势。")
    else:
        lines.append("- 未发现影响当前趋势判断的主要缺口。")
    lines.extend(
        [
            "",
            "## 解释",
            f"- 标记：{_format_value(flags)}",
            "",
            "## 建议",
            f"- 当前建议：{analysis['recommendation']}",
            "",
            "## 需审批项",
            "- 涉及热量、周训练量、有氧总量、疼痛动作替换或周期重构时，等待教练批准。",
            "",
            "## 下次复查",
            "- 补齐下一周记录后重新计算；异常安全信号不等待周末。",
            "",
        ]
    )
    output = base / "reviews/weekly" / f"{end_date.isoformat()}.md"
    atomic_write_text(output, "\n".join(lines))
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("daily", "weekly"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--workspace", required=True, type=Path)
        subparser.add_argument("--client", required=True)
        subparser.add_argument("--date", required=True, type=date.fromisoformat)
    args = parser.parse_args()
    try:
        output = (
            render_daily(args.workspace, args.client, args.date)
            if args.command == "daily"
            else render_weekly(args.workspace, args.client, args.date)
        )
    except (KeyError, OSError, TypeError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps({"output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
