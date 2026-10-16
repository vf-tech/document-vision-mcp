"""PDF operations independent of MCP. All coordinates use the visible page."""

from contextlib import contextmanager
import math
from pathlib import Path

import pymupdf as fitz


class Documents:
    def __init__(self, root: str | Path | list[str | Path]):
        values = [root] if isinstance(root, (str, Path)) else root
        if not values:
            raise ValueError("At least one document root is required")
        roots = []
        for value in values:
            path = Path(value).expanduser().resolve(strict=True)
            if not path.is_dir():
                raise ValueError(f"Document root must be an existing directory: {path}")
            if path not in roots:
                roots.append(path)
        self.roots = tuple(roots)
        self.root = self.roots[0]  # Retain the single-root API.
        self.root_map = {f"root{i}": p for i, p in enumerate(self.roots, 1)}

    @property
    def multiple(self):
        return len(self.roots) > 1

    def resolve(self, file: str) -> Path:
        root = self.root
        relative = file
        if self.multiple:
            prefix, separator, relative = file.partition("/")
            if not separator or prefix not in self.root_map or not relative:
                raise ValueError("Multiple roots: use a filename from list_documents, e.g. root1/file.pdf")
            root = self.root_map[prefix]
            if Path(relative).anchor:
                raise ValueError("Use a relative filename after the root prefix")
        path = (root / relative).resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError("PDF must be inside the configured document root")
        if path.suffix.lower() != ".pdf" or not path.is_file():
            raise ValueError("Expected a PDF file")
        return path

    def list_documents(self, limit: int = 100) -> dict:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be 1..1000")
        files = []
        mappings = [{"id": key, "path": str(root)} for key, root in self.root_map.items()]
        for key, root in self.root_map.items():
            for p in sorted(root.rglob("*")):
                if p.suffix.lower() != ".pdf" or not p.is_file():
                    continue
                if not p.resolve().is_relative_to(root):
                    continue
                if len(files) == limit:
                    return {"files": files, "roots": mappings, "truncated": True}
                name = p.relative_to(root).as_posix()
                files.append(f"{key}/{name}" if self.multiple else name)
        return {"files": files, "roots": mappings, "truncated": False}

    @contextmanager
    def open(self, file: str):
        with fitz.open(self.resolve(file)) as doc:
            if not doc.is_pdf:
                raise ValueError("Expected PDF content")
            if doc.needs_pass:
                raise ValueError("Password-protected PDF is not supported")
            yield doc

    @staticmethod
    def page(doc, number: int):
        if not 1 <= number <= len(doc):
            raise ValueError(f"page must be 1..{len(doc)} (1-based)")
        page = doc[number - 1]
        # Normalize rotation in memory, preserving appearance and text positions.
        # Never save this document: the source bytes remain unchanged.
        if page.rotation:
            page.remove_rotation()
        return page

    @staticmethod
    def box(page, bbox: list[float] | None):
        if bbox is None:
            return page.rect
        if len(bbox) != 4 or not all(math.isfinite(v) for v in bbox):
            raise ValueError("bbox must contain four finite numbers")
        x0, y0, x1, y1 = bbox
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError("bbox must satisfy 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1")
        r = page.rect
        return fitz.Rect(r.x0 + x0*r.width, r.y0 + y0*r.height,
                         r.x0 + x1*r.width, r.y0 + y1*r.height)

    @staticmethod
    def normalized(page, rect):
        r = page.rect
        return [round((rect.x0-r.x0)/r.width, 6), round((rect.y0-r.y0)/r.height, 6),
                round((rect.x1-r.x0)/r.width, 6), round((rect.y1-r.y0)/r.height, 6)]

    def document_info(self, file: str, start_page: int = 1, limit: int = 50) -> dict:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be 1..100")
        with self.open(file) as doc:
            self.page(doc, start_page)
            end = min(len(doc), start_page + limit - 1)
            pages = []
            for n in range(start_page, end+1):
                p = self.page(doc, n)
                pages.append({"page": n, "width_pt": p.rect.width,
                              "height_pt": p.rect.height,
                              "text_characters": len(p.get_text()),
                              "has_text_layer": bool(p.get_text().strip())})
            return {"file": file, "page_count": len(doc), "metadata": doc.metadata,
                    "coordinate_system": "normalized visible page; origin top-left; x right, y down",
                    "pages": pages, "next_page": end+1 if end < len(doc) else None}

    def page_text(self, file: str, page: int, bbox: list[float] | None = None,
                  offset: int = 0, max_chars: int = 16000) -> dict:
        if offset < 0 or not 1 <= max_chars <= 50000:
            raise ValueError("offset must be >= 0; max_chars must be 1..50000")
        with self.open(file) as doc:
            p = self.page(doc, page)
            # Preserve PDF extraction order: layout sorting can inject hundreds
            # of thousands of whitespace characters on dense schematics.
            text = p.get_text("text", clip=self.box(p, bbox), sort=False)
            stop = offset + max_chars
            return {"file": file, "page": page, "bbox": bbox or [0, 0, 1, 1],
                    "text": text[offset:stop], "total_chars": len(text),
                    "next_offset": stop if stop < len(text) else None,
                    "note": "Text order does not prove schematic connectivity. No OCR is performed."}

    def search_text(self, file: str, query: str, start_page: int = 1,
                    end_page: int | None = None, limit: int = 30) -> dict:
        if not query.strip() or len(query) > 500:
            raise ValueError("query must contain 1..500 characters")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be 1..100")
        with self.open(file) as doc:
            end = len(doc) if end_page is None else end_page
            if not 1 <= start_page <= end <= len(doc):
                raise ValueError(f"page range must be within 1..{len(doc)}")
            if end-start_page+1 > 200:
                raise ValueError("Search at most 200 pages per call using start_page/end_page")
            hits = []
            for n in range(start_page, end+1):
                p = self.page(doc, n)
                for rect in p.search_for(query):
                    if len(hits) == limit:
                        return {"file": file, "query": query, "hits": hits, "truncated": True,
                                "note": "Narrow query or page range; text search is not OCR."}
                    nearby = fitz.Rect(rect.x0-24, rect.y0-12, rect.x1+24, rect.y1+12) & p.rect
                    hits.append({"page": n, "bbox": self.normalized(p, rect),
                                 "context": p.get_textbox(nearby)[:500]})
            return {"file": file, "query": query, "hits": hits, "truncated": False,
                    "note": "Literal PDF text search; no OCR. Empty hits do not prove absence."}

    def render(self, file: str, page: int, bbox: list[float] | None = None,
               dpi: int = 180) -> tuple[dict, bytes]:
        if not 36 <= dpi <= 600:
            raise ValueError("dpi must be 36..600")
        with self.open(file) as doc:
            p = self.page(doc, page)
            clip = self.box(p, bbox)
            # Reject oversize requests rather than silently downscaling unreadable labels.
            width = math.ceil(clip.width*dpi/72)+2
            height = math.ceil(clip.height*dpi/72)+2
            if width*height > 12_000_000 or max(width, height) > 6000:
                raise ValueError("Image exceeds 12 MP / 6000 px limit. Use a smaller crop or lower dpi.")
            pix = p.get_pixmap(dpi=dpi, clip=clip, alpha=False, colorspace=fitz.csRGB)
            png = pix.tobytes("png")
            if len(png) > 8_000_000:
                raise ValueError("PNG exceeds 8 MB. Use a smaller crop or lower dpi.")
            return {"file": file, "page": page, "bbox": bbox or [0, 0, 1, 1],
                    "dpi": dpi, "width_px": pix.width, "height_px": pix.height,
                    "mime_type": "image/png",
                    "note": "Crop coordinates always refer to the full visible page, not this image."}, png
