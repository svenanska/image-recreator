"""Filesystem and image-source helpers for Image Recreator."""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import uuid
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUTS_DIR = ROOT_DIR / "inputs"
OUTPUTS_DIR = ROOT_DIR / "outputs"
PROMPTS_DIR = ROOT_DIR / "prompts"
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
REQUEST_TIMEOUT = (8, 30)
USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


class ImageDownloadError(ValueError):
    """Raised when a remote scene image cannot be safely downloaded."""


class _OpenGraphImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.image_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta" or self.image_url:
            return
        values = {key.lower(): value for key, value in attrs if value is not None}
        property_name = (values.get("property") or values.get("name") or "").lower()
        if property_name in {"og:image", "og:image:url", "twitter:image"}:
            self.image_url = values.get("content")


def ensure_directories() -> None:
    for directory in (INPUTS_DIR, OUTPUTS_DIR, PROMPTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def new_project_id() -> str:
    return uuid.uuid4().hex[:12]


def safe_project_id(project_id: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{12}", project_id):
        raise ValueError("Invalid project ID")
    return project_id


def project_input_dir(project_id: str) -> Path:
    return INPUTS_DIR / safe_project_id(project_id)


def project_output_dir(project_id: str) -> Path:
    return OUTPUTS_DIR / safe_project_id(project_id)


def prompt_text(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8").strip()


def detect_image_extension(data: bytes) -> str | None:
    """Return a safe extension after validating the file's binary signature."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def save_image_bytes(data: bytes, directory: Path, stem: str) -> Path:
    if not data:
        raise ValueError("The image is empty")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("The image is larger than the 20 MB limit")
    extension = detect_image_extension(data)
    if not extension:
        raise ValueError("The file is not a valid JPG, PNG, or WEBP image")

    directory.mkdir(parents=True, exist_ok=True)
    for old_path in directory.glob(f"{stem}.*"):
        if old_path.is_file():
            old_path.unlink()
    destination = directory / f"{stem}{extension}"
    destination.write_bytes(data)
    return destination


def find_input(project_id: str, stem: str) -> Path:
    directory = project_input_dir(project_id)
    matches = [path for path in directory.glob(f"{stem}.*") if path.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS]
    if not matches:
        raise FileNotFoundError(f"Missing {stem.replace('_', ' ')} image")
    return matches[0]


def _validate_remote_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ImageDownloadError("Enter a complete http:// or https:// image URL")
    if parsed.username or parsed.password:
        raise ImageDownloadError("URLs containing credentials are not supported")

    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))}
    except socket.gaierror as exc:
        raise ImageDownloadError("The image URL hostname could not be resolved") from exc

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ImageDownloadError("Private, local, and reserved network URLs are not allowed")


def _request_with_safe_redirects(session: requests.Session, url: str) -> requests.Response:
    current_url = url
    for _ in range(MAX_REDIRECTS + 1):
        _validate_remote_url(current_url)
        try:
            response = session.get(
                current_url,
                headers={"User-Agent": USER_AGENT, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"},
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,
                stream=True,
            )
        except requests.RequestException as exc:
            raise ImageDownloadError(f"Could not download the URL: {exc}") from exc

        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ImageDownloadError("The image URL redirected without a destination")
            current_url = urljoin(current_url, location)
            continue
        if response.status_code >= 400:
            response.close()
            raise ImageDownloadError(f"The image server returned HTTP {response.status_code}")
        response.url = current_url
        return response
    raise ImageDownloadError("The image URL redirected too many times")


def _read_limited(response: requests.Response, limit: int) -> bytes:
    declared_size = response.headers.get("Content-Length")
    if declared_size and declared_size.isdigit() and int(declared_size) > limit:
        raise ImageDownloadError(f"The remote file exceeds the {limit // (1024 * 1024)} MB limit")
    content = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        content.extend(chunk)
        if len(content) > limit:
            raise ImageDownloadError(f"The downloaded file exceeds the {limit // (1024 * 1024)} MB limit")
    return bytes(content)


def _extract_page_image(html: bytes, page_url: str) -> str | None:
    parser = _OpenGraphImageParser()
    parser.feed(html.decode("utf-8", errors="ignore"))
    return urljoin(page_url, parser.image_url) if parser.image_url else None


def download_scene_image(
    url: str,
    directory: Path,
    session: requests.Session | None = None,
    *,
    _page_depth: int = 0,
) -> Path:
    """Download a direct image or an Open Graph image from a Pinterest-style page."""
    url = url.strip()
    if not url:
        raise ImageDownloadError("Enter a scene image URL")

    client = session or requests.Session()
    response = _request_with_safe_redirects(client, url)
    try:
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if content_type.startswith("text/html"):
            if _page_depth >= 1:
                raise ImageDownloadError("The page's image address led to another HTML page instead of an image")
            html = _read_limited(response, MAX_HTML_BYTES)
            page_image_url = _extract_page_image(html, response.url)
            if not page_image_url:
                raise ImageDownloadError(
                    "That page did not expose a downloadable image. Try opening the image and copying its direct address."
                )
            return download_scene_image(page_image_url, directory, client, _page_depth=_page_depth + 1)

        data = _read_limited(response, MAX_IMAGE_BYTES)
    finally:
        response.close()

    if content_type and not content_type.startswith("image/"):
        raise ImageDownloadError(f"The URL returned {content_type}, not an image")
    try:
        return save_image_bytes(data, directory, "scene_reference")
    except ValueError as exc:
        raise ImageDownloadError(f"The downloaded URL did not contain a valid JPG, PNG, or WEBP image: {exc}") from exc


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
