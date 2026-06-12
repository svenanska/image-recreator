from pathlib import Path

import pytest

pytest.importorskip("requests")

from app import file_utils

PNG = b"\x89PNG\r\n\x1a\n" + b"test-payload"
JPG = b"\xff\xd8\xff\xe0" + b"test-payload"
WEBP = b"RIFF\x10\x00\x00\x00WEBP" + b"test-payload"


class FakeResponse:
    def __init__(self, body: bytes, content_type: str, url: str = "https://example.com/source"):
        self.body = body
        self.headers = {"Content-Type": content_type}
        self.status_code = 200
        self.url = url
        self.is_redirect = False
        self.is_permanent_redirect = False
        self.closed = False

    def iter_content(self, chunk_size: int):
        yield self.body

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requested_urls = []

    def get(self, url, **kwargs):
        self.requested_urls.append(url)
        return next(self.responses)


@pytest.mark.parametrize(
    ("data", "extension"),
    [(PNG, ".png"), (JPG, ".jpg"), (WEBP, ".webp")],
)
def test_save_image_bytes_validates_signature(tmp_path: Path, data: bytes, extension: str):
    path = file_utils.save_image_bytes(data, tmp_path, "scene_reference")
    assert path.suffix == extension
    assert path.read_bytes() == data


def test_save_image_bytes_rejects_non_image(tmp_path: Path):
    with pytest.raises(ValueError, match="not a valid"):
        file_utils.save_image_bytes(b"not-an-image", tmp_path, "scene_reference")


def test_download_direct_image(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(file_utils, "_validate_remote_url", lambda url: None)
    session = FakeSession([FakeResponse(PNG, "image/png")])
    path = file_utils.download_scene_image("https://example.com/photo", tmp_path, session)
    assert path.name == "scene_reference.png"
    assert path.read_bytes() == PNG


def test_download_pinterest_style_page_uses_open_graph_image(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(file_utils, "_validate_remote_url", lambda url: None)
    html = b'<html><head><meta property="og:image" content="https://i.pinimg.com/photo.jpg"></head></html>'
    session = FakeSession(
        [
            FakeResponse(html, "text/html; charset=utf-8", "https://www.pinterest.com/pin/123"),
            FakeResponse(JPG, "image/jpeg", "https://i.pinimg.com/photo.jpg"),
        ]
    )
    path = file_utils.download_scene_image("https://www.pinterest.com/pin/123", tmp_path, session)
    assert path.name == "scene_reference.jpg"
    assert session.requested_urls == [
        "https://www.pinterest.com/pin/123",
        "https://i.pinimg.com/photo.jpg",
    ]


def test_download_rejects_non_image_response(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(file_utils, "_validate_remote_url", lambda url: None)
    session = FakeSession([FakeResponse(b"plain text", "text/plain")])
    with pytest.raises(file_utils.ImageDownloadError, match="not an image"):
        file_utils.download_scene_image("https://example.com/file", tmp_path, session)


def test_private_urls_are_blocked(monkeypatch):
    monkeypatch.setattr(
        file_utils.socket,
        "getaddrinfo",
        lambda *args: [(None, None, None, None, ("127.0.0.1", 443))],
    )
    with pytest.raises(file_utils.ImageDownloadError, match="Private, local"):
        file_utils._validate_remote_url("https://localhost/image.jpg")
