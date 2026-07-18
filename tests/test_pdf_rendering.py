from pathlib import Path

import pytest

from sagasmith_core.documents import render_pdf_page


def test_render_pdf_page_returns_provenance_preserving_png(tmp_path: Path) -> None:
    pypdf = pytest.importorskip("pypdf")
    pytest.importorskip("pypdfium2")
    pytest.importorskip("PIL")
    source = tmp_path / "map.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=100)
    with source.open("wb") as stream:
        writer.write(stream)

    rendered = render_pdf_page(source, 1, scale=1.0)

    assert rendered.media_type == "image/png"
    assert rendered.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert rendered.page_number == 1
    assert rendered.page_count == 1
    assert rendered.width == 200
    assert rendered.height == 100
    assert len(rendered.checksum) == 64


def test_render_pdf_page_rejects_an_out_of_range_page(tmp_path: Path) -> None:
    pypdf = pytest.importorskip("pypdf")
    pytest.importorskip("pypdfium2")
    pytest.importorskip("PIL")
    source = tmp_path / "one-page.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=10, height=10)
    with source.open("wb") as stream:
        writer.write(stream)

    with pytest.raises(ValueError, match="between 1 and 1"):
        render_pdf_page(source, 2)
