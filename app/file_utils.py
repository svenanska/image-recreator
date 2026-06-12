"""Filesystem helpers for uploads and generated artifacts."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUTS_DIR = ROOT_DIR / "inputs"
OUTPUTS_DIR = ROOT_DIR / "outputs"
PROMPTS_DIR = ROOT_DIR / "prompts"
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def ensure_directories() -> None:
    for directory in (INPUTS_DIR, OUTPUTS_DIR, PROMPTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def new_project_id() -> str:
    return uuid.uuid4().hex[:12]


def project_input_dir(project_id: str) -> Path:
    return INPUTS_DIR / safe_project_id(project_id)


def project_output_dir(project_id: str) -> Path:
    return OUTPUTS_DIR / safe_project_id(project_id)


def safe_project_id(project_id: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{12}", project_id):
        raise ValueError("Invalid project ID")
    return project_id


def prompt_text(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8").strip()


async def save_upload(upload: UploadFile, directory: Path, stem: str) -> Path:
    extension = Path(upload.filename or "").suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Images must be PNG, JPG, JPEG, or WEBP files")

    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{stem}{extension}"
    destination.write_bytes(await upload.read())
    if destination.stat().st_size == 0:
        destination.unlink(missing_ok=True)
        raise ValueError("Uploaded image is empty")
    return destination


def find_input(project_id: str, stem: str) -> Path:
    directory = project_input_dir(project_id)
    matches = [path for path in directory.glob(f"{stem}.*") if path.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS]
    if not matches:
        raise FileNotFoundError(f"Missing {stem.replace('_', ' ')} image")
    return matches[0]


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def artifact_url(path: Path) -> str:
    resolved = path.resolve()
    if resolved.is_relative_to(INPUTS_DIR.resolve()):
        relative = resolved.relative_to(INPUTS_DIR.resolve())
        return f"/files/inputs/{relative.as_posix()}"
    if resolved.is_relative_to(OUTPUTS_DIR.resolve()):
        relative = resolved.relative_to(OUTPUTS_DIR.resolve())
        return f"/files/outputs/{relative.as_posix()}"
    raise ValueError("Only input and output artifacts can be served")
