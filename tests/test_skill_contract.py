import re
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


class SkillContractTests(unittest.TestCase):
    def setUp(self):
        self.text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    def test_frontmatter_has_name_and_trigger_terms(self):
        match = re.match(r"^---\n(.*?)\n---", self.text, re.DOTALL)
        self.assertIsNotNone(match)
        frontmatter = match.group(1)
        self.assertIn("name: training-coach-ops", frontmatter)
        for term in ("multiple", "training plan", "daily feedback", "weekly reviews", "plan adjustments"):
            self.assertIn(term, frontmatter)
        description = next(line for line in frontmatter.splitlines() if line.startswith("description: "))
        self.assertTrue(description.startswith("description: Use when "))
        self.assertIsNone(re.search(r"[\u4e00-\u9fff]", description))
        self.assertNotIn("TODO", frontmatter)

    def test_body_routes_all_supported_workflows(self):
        for route in ("onboard", "ingest", "daily", "weekly-review", "adjust-plan", "validate"):
            self.assertIn(f"`{route}`", self.text)

    def test_body_references_resources_and_guardrails(self):
        for reference in ("data-model.md", "adjustment-policy.md", "safety-boundaries.md", "evidence-policy.md"):
            self.assertIn(reference, self.text)
            self.assertTrue((SKILL_ROOT / "references" / reference).exists())
        for script in ("client.py", "ingest.py", "analyze.py", "plan.py", "render.py", "validate.py"):
            self.assertIn(script, self.text)
        self.assertIn("先解析唯一学员", self.text)
        self.assertIn("高风险调整需要批准", self.text)
        self.assertNotIn("TODO", self.text)

    def test_scientific_claims_require_proactive_authoritative_web_research(self):
        evidence = (SKILL_ROOT / "references/evidence-policy.md").read_text(encoding="utf-8")
        required = (
            "必须主动联网检索",
            "医学与安全",
            "训练与表现",
            "营养与体成分",
            "数值阈值",
            "适用人群",
            "直接页面",
            "不得伪造精确数字",
        )
        for value in required:
            self.assertIn(value, evidence)
        self.assertIn("权威证据政策", self.text)
        self.assertIn("evidence-policy.md", self.text)

    def test_openai_metadata_mentions_skill(self):
        metadata = (SKILL_ROOT / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertIn("$training-coach-ops", metadata)

    def test_skill_tree_has_no_live_workspace_coupling(self):
        forbidden = ("/Users/spellbook/Desktop/Training Plans", "Li Zenuo", "李泽诺", "McCain")
        for path in SKILL_ROOT.rglob("*"):
            if not path.is_file() or path == Path(__file__) or path.suffix not in {".py", ".md", ".yaml"}:
                continue
            text = path.read_text(encoding="utf-8")
            for value in forbidden:
                self.assertNotIn(value, text, path)

    def test_workspace_resolution_is_lazy_and_ordered(self):
        required = (
            "不要在 Skill 加载时询问工作区",
            "用户明确提供的绝对路径",
            "当前目录包含 `clients/index.json`",
            "`TRAINING_COACH_WORKSPACE`",
            "最后才询问用户",
            "不静默回退",
        )
        for value in required:
            self.assertIn(value, self.text)
        positions = [self.text.index(value) for value in required]
        self.assertEqual(positions, sorted(positions))


if __name__ == "__main__":
    unittest.main()
