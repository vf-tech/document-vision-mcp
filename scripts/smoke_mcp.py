"""Exercise a real stdio MCP session against all PDFs in a directory.

Usage: python scripts/smoke_mcp.py --root /path/to/pdfs --output /path/to/results
No model call/API key. Confirms protocol image delivery, not model recognition.
"""

import argparse
import asyncio
import base64
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pymupdf as fitz


def data(result):
    assert not result.isError, result
    return json.loads(next(x.text for x in result.content if x.type == "text"))


async def run(root, output, env_root=False):
    output.mkdir(parents=True, exist_ok=True)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob("*.pdf")}
    report = {"python": sys.version.split()[0],
              "mcp": importlib.metadata.version("mcp"), "pymupdf": fitz.VersionBind,
              "scope": "SDK stdio client; actual Codex CLI/model session NOT exercised", "files": []}
    report["root_configuration"] = "DOCUMENT_VISION_ROOT" if env_root else "--root"
    server_args = ["-m", "document_vision_mcp.server"]
    if not env_root:
        server_args += ["--root", str(root)]
    params = StdioServerParameters(command=sys.executable, args=server_args,
        env={**os.environ, "DOCUMENT_VISION_ROOT": str(root)} if env_root else None)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            tools = await s.list_tools()
            report["tools"] = [t.name for t in tools.tools]
            assert set(report["tools"]) == {"list_documents", "document_info", "page_text",
                                           "search_text", "page_render", "page_crop"}
            listing = data(await s.call_tool("list_documents", {}))
            for i, name in enumerate(listing["files"]):
                info = data(await s.call_tool("document_info", {"file": name}))
                text = data(await s.call_tool("page_text", {"file": name, "page": 1}))
                # A known family name in the supplied hardware reference documents.
                hits = data(await s.call_tool("search_text", {"file": name, "query": "F1C"}))
                bbox = [0, 0, .35, .35]
                if hits["hits"]:
                    # Prefer a circuit label over a bottom-of-page title block.
                    hit = min(hits["hits"], key=lambda h: h["bbox"][1])
                    x0,y0,x1,y1 = hit["bbox"]
                    bbox = [max(0,x0-.10), max(0,y0-.12), min(1,x1+.15), min(1,y1+.15)]
                images = []
                for tool, args in [("page_render", {"dpi": 120}),
                                   ("page_crop", {"bbox": bbox, "dpi": 400})]:
                    result = await s.call_tool(tool, {"file": name, "page": 1, **args})
                    meta = data(result)
                    blocks = [b for b in result.content if b.type == "image"]
                    assert len(blocks) == 1 and blocks[0].mimeType == "image/png"
                    png = base64.b64decode(blocks[0].data, validate=True)
                    pix = fitz.Pixmap(png)
                    assert (pix.width, pix.height) == (meta["width_px"], meta["height_px"])
                    path = output / f"{i+1}-{tool}.png"
                    path.write_bytes(png)
                    images.append({**meta, "bytes": len(png), "preview": path.name})
                report["files"].append({"file": name, "page_count": info["page_count"],
                    "page1_text_characters": text["total_chars"], "F1C_hits": len(hits["hits"]),
                    "images": images})
            bad = await s.call_tool("page_crop", {"file": listing["files"][0],
                "page": 1, "bbox": [0,0,2,1]})
            assert bad.isError
            report["invalid_bbox_returns_tool_error"] = True
            # The same session must remain usable after a tool error.
            data(await s.call_tool("document_info", {"file": listing["files"][0]}))
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob("*.pdf")}
    assert before == after
    report["source_sha256_unchanged"] = before
    (output / "smoke-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--env-root", action="store_true", help="Test DOCUMENT_VISION_ROOT instead of --root")
    a = p.parse_args()
    asyncio.run(run(a.root.resolve(), a.output.resolve(), a.env_root))
