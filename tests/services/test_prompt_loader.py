"""Unit tests for PromptManager in app/services/prompt_loader.py."""

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound
from services.prompt_loader import PromptManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_prompt_manager_env():
    """Save and restore the PromptManager singleton env around every test.

    PromptManager._env is a class-level singleton.  Without this reset each
    test would share the same Jinja2 Environment, causing the temp-dir tests
    to interfere with one another.
    """
    original = PromptManager._env
    yield
    PromptManager._env = original


@pytest.fixture()
def prompt_dir(tmp_path):
    """Wire PromptManager to a temporary directory instead of app/prompts/.

    Creates an isolated Jinja2 Environment pointing at *tmp_path* and stores
    it as the PromptManager singleton so that test templates live entirely in
    the temporary directory and never touch real prompt files.
    """
    env = Environment(
        loader=FileSystemLoader(str(tmp_path)),
        undefined=StrictUndefined,
    )
    PromptManager._env = env
    return tmp_path


# ---------------------------------------------------------------------------
# get_prompt — basic rendering
# ---------------------------------------------------------------------------


class TestGetPromptRendering:
    def test_renders_single_variable(self, prompt_dir):
        """get_prompt substitutes a single variable into the template body."""
        (prompt_dir / "greeting.j2").write_text(
            "Hello, {{ name }}!", encoding="utf-8"
        )
        result = PromptManager.get_prompt("greeting", name="Alice")
        assert result == "Hello, Alice!"

    def test_renders_multiple_variables(self, prompt_dir):
        """get_prompt substitutes several variables in one render call."""
        (prompt_dir / "intro.j2").write_text(
            "{{ greeting }}, {{ first }}. Age: {{ age }}.", encoding="utf-8"
        )
        result = PromptManager.get_prompt(
            "intro", greeting="Hi", first="Bob", age=30
        )
        assert result == "Hi, Bob. Age: 30."

    def test_renders_template_with_no_variables(self, prompt_dir):
        """get_prompt returns the literal text when the template has no variables."""
        (prompt_dir / "static.j2").write_text(
            "Static content here.", encoding="utf-8"
        )
        result = PromptManager.get_prompt("static")
        assert result == "Static content here."

    def test_renders_multiline_template(self, prompt_dir):
        """get_prompt preserves newlines from the template body."""
        body = "Line one.\nLine two: {{ value }}.\nLine three."
        (prompt_dir / "multiline.j2").write_text(body, encoding="utf-8")
        result = PromptManager.get_prompt("multiline", value="inserted")
        assert "Line one." in result
        assert "Line two: inserted." in result
        assert "Line three." in result


# ---------------------------------------------------------------------------
# get_prompt — YAML frontmatter handling
# ---------------------------------------------------------------------------


class TestGetPromptFrontmatter:
    def test_body_only_is_returned_when_frontmatter_present(self, prompt_dir):
        """get_prompt returns only the body; YAML frontmatter is stripped."""
        content = "---\ndescription: A greeting\nauthor: Tester\n---\nHello, {{ name }}!"
        (prompt_dir / "fm_greeting.j2").write_text(content, encoding="utf-8")
        result = PromptManager.get_prompt("fm_greeting", name="Carol")
        assert result == "Hello, Carol!"

    def test_frontmatter_markers_are_not_in_output(self, prompt_dir):
        """The '---' delimiters from the YAML block do not appear in output."""
        content = "---\ntitle: Test\n---\nBody text."
        (prompt_dir / "markers.j2").write_text(content, encoding="utf-8")
        result = PromptManager.get_prompt("markers")
        assert "---" not in result
        assert result == "Body text."

    def test_frontmatter_keys_are_not_in_output(self, prompt_dir):
        """YAML keys like 'description' and 'author' do not appear in the rendered body."""
        content = "---\ndescription: Should not appear\nauthor: Ghost\n---\nOnly this."
        (prompt_dir / "fm_keys.j2").write_text(content, encoding="utf-8")
        result = PromptManager.get_prompt("fm_keys")
        assert "description" not in result
        assert "Ghost" not in result
        assert result == "Only this."


# ---------------------------------------------------------------------------
# get_prompt — error cases
# ---------------------------------------------------------------------------


class TestGetPromptErrors:
    def test_missing_template_raises_template_not_found(self, prompt_dir):
        """get_prompt raises TemplateNotFound for a template that does not exist."""
        with pytest.raises(TemplateNotFound):
            PromptManager.get_prompt("does_not_exist")

    def test_missing_required_variable_raises_value_error(self, prompt_dir):
        """get_prompt raises ValueError when a required variable is not supplied.

        PromptManager uses StrictUndefined so Jinja2 raises UndefinedError on
        access; the implementation catches TemplateError (parent of
        UndefinedError) and re-raises it as ValueError.
        """
        (prompt_dir / "strict.j2").write_text(
            "Hello, {{ name }}!", encoding="utf-8"
        )
        with pytest.raises(ValueError, match="Error rendering template"):
            PromptManager.get_prompt("strict")  # 'name' not supplied

    def test_missing_variable_error_is_not_silent_empty_string(self, prompt_dir):
        """An undefined variable never silently becomes an empty string.

        Confirms that StrictUndefined is configured — the silent-miss behaviour
        would return "Hello, !" instead of raising.
        """
        (prompt_dir / "silent_check.j2").write_text(
            "Value: {{ undefined_var }}", encoding="utf-8"
        )
        with pytest.raises(ValueError):
            result = PromptManager.get_prompt("silent_check")
            # If we reach here StrictUndefined was NOT configured — fail explicitly
            assert "undefined_var" not in result, (
                "Expected an error but got silent empty-string substitution"
            )


# ---------------------------------------------------------------------------
# get_template_info — metadata extraction
# ---------------------------------------------------------------------------


class TestGetTemplateInfo:
    def test_returns_name_matching_template_argument(self, prompt_dir):
        """get_template_info['name'] equals the template name passed in."""
        (prompt_dir / "simple.j2").write_text("Hello.", encoding="utf-8")
        info = PromptManager.get_template_info("simple")
        assert info["name"] == "simple"

    def test_parses_description_from_frontmatter(self, prompt_dir):
        """get_template_info extracts the 'description' YAML field."""
        content = "---\ndescription: My template\nauthor: Dev\n---\nHello."
        (prompt_dir / "meta.j2").write_text(content, encoding="utf-8")
        info = PromptManager.get_template_info("meta")
        assert info["description"] == "My template"

    def test_parses_author_from_frontmatter(self, prompt_dir):
        """get_template_info extracts the 'author' YAML field."""
        content = "---\ndescription: Desc\nauthor: Jane\n---\nHello."
        (prompt_dir / "author_meta.j2").write_text(content, encoding="utf-8")
        info = PromptManager.get_template_info("author_meta")
        assert info["author"] == "Jane"

    def test_returns_raw_frontmatter_dict(self, prompt_dir):
        """get_template_info exposes the full frontmatter dict under 'frontmatter'."""
        content = "---\ndescription: Full\nauthor: Lee\nextra: custom_value\n---\nBody."
        (prompt_dir / "full_fm.j2").write_text(content, encoding="utf-8")
        info = PromptManager.get_template_info("full_fm")
        assert info["frontmatter"]["extra"] == "custom_value"

    def test_default_description_when_frontmatter_absent(self, prompt_dir):
        """get_template_info returns 'No description provided' when key is missing."""
        (prompt_dir / "no_desc.j2").write_text("Body only.", encoding="utf-8")
        info = PromptManager.get_template_info("no_desc")
        assert info["description"] == "No description provided"

    def test_default_author_when_frontmatter_absent(self, prompt_dir):
        """get_template_info returns 'Unknown' when 'author' key is missing."""
        (prompt_dir / "no_author.j2").write_text("Body only.", encoding="utf-8")
        info = PromptManager.get_template_info("no_author")
        assert info["author"] == "Unknown"

    def test_lists_single_variable(self, prompt_dir):
        """get_template_info['variables'] contains the single undeclared variable."""
        (prompt_dir / "one_var.j2").write_text(
            "Hello, {{ name }}!", encoding="utf-8"
        )
        info = PromptManager.get_template_info("one_var")
        assert "name" in info["variables"]

    def test_lists_all_variables(self, prompt_dir):
        """get_template_info['variables'] contains every undeclared variable."""
        (prompt_dir / "multi_var.j2").write_text(
            "{{ greeting }}, {{ first_name }} {{ last_name }}!", encoding="utf-8"
        )
        info = PromptManager.get_template_info("multi_var")
        assert set(info["variables"]) == {"greeting", "first_name", "last_name"}

    def test_variables_empty_for_static_template(self, prompt_dir):
        """get_template_info['variables'] is empty for a template with no variables."""
        (prompt_dir / "no_vars.j2").write_text("Static text.", encoding="utf-8")
        info = PromptManager.get_template_info("no_vars")
        assert info["variables"] == []

    def test_missing_template_raises_template_not_found(self, prompt_dir):
        """get_template_info raises TemplateNotFound for a missing template file."""
        with pytest.raises(TemplateNotFound):
            PromptManager.get_template_info("nonexistent_template")
