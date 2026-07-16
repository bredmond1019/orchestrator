"""Unit tests for app/services/workspace_resolver.py (contract §3 semantics)."""

from pathlib import Path

import pytest
from services.workspace_resolver import (
    InvalidWorkspaceNameError,
    MalformedRegistryError,
    NoWorkspaceRegistryError,
    UnknownWorkspaceError,
    WorkspaceRegistry,
    load_registry,
    resolve_workspace_root,
    validate_workspace_name,
)

# ---------------------------------------------------------------------------
# validate_workspace_name
# ---------------------------------------------------------------------------


class TestValidateWorkspaceName:
    @pytest.mark.parametrize(
        "name",
        ["brain", "bastion", "client-a", "a1-b2", "x"],
    )
    def test_valid_names_pass(self, name):
        validate_workspace_name(name)  # no raise

    @pytest.mark.parametrize(
        "name",
        ["Brain", "client_a", "client a", "-leading", "trailing-", "double--hyphen", ""],
    )
    def test_invalid_names_raise(self, name):
        with pytest.raises(InvalidWorkspaceNameError):
            validate_workspace_name(name)


# ---------------------------------------------------------------------------
# load_registry
# ---------------------------------------------------------------------------


class TestLoadRegistry:
    def test_absent_file_returns_empty_registry(self, tmp_path):
        registry = load_registry(tmp_path / "does-not-exist" / "config.toml")
        assert registry.is_empty is True
        assert registry.workspaces == {}
        assert registry.default_workspace is None

    def test_unreadable_directory_returns_empty_registry(self, tmp_path):
        # Pointing the "file" path at a directory makes read_text() raise OSError.
        directory_as_file = tmp_path / "a_directory"
        directory_as_file.mkdir()
        registry = load_registry(directory_as_file)
        assert registry.is_empty is True
        assert registry.workspaces == {}

    def test_malformed_toml_raises(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text("this is not [ valid toml", encoding="utf-8")
        with pytest.raises(MalformedRegistryError):
            load_registry(config_path)

    def test_malformed_workspaces_shape_raises(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text('workspaces = "not-a-table"\n', encoding="utf-8")
        with pytest.raises(MalformedRegistryError):
            load_registry(config_path)

    def test_malformed_default_workspace_type_raises(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text("default_workspace = 5\n", encoding="utf-8")
        with pytest.raises(MalformedRegistryError):
            load_registry(config_path)

    def test_valid_registry_loads(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            'default_workspace = "brain"\n\n'
            "[workspaces]\n"
            'brain = "/home/user/agentic-portfolio"\n'
            'client-a = "/home/user/clients/client-a"\n',
            encoding="utf-8",
        )
        registry = load_registry(config_path)
        assert registry.is_empty is False
        assert registry.default_workspace == "brain"
        assert registry.workspaces == {
            "brain": "/home/user/agentic-portfolio",
            "client-a": "/home/user/clients/client-a",
        }

    def test_empty_workspaces_table_loads_as_present_but_empty(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text("[workspaces]\n", encoding="utf-8")
        registry = load_registry(config_path)
        assert registry.is_empty is False
        assert registry.workspaces == {}

    def test_default_path_derivation_uses_xdg_config_home(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        config_dir = tmp_path / "orchestrator"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text(
            "[workspaces]\nbrain = \"/x\"\n", encoding="utf-8"
        )
        registry = load_registry()
        assert registry.workspaces == {"brain": "/x"}

    def test_default_path_falls_back_to_home_dot_config(self, tmp_path, monkeypatch):
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config_dir = tmp_path / ".config" / "orchestrator"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text(
            "[workspaces]\nbrain = \"/y\"\n", encoding="utf-8"
        )
        registry = load_registry()
        assert registry.workspaces == {"brain": "/y"}


# ---------------------------------------------------------------------------
# resolve_workspace_root
# ---------------------------------------------------------------------------


class TestResolveWorkspaceRoot:
    def test_explicit_root_always_wins(self):
        registry = WorkspaceRegistry(
            workspaces={"brain": "/registry/brain"},
            default_workspace="brain",
            is_empty=False,
        )
        result = resolve_workspace_root(
            explicit_root=Path("/explicit/root"),
            workspace="brain",
            registry=registry,
        )
        assert result == Path("/explicit/root")

    def test_explicit_root_wins_even_with_no_registry(self):
        registry = WorkspaceRegistry()
        result = resolve_workspace_root(
            explicit_root=Path("/explicit/root"),
            workspace=None,
            registry=registry,
        )
        assert result == Path("/explicit/root")

    def test_named_workspace_resolves_from_registry(self):
        registry = WorkspaceRegistry(
            workspaces={"client-a": "/clients/client-a"}, is_empty=False
        )
        result = resolve_workspace_root(
            explicit_root=None, workspace="client-a", registry=registry
        )
        assert result == Path("/clients/client-a")

    def test_named_workspace_unknown_raises_typed_error(self):
        registry = WorkspaceRegistry(workspaces={"brain": "/brain"}, is_empty=False)
        with pytest.raises(UnknownWorkspaceError) as exc_info:
            resolve_workspace_root(
                explicit_root=None, workspace="missing", registry=registry
            )
        assert exc_info.value.name == "missing"

    def test_named_workspace_no_registry_raises_distinct_error(self):
        registry = WorkspaceRegistry()  # is_empty=True
        with pytest.raises(NoWorkspaceRegistryError):
            resolve_workspace_root(
                explicit_root=None, workspace="brain", registry=registry
            )

    def test_unknown_and_no_registry_are_distinct_types(self):
        assert not issubclass(NoWorkspaceRegistryError, UnknownWorkspaceError)
        assert not issubclass(UnknownWorkspaceError, NoWorkspaceRegistryError)

    def test_default_workspace_fallback(self):
        registry = WorkspaceRegistry(
            workspaces={"brain": "/brain"}, default_workspace="brain", is_empty=False
        )
        result = resolve_workspace_root(
            explicit_root=None, workspace=None, registry=registry
        )
        assert result == Path("/brain")

    def test_default_workspace_unknown_raises(self):
        registry = WorkspaceRegistry(
            workspaces={"brain": "/brain"},
            default_workspace="ghost",
            is_empty=False,
        )
        with pytest.raises(UnknownWorkspaceError):
            resolve_workspace_root(explicit_root=None, workspace=None, registry=registry)

    def test_built_in_default_is_cwd(self):
        registry = WorkspaceRegistry()
        result = resolve_workspace_root(
            explicit_root=None, workspace=None, registry=registry
        )
        assert result == Path(".")

    def test_purity_nonexistent_paths_resolve_fine(self, tmp_path):
        nonexistent = tmp_path / "does" / "not" / "exist"
        registry = WorkspaceRegistry(
            workspaces={"ghost-workspace": str(nonexistent)}, is_empty=False
        )
        result = resolve_workspace_root(
            explicit_root=None, workspace="ghost-workspace", registry=registry
        )
        assert result == nonexistent
        assert not result.exists()

    def test_registry_path_returned_verbatim_no_canonicalization(self):
        registry = WorkspaceRegistry(
            workspaces={"relative": "../relative/path"}, is_empty=False
        )
        result = resolve_workspace_root(
            explicit_root=None, workspace="relative", registry=registry
        )
        assert result == Path("../relative/path")

    def test_invalid_workspace_name_format_raises(self):
        registry = WorkspaceRegistry(workspaces={}, is_empty=False)
        with pytest.raises(InvalidWorkspaceNameError):
            resolve_workspace_root(
                explicit_root=None, workspace="Not_Valid", registry=registry
            )
