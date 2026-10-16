import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pymupdf as fitz
import pytest

from document_vision_mcp.core import Documents


@pytest.fixture
def roots(tmp_path):
    paths = [tmp_path / "project refs", tmp_path / "shared refs"]
    for i, path in enumerate(paths, 1):
        path.mkdir()
        with fitz.open() as d:
            p = d.new_page(width=400, height=300)
            p.insert_text((30, 40), f"PROJECT{i} R24")
            d.save(path / "same.pdf")
    return paths


def test_same_name_resolves_to_correct_root(roots):
    docs = Documents(roots)
    assert docs.list_documents()["files"] == ["root1/same.pdf", "root2/same.pdf"]
    assert "PROJECT1" in docs.page_text("root1/same.pdf", 1)["text"]
    assert "PROJECT2" in docs.page_text("root2/same.pdf", 1)["text"]
    assert docs.list_documents()["roots"][1]["path"] == str(roots[1])


def test_relative_roots_use_cwd(roots, monkeypatch):
    monkeypatch.chdir(roots[0].parent)
    docs = Documents(["./project refs", "./shared refs"])
    assert docs.roots == tuple(roots)
    assert docs.resolve("root2/same.pdf") == roots[1] / "same.pdf"


def test_duplicate_roots_deduplicated(roots):
    docs = Documents([roots[0], roots[0] / "."])
    assert docs.list_documents()["files"] == ["same.pdf"]


def test_one_plural_root_preserves_legacy_names(roots):
    assert Documents([roots[0]]).resolve("same.pdf") == roots[0] / "same.pdf"


@pytest.mark.parametrize("name", ["same.pdf", "root3/same.pdf", "root1/", "root1//etc/passwd"])
def test_bad_root_identifier(roots, name):
    with pytest.raises(ValueError):
        Documents(roots).resolve(name)


def test_cannot_traverse_to_other_configured_root(roots):
    with pytest.raises(ValueError):
        Documents(roots).resolve("root1/../shared refs/same.pdf")


def test_missing_root_is_not_silently_ignored(roots):
    with pytest.raises(FileNotFoundError):
        Documents([roots[0], roots[1] / "missing"])


def test_limit_across_roots(roots):
    result = Documents(roots).list_documents(limit=1)
    assert result["files"] == ["root1/same.pdf"]
    assert result["truncated"]


def test_multi_root_stdio_with_relative_env(roots):
    async def run():
        env = {**os.environ, "DOCUMENT_VISION_ROOTS": '["./project refs", "./shared refs"]'}
        params = StdioServerParameters(command=sys.executable,
            args=["-m", "document_vision_mcp.server"], env=env,
            cwd=str(roots[0].parent))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listing = await session.call_tool("list_documents", {})
                payload = json.loads(listing.content[0].text)
                assert payload["files"] == ["root1/same.pdf", "root2/same.pdf"]
                for i in (1, 2):
                    name = f"root{i}/same.pdf"
                    text = await session.call_tool("page_text", {"file": name, "page": 1})
                    assert not text.isError
                    assert f"PROJECT{i}" in json.loads(text.content[0].text)["text"]
                    result = await session.call_tool("page_crop", {"file": name, "page": 1,
                        "bbox": [0, 0, .5, .5], "dpi": 300})
                    assert not result.isError
                    png = base64.b64decode(next(b.data for b in result.content if b.type == "image"))
                    assert min(fitz.Pixmap(png).samples) < 100
    before = [hashlib.sha256((p / "same.pdf").read_bytes()).digest() for p in roots]
    asyncio.run(run())
    assert before == [hashlib.sha256((p / "same.pdf").read_bytes()).digest() for p in roots]
