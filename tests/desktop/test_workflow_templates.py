from __future__ import annotations

import tempfile
from pathlib import Path

from maref.desktop.workflow_templates import (
    WORKFLOW_TEMPLATES,
    WorkflowCategory,
    WorkflowExecutor,
    WorkflowStep,
    WorkflowTemplate,
)


class TestWorkflowStep:
    def test_to_dict(self) -> None:
        step = WorkflowStep(
            action_type="click",
            action_value="100,200",
            wait_seconds=0.5,
            expected_app="Finder",
        )
        d = step.to_dict()
        assert d["action_type"] == "click"
        assert d["wait_seconds"] == 0.5


class TestWorkflowTemplate:
    def test_to_dict(self) -> None:
        step = WorkflowStep(action_type="click", action_value="100,200")
        template = WorkflowTemplate(
            name="test_template",
            category=WorkflowCategory.OFFICE,
            description="A test template",
            steps=[step],
            safe_apps=["Finder"],
            tags=["test"],
        )
        d = template.to_dict()
        assert d["name"] == "test_template"
        assert d["category"] == "office"
        assert len(d["steps"]) == 1
        assert len(d["steps"]) == 1


class TestWorkflowTemplates:
    def test_default_templates_exist(self) -> None:
        assert len(WORKFLOW_TEMPLATES) >= 5
        assert "compose_email" in WORKFLOW_TEMPLATES
        assert "terminal_command" in WORKFLOW_TEMPLATES

    def test_template_categories(self) -> None:
        cats = {t.category for t in WORKFLOW_TEMPLATES.values()}
        assert WorkflowCategory.EMAIL in cats
        assert WorkflowCategory.BROWSER in cats

    def test_templates_have_steps(self) -> None:
        for name, template in WORKFLOW_TEMPLATES.items():
            assert template.name == name
            assert len(template.steps) > 0
            assert all(isinstance(s, WorkflowStep) for s in template.steps)


class TestWorkflowExecutor:
    def test_list_templates(self) -> None:
        executor = WorkflowExecutor()
        templates = executor.list_templates()
        assert len(templates) >= 5
        names = [t["name"] for t in templates]
        assert "compose_email" in names

    def test_get_template(self) -> None:
        executor = WorkflowExecutor()
        template = executor.get_template("browser_form")
        assert template is not None
        assert template.category == WorkflowCategory.BROWSER

    def test_get_template_unknown(self) -> None:
        executor = WorkflowExecutor()
        assert executor.get_template("nonexistent") is None

    def test_execute_without_agent(self) -> None:
        executor = WorkflowExecutor()
        result = executor.execute("compose_email")
        assert result["success"] is True
        assert result["total_steps"] > 0

    def test_execute_unknown_template(self) -> None:
        executor = WorkflowExecutor()
        result = executor.execute("nonexistent")
        assert result["success"] is False

    def test_save_and_load_template(self) -> None:
        executor = WorkflowExecutor()
        template = WorkflowTemplate(
            name="custom_test",
            category=WorkflowCategory.FILE,
            description="Custom test",
            steps=[WorkflowStep("click", "100,200")],
        )
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            path = f.name
        try:
            executor.save_template(template, path)
            loaded = executor.load_template(path)
            assert loaded is not None
            assert loaded.name == "custom_test"
            assert len(loaded.steps) == 1
        finally:
            Path(path).unlink(missing_ok=True)

    def test_load_template_invalid(self) -> None:
        executor = WorkflowExecutor()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            f.write("not json")
            path = f.name
        try:
            loaded = executor.load_template(path)
            assert loaded is None
        finally:
            Path(path).unlink(missing_ok=True)

    def test_load_template_file_not_found(self) -> None:
        executor = WorkflowExecutor()
        assert executor.load_template("/nonexistent/path/template.json") is None

    def test_execute_with_agent(self) -> None:
        class MockAgent:
            def execute_operation(self, action_type: str, action_value: str) -> None:
                pass

        executor = WorkflowExecutor(agent=MockAgent())
        result = executor.execute("compose_email")
        assert result["success"] is True
        assert result["total_steps"] > 0

    def test_execute_with_agent_error_skip_on_error(self) -> None:
        class FailingAgent:
            def execute_operation(self, action_type: str, action_value: str) -> None:
                raise RuntimeError("operation failed")

        executor = WorkflowExecutor(agent=FailingAgent())
        custom_template = WorkflowTemplate(
            name="fail_template",
            category=WorkflowCategory.FILE,
            description="Failing test",
            steps=[
                WorkflowStep("click", "100,200", wait_seconds=0.1, skip_on_error=True),
                WorkflowStep("type", "hello", wait_seconds=0.1),
            ],
        )
        from maref.desktop.workflow_templates import WORKFLOW_TEMPLATES
        WORKFLOW_TEMPLATES["fail_template"] = custom_template
        try:
            result = executor.execute("fail_template")
            assert result["success"] is False
            assert len(result["step_results"]) == 2
        finally:
            WORKFLOW_TEMPLATES.pop("fail_template", None)

    def test_save_template_creates_dirs(self) -> None:
        executor = WorkflowExecutor()
        with tempfile.TemporaryDirectory() as td:
            nested = Path(td) / "a" / "b" / "template.json"
            template = WorkflowTemplate(
                name="nested_test",
                category=WorkflowCategory.BROWSER,
                description="Nested path test",
                steps=[WorkflowStep("click", "x,y")],
            )
            executor.save_template(template, str(nested))
            assert nested.exists()
            loaded = executor.load_template(str(nested))
            assert loaded is not None
            assert loaded.name == "nested_test"
