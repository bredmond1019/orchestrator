"""Unit tests for app/services/workspace_resolver.py (contract §3 semantics)."""

import dataclasses
from pathlib import Path

import pytest
from services.workspace_resolver import (
    InvalidWorkspaceNameError,
    MalformedRegistryError,
    NoWorkspaceRegistryError,
    UnknownWorkspaceError,
    WorkspaceRegistry,
    default_registry_path,
    load_registry,
    resolve_workspace_root,
    validate_workspace_name,
)

# ---------------------------------------------------------------------------
# validate_workspace_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["brain", "client-a", "or-c", "a1-b2", "x"])
def test_validate_workspace_name_accepts_kebab_case(name):
    validate_workspace_name(name)  # should not raise


@pytest.mark.parametrize(
    "name",
    ["Brain", "client_a", "client a", "-brain", "brain-", "brain--a", "", "CLIENT"],
)
def test_validate_workspace_name_rejects_bad_format(name):
    with pytest.raises(InvalidWorkspaceNameError):
        validate_workspace_name(name)


# ---------------------------------------------------------------------------
# default_registry_path
# ---------------------------------------------------------------------------


def test_default_registry_path_prefers_xdg():
    path = default_registry_path(xdg_config_home="/xdg", home="/home/user")
    assert path == Path("/xdg/orchestrator/config.toml")


def test_default_registry_path_falls_back_to_home():
    path = default_registry_path(xdg_config_home=None, home="/home/user")
    assert path == Path("/home/user/.config/orchestrator/config.toml")


def test_default_registry_path_none_when_neither_set():
    assert default_registry_path(xdg_config_home=None, home=None) is None


# ---------------------------------------------------------------------------
# load_registry
# ---------------------------------------------------------------------------


def test_load_registry_none_path_is_empty():
    registry = load_registry(None)
    assert registry.workspaces == {}
    assert registry.default_workspace is None
    assert registry.is_empty


def test_load_registry_absent_file_is_empty(tmp_path):
    missing = tmp_path / "does-not-exist" / "config.toml"
    registry = load_registry(missing)
    assert registry.is_empty


def test_load_registry_unreadable_file_is_empty(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[workspaces]\nbrain = '/x'\n", encoding="utf-8")
    path.chmod(0o000)
    try:
        registry = load_registry(path)
        assert registry.is_empty
    finally:
        path.chmod(0o644)


def test_load_registry_valid_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
default_workspace = "brain"

[workspaces]
brain = "/abs/brain"
client-a = "/abs/client-a"
""",
        encoding="utf-8",
    )
    registry = load_registry(path)
    assert registry.workspaces == {"brain": "/abs/brain", "client-a": "/abs/client-a"}
    assert registry.default_workspace == "brain"
    assert not registry.is_empty


def test_load_registry_file_with_no_workspaces_table(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("default_workspace = \"brain\"\n", encoding="utf-8")
    registry = load_registry(path)
    assert registry.workspaces == {}
    assert registry.default_workspace == "brain"


def test_load_registry_malformed_toml_raises(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("this is not [ valid toml", encoding="utf-8")
    with pytest.raises(MalformedRegistryError):
        load_registry(path)


def test_load_registry_wrong_shape_workspaces_raises(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('workspaces = "not-a-table"\n', encoding="utf-8")
    with pytest.raises(MalformedRegistryError):
        load_registry(path)


def test_load_registry_non_string_workspace_value_raises(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[workspaces]\nbrain = 42\n", encoding="utf-8")
    with pytest.raises(MalformedRegistryError):
        load_registry(path)


def test_load_registry_non_string_default_workspace_raises(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("default_workspace = 42\n", encoding="utf-8")
    with pytest.raises(MalformedRegistryError):
        load_registry(path)


# ---------------------------------------------------------------------------
# resolve_workspace_root — precedence
# ---------------------------------------------------------------------------


def test_explicit_root_wins_over_everything():
    registry = WorkspaceRegistry(
        workspaces={"brain": "/registry/brain"}, default_workspace="brain"
    )
    root = resolve_workspace_root(
        explicit_root=Path("/explicit/root"), workspace="brain", registry=registry
    )
    assert root == Path("/explicit/root")


def test_explicit_root_does_not_require_registry_lookup():
    # Even with an unknown workspace name, explicit root wins with no error.
    registry = WorkspaceRegistry()
    root = resolve_workspace_root(
        explicit_root=Path("/explicit/root"), workspace="ghost", registry=registry
    )
    assert root == Path("/explicit/root")


def test_named_workspace_resolves_from_registry():
    registry = WorkspaceRegistry(workspaces={"client-a": "/abs/client-a"})
    root = resolve_workspace_root(explicit_root=None, workspace="client-a", registry=registry)
    assert root == Path("/abs/client-a")


def test_named_workspace_unknown_raises_unknown_workspace_error():
    registry = WorkspaceRegistry(workspaces={"brain": "/abs/brain"})
    with pytest.raises(UnknownWorkspaceError) as exc_info:
        resolve_workspace_root(explicit_root=None, workspace="missing", registry=registry)
    assert exc_info.value.name == "missing"


def test_named_workspace_with_empty_registry_raises_no_registry_error():
    registry = WorkspaceRegistry()
    with pytest.raises(NoWorkspaceRegistryError) as exc_info:
        resolve_workspace_root(explicit_root=None, workspace="brain", registry=registry)
    assert exc_info.value.name == "brain"


def test_unknown_and_no_registry_are_distinct_types():
    assert not issubclass(UnknownWorkspaceError, NoWorkspaceRegistryError)
    assert not issubclass(NoWorkspaceRegistryError, UnknownWorkspaceError)


def test_default_workspace_used_when_no_explicit_name():
    registry = WorkspaceRegistry(
        workspaces={"brain": "/abs/brain"}, default_workspace="brain"
    )
    root = resolve_workspace_root(explicit_root=None, workspace=None, registry=registry)
    assert root == Path("/abs/brain")


def test_default_workspace_unknown_raises_unknown_workspace_error():
    registry = WorkspaceRegistry(
        workspaces={"other": "/abs/other"}, default_workspace="ghost"
    )
    with pytest.raises(UnknownWorkspaceError):
        resolve_workspace_root(explicit_root=None, workspace=None, registry=registry)


def test_builtin_default_when_nothing_supplied():
    registry = WorkspaceRegistry()
    root = resolve_workspace_root(explicit_root=None, workspace=None, registry=registry)
    assert root == Path(".")


def test_resolution_is_pure_for_nonexistent_paths():
    # No existence check — a path that doesn't exist on disk resolves fine.
    registry = WorkspaceRegistry(workspaces={"ghost-dir": "/does/not/exist/at/all"})
    root = resolve_workspace_root(explicit_root=None, workspace="ghost-dir", registry=registry)
    assert root == Path("/does/not/exist/at/all")
    assert not root.exists()


def test_registry_paths_returned_verbatim_no_canonicalization():
    registry = WorkspaceRegistry(workspaces={"rel": "./relative/../weird/path"})
    root = resolve_workspace_root(explicit_root=None, workspace="rel", registry=registry)
    assert root == Path("./relative/../weird/path")


def test_named_workspace_invalid_format_raises_before_lookup():
    registry = WorkspaceRegistry(workspaces={"brain": "/abs/brain"})
    with pytest.raises(InvalidWorkspaceNameError):
        resolve_workspace_root(explicit_root=None, workspace="Not_Kebab", registry=registry)


# ---------------------------------------------------------------------------
# WorkspaceRegistry basics
# ---------------------------------------------------------------------------


def test_workspace_registry_is_empty_default():
    assert WorkspaceRegistry().is_empty


def test_workspace_registry_not_empty_with_workspaces():
    assert not WorkspaceRegistry(workspaces={"brain": "/x"}).is_empty


def test_workspace_registry_not_empty_with_default_only():
    assert not WorkspaceRegistry(default_workspace="brain").is_empty


def test_workspace_registry_frozen():
    registry = WorkspaceRegistry()
    with pytest.raises(dataclasses.FrozenInstanceError):
        registry.workspaces = {"a": "b"}
