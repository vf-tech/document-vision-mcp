# Validation — 2026-10-16

## Tested environment

- Linux container, Python 3.12.14
- MCP Python SDK 1.30.0 (1.x API)
- PyMuPDF 1.26.6
- Automated tests: **48 passed** (includes real multi-root stdio integration)
- Real stdio MCP session via official SDK client: **passed**

## User-provided reference documents

| PDF | Pages | Page 1 extracted characters | Literal `F1C` matches | Render / crop |
|---|---:|---:|---:|---|
| CherryPi-F1C200S.pdf | 1 | 6705 | 3 | PASS / PASS |
| Planck-Pi-DK.pdf | 2 | 12693 | 1 | PASS / PASS |
| lichee_nano_8.16(Schematic).pdf | 1 | 7655 | 2 | PASS / PASS |

For each document the smoke test called document_info, page_text, search_text,
page_render at 120 dpi and page_crop at 400 dpi. list_documents was called once.
Each image response contained a text metadata block and a real MCP ImageContent
PNG block. Base64 decoded successfully and pixel dimensions matched metadata.
The crop PNGs were opened for visual inspection; labels were readable.
The source PDF SHA256 values were unchanged after all operations.

## Additional checks

- Multiple roots: DOCUMENT_VISION_ROOTS and --roots accept JSON arrays of
  absolute/relative directory strings. CLI overrides environment settings;
  plural environment setting overrides singular. Invalid lists fail explicitly.
- Distinct roots namespace files as root1/, root2/, etc.; identical resolved roots
  are deduplicated. One remaining root preserves legacy filenames.
- Real stdio test used two relative roots (with spaces) resolved against a set cwd,
  each containing a different PDF named same.pdf. Listing, text and image calls
  selected the correct root; source SHA256 values were unchanged.
- Missing roots are rejected; traversal between configured roots is blocked.
- The original three user PDFs passed the single-root environment smoke test
  after the multi-root change.

- DOCUMENT_VISION_ROOT support: environment-only startup, explicit --root
  precedence, absent/blank values rejected. Six configuration cases passed.
- The complete three-PDF stdio smoke test also passed with DOCUMENT_VISION_ROOT
  supplied in the child process environment and no --root argument.

- Linux installer added: explicitly selects Linux Python, reuses a valid Linux
  venv, rejects a Windows/non-Linux venv without deleting it, and leaves Codex
  registration to the user.
- A clean Linux venv installation completed with the alternative interpreter
  argument and the server import check passed. Default `/usr/bin/python3` in
  this container lacks ensurepip and correctly reports the need for python3-venv.
  The clean installation resolved MCP 1.30.0 and PyMuPDF 1.28.2.

- Search-hit bounding boxes map to rendered pixels at 0/90/180/270 degree rotation.
- Nonzero page cropbox + rotation preserves coordinate alignment.
- Invalid page numbers, invalid/nonfinite crops and excessive render requests fail explicitly.
- Parent traversal and symlinks to PDFs outside the configured root are rejected.
- Password-protected PDFs fail with a clear error.
- Text and metadata pagination work; pages without text layers are reported.
- An invalid crop returns an MCP tool error; subsequent calls still work in the same session.
- Raw PDF text extraction is used instead of layout-sorted whitespace reconstruction:
  on these schematic pages the latter inflated output by more than an order of magnitude.

## Scope limits

This validates the backend, image output and stdio MCP protocol in this Linux
environment. No authenticated Codex CLI/model session or AnythingLLM session
was run here. The user's Codex installation still needs the three-label visual
smoke check in README.md. Native Windows and actual WSL were not executed here.
OCR, semantic retrieval, automated netlist reconstruction and electrical
correctness are outside this version's scope.

The supplied PDFs are not bundled. Re-run scripts/smoke_mcp.py against local
copies to reproduce the JSON report and image previews.
