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


def _week_number(plan: dict[str, Any], target_date: date) -> tuple[int, int]:
    start = date.fromisoformat(plan["effective_from"])
    end = date.fromisoformat(plan["effective_to"])
    if target_date < start or target_date > end:
        raise ValueError("target date outside current plan")
    day_index = (target_date - start).days
    return day_index // 7 + 1, day_index


def _weekly_value(mapping: Any, week: int, default: Any = None) -> Any:
    if not isinstance(mapping, dict):
        return default
    exact = mapping.get(str(week))
    if exact is not None:
        return exact
    for key, value in mapping.items():
        if not isinstance(key, str) or "-" not in key:
            continue
        start_text, end_text = key.split("-", 1)
        try:
            if int(start_text) <= week <= int(end_text):
                return value
        except ValueError:
            continue
    return default


def _phase_name(plan: dict[str, Any], week: int) -> str | None:
    for block in plan.get("phase", {}).get("blocks", []):
        weeks = block.get("weeks")
        if isinstance(weeks, list) and len(weeks) == 2 and weeks[0] <= week <= weeks[1]:
            return block.get("name")
    return plan.get("phase", {}).get("name")


def _adjusted_sets(plan: dict[str, Any], week: int, base_sets: int) -> int:
    progression = plan.get("progression", {})
    if week == 1:
        return min(base_sets, int(progression.get("week_1_set_cap", base_sets)))
    if week == progression.get("deload_week"):
        return max(1, base_sets - int(progression.get("deload_set_subtract", 1)))
    return base_sets


def _range_text(value: Any, suffix: str) -> str:
    if isinstance(value, list) and len(value) == 2:
        return f"{value[0]}–{value[1]}{suffix}"
    return f"{_format_value(value)}{suffix}"


def _workout_line(plan: dict[str, Any], workout: dict[str, Any], week: int) -> str:
    name = workout.get("name", workout["id"])
    duration_by_week = workout.get("duration_by_week")
    duration_minutes = _weekly_value(duration_by_week, week, workout.get("duration_minutes"))
    rpe = workout.get("rpe")
    if rpe is None:
        rpe = _weekly_value(plan.get("progression", {}).get("weekly_rpe"), week)
    if duration_minutes is not None:
        line = f"{name}：{_range_text(duration_minutes, '分钟')}"
        return f"{line}，RPE {_format_value(rpe)}" if rpe is not None else line
    if workout.get("duration_seconds") is not None:
        rep_text = _range_text(workout["duration_seconds"], "秒")
    elif workout.get("reps_text"):
        rep_text = workout["reps_text"]
    else:
        rep_text = _range_text(workout.get("reps"), "次")
    sets = _adjusted_sets(plan, week, int(workout.get("sets", 0)))
    rest = workout.get("rest_seconds")
    line = f"{name}：{sets}组×{rep_text}，RPE {_format_value(rpe)}"
    return f"{line}，休{rest}秒" if rest else line


def _finisher_line(finisher: dict[str, Any]) -> str:
    name = finisher.get("name", finisher.get("type", "收尾"))
    minutes = finisher.get("duration_minutes", finisher.get("minutes"))
    line = f"{name}：{_range_text(minutes, '分钟')}"
    if finisher.get("pattern"):
        line += f"（{finisher['pattern']}）"
    return line


def render_daily(root: Path, client_query: str, target_date: date) -> Path:
    client = resolve_client(root, client_query)
    base = root.resolve() / client["directory"]
    plan = load_json(base / "plans/current.json")
    if plan["client_id"] != client["id"]:
        raise ValueError("client_id mismatch in current plan")
    week, day_index = _week_number(plan, target_date)
    day_name = target_date.strftime("%A").lower()
    day_plan = next((item for item in plan["schedule"] if item.get("day", "").lower() == day_name), None)
    analysis = analyze_week(root, client["id"], target_date)

    phase = _phase_name(plan, week)
    subtitle = f"第{week}周" + (f"｜{phase}" if phase else "")
    lines = [f"# {client['display_name']}｜{target_date.isoformat()} 教练发送", "", f"> {subtitle}", ""]
    if analysis["recommendation"] == "safety_review":
        lines.extend(["> 暂停常规加量：存在疼痛或安全信号，需要教练复核。", ""])
    lines.append("## 今日训练")
    if day_plan is None or day_plan.get("type") == "rest":
        lines.append("休息或按计划进行轻松活动，不补做漏课。")
    else:
        lines.append(day_plan.get("title") or day_plan.get("type", "训练"))
        lines.append("")
        if day_plan.get("warmup"):
            lines.append(day_plan["warmup"])
            lines.append("")
        for workout in day_plan.get("workouts", []):
            lines.append(f"- {_workout_line(plan, workout, week)}")
        if day_plan.get("finisher"):
            lines.append(f"- {_finisher_line(day_plan['finisher'])}")
    nutrition = plan.get("nutrition", {})
    meals = nutrition.get("meal_cycle", [])
    meal = meals[day_index % len(meals)] if meals else None
    targets = plan.get("daily_targets", {})
    steps = _weekly_value(targets.get("steps"), week)
    lines.extend(
        [
            "",
            "## 今日饮食",
            f"- 热量：{_format_value(nutrition.get('calories'))} kcal",
            f"- 蛋白质：{_format_value(nutrition.get('protein_g'))} g",
        ]
    )
    if meal:
        lines.extend([
            f"- 早餐：{meal.get('breakfast', '无数据')}",
            f"- 午餐：{meal.get('lunch', '无数据')}",
            f"- 加餐：{meal.get('snack', '无数据')}",
            f"- 晚餐：{meal.get('dinner', '无数据')}",
        ])
    lines.extend([
        "",
        "## 活动与恢复",
        f"- 步数：{_format_value(steps)}",
        f"- 饮水：{_format_value(targets.get('water'))}",
        f"- 睡眠：{_format_value(targets.get('sleep'))}",
        "- 完成后记录重量、次数、RPE、睡眠和疼痛评分。",
        "",
        "## 安全提醒",
        "出现胸痛、晕厥或严重呼吸困难时立即停止并寻求紧急医疗帮助；关节锐痛、麻木或放射痛需要教练复核。",
        "",
    ])
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
