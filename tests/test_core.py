import hashlib
import math

import pymupdf as fitz
import pytest

from document_vision_mcp.core import Documents


@pytest.fixture
def docs(tmp_path):
    with fitz.open() as d:
        p = d.new_page(width=400, height=300)
        p.insert_text((40, 60), "R24 1k BOOTSTRAP")
        p.draw_rect(fitz.Rect(20, 20, 190, 140), color=(1, 0, 0))
        d.new_page(width=400, height=300)  # No text layer.
        d.save(tmp_path / "sample.pdf")
    return Documents(tmp_path)


def test_search_to_crop_and_source_integrity(docs):
    source = docs.root / "sample.pdf"
    before = hashlib.sha256(source.read_bytes()).digest()
    hit = docs.search_text("sample.pdf", "BOOTSTRAP")["hits"][0]
    assert hit["page"] == 1
    x0, y0, x1, y1 = hit["bbox"]
    bbox = [max(0, x0-.02), max(0, y0-.02), min(1, x1+.02), min(1, y1+.02)]
    assert "BOOTSTRAP" in docs.page_text("sample.pdf", 1, bbox)["text"]
    meta, png = docs.render("sample.pdf", 1, bbox, 400)
    pix = fitz.Pixmap(png)
    assert pix.width == meta["width_px"] and pix.height == meta["height_px"]
    assert png.startswith(b"\x89PNG")
    assert hashlib.sha256(source.read_bytes()).digest() == before


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_rotated_search_coordinates_match_pixels(docs, rotation):
    with fitz.open(docs.root / "sample.pdf") as d:
        d[0].set_rotation(rotation)
        d.save(docs.root / f"rotated-{rotation}.pdf")
    name = f"rotated-{rotation}.pdf"
    bbox = docs.search_text(name, "BOOTSTRAP")["hits"][0]["bbox"]
    # The small search hit crop contains ink at every page rotation.
    _, png = docs.render(name, 1, bbox, 400)
    pix = fitz.Pixmap(png)
    assert min(pix.samples) < 100
    assert "BOOTSTRAP" in docs.page_text(name, 1,
        [max(0,bbox[0]-.01), max(0,bbox[1]-.01), min(1,bbox[2]+.01), min(1,bbox[3]+.01)])["text"]


def test_cropbox_offset(docs):
    with fitz.open(docs.root / "sample.pdf") as d:
        d[0].set_cropbox(fitz.Rect(10, 10, 350, 250))
        d[0].set_rotation(90)
        d.save(docs.root / "cropped.pdf")
    hit = docs.search_text("cropped.pdf", "R24")["hits"][0]
    _, png = docs.render("cropped.pdf", 1, hit["bbox"], 400)
    assert min(fitz.Pixmap(png).samples) < 100


def test_pagination_and_empty_text(docs):
    first = docs.page_text("sample.pdf", 1, max_chars=4)
    second = docs.page_text("sample.pdf", 1, offset=first["next_offset"])
    assert first["text"]+second["text"] == docs.page_text("sample.pdf", 1)["text"]
    assert docs.document_info("sample.pdf", limit=1)["next_page"] == 2
    assert not docs.document_info("sample.pdf")["pages"][1]["has_text_layer"]
    assert docs.search_text("sample.pdf", "missing")["hits"] == []


@pytest.mark.parametrize("bbox", [[0,0,0,1], [-.1,0,1,1], [0,0,2,1],
                                    [0,0,math.nan,1], [0,0,1]])
def test_invalid_crops(docs, bbox):
    with pytest.raises(ValueError):
        docs.render("sample.pdf", 1, bbox)


@pytest.mark.parametrize("page", [0, -1, 3])
def test_page_bounds(docs, page):
    with pytest.raises(ValueError):
        docs.render("sample.pdf", page)


def test_path_escape_and_symlink(docs, tmp_path):
    outside = tmp_path.parent / (tmp_path.name + "-outside.pdf")
    outside.write_bytes((docs.root / "sample.pdf").read_bytes())
    try:
        with pytest.raises(ValueError):
            docs.resolve(str(outside))
        link = tmp_path / "escape.pdf"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("Symlink creation unavailable")
        with pytest.raises(ValueError):
            docs.resolve("escape.pdf")
        assert "escape.pdf" not in docs.list_documents()["files"]
    finally:
        outside.unlink()


def test_limits(docs):
    with pytest.raises(ValueError):
        docs.render("sample.pdf", 1, dpi=601)
    with fitz.open() as d:
        d.new_page(width=3000, height=3000)
        d.save(docs.root / "large.pdf")
    with pytest.raises(ValueError, match="smaller crop"):
        docs.render("large.pdf", 1, dpi=600)
    with pytest.raises(ValueError):
        docs.search_text("sample.pdf", " ")


def test_encrypted_pdf(docs):
    with fitz.open(docs.root / "sample.pdf") as d:
        d.save(docs.root / "encrypted.pdf", encryption=fitz.PDF_ENCRYPT_AES_256,
               owner_pw="owner", user_pw="password")
    with pytest.raises(ValueError, match="Password"):
        docs.document_info("encrypted.pdf")
