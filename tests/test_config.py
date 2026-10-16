"""Configuration precedence and fail-closed behavior."""

import pytest

from document_vision_mcp.server import parse_args


@pytest.fixture(autouse=True)
def clear_roots(monkeypatch):
    monkeypatch.delenv("DOCUMENT_VISION_ROOT", raising=False)
    monkeypatch.delenv("DOCUMENT_VISION_ROOTS", raising=False)


def test_env_root(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCUMENT_VISION_ROOT", str(tmp_path / "PDF references"))
    assert parse_args([]).root == str(tmp_path / "PDF references")


def test_cli_overrides_env(monkeypatch):
    monkeypatch.setenv("DOCUMENT_VISION_ROOT", "/project-a/pdfs")
    assert parse_args(["--root", "/project-b/pdfs"]).root == "/project-b/pdfs"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_root_fails(monkeypatch, value):
    monkeypatch.delenv("DOCUMENT_VISION_ROOT", raising=False)
    if value is not None:
        monkeypatch.setenv("DOCUMENT_VISION_ROOT", value)
    with pytest.raises(SystemExit) as err:
        parse_args([])
    assert err.value.code == 2


def test_explicit_empty_cli_does_not_fall_back(monkeypatch):
    monkeypatch.setenv("DOCUMENT_VISION_ROOT", "/project-a/pdfs")
    with pytest.raises(SystemExit):
        parse_args(["--root", ""])


def test_plural_env_overrides_singular(monkeypatch):
    monkeypatch.setenv("DOCUMENT_VISION_ROOT", "/ignored")
    monkeypatch.setenv("DOCUMENT_VISION_ROOTS", '["./refs", "../shared documents"]')
    assert parse_args([]).roots == ["./refs", "../shared documents"]


def test_cli_root_overrides_plural_env(monkeypatch):
    monkeypatch.setenv("DOCUMENT_VISION_ROOTS", "invalid-json")
    assert parse_args(["--root", "./one"]).roots == ["./one"]


def test_cli_roots_overrides_both_envs(monkeypatch):
    monkeypatch.setenv("DOCUMENT_VISION_ROOT", "/ignored")
    monkeypatch.setenv("DOCUMENT_VISION_ROOTS", "invalid-json")
    assert parse_args(["--roots", '["./one","./two"]']).roots == ["./one", "./two"]


@pytest.mark.parametrize("value", ["", "one,two", "[]", '"./refs"', "{}", "[null]", '[" "]', '["./refs", 2]'])
def test_bad_plural_env_rejected_without_fallback(monkeypatch, value):
    monkeypatch.setenv("DOCUMENT_VISION_ROOT", "/must-not-fall-back")
    monkeypatch.setenv("DOCUMENT_VISION_ROOTS", value)
    with pytest.raises(SystemExit):
        parse_args([])


def test_mutually_exclusive_cli_roots():
    with pytest.raises(SystemExit):
        parse_args(["--root", "./one", "--roots", '["./two"]'])
