"""Small, testable wrapper around the current OpenAI Python SDK."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from .prompt_builder import blueprint_as_text

VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-5.5")
TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-5.5")
IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2")
IMAGE_SIZE = os.getenv("OPENAI_IMAGE_SIZE", "1024x1536")
IMAGE_QUALITY = os.getenv("OPENAI_IMAGE_QUALITY", "medium")


class ImageRecreatorClient:
    def __init__(self, client: OpenAI | None = None) -> None:
        self.client = client or OpenAI()

    @staticmethod
    def _image_data_url(image_path: Path) -> str:
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def analyze_scene(self, image_path: Path, analysis_prompt: str) -> dict[str, Any]:
        response = self.client.responses.create(
            model=VISION_MODEL,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": analysis_prompt},
                        {
                            "type": "input_image",
                            "image_url": self._image_data_url(image_path),
                            "detail": "high",
                        },
                    ],
                }
            ],
        )
        raw = response.output_text.strip()
        if raw.startswith("```"):
            raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("The vision model did not return valid JSON") from exc
        if not isinstance(result, dict):
            raise ValueError("The scene analysis must be a JSON object")
        return result

    def convert_blueprint(self, analysis: dict[str, Any], conversion_prompt: str) -> str:
        response = self.client.responses.create(
            model=TEXT_MODEL,
            input=(
                f"{conversion_prompt}\n\n"
                "RECONSTRUCTION BLUEPRINT JSON\n"
                f"{blueprint_as_text(analysis)}"
            ),
        )
        prompt = response.output_text.strip()
        if not prompt:
            raise ValueError("The text model returned an empty generation prompt")
        return prompt

    def generate_from_identity(self, identity_path: Path, prompt: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with identity_path.open("rb") as identity_file:
            result = self.client.images.edit(
                model=IMAGE_MODEL,
                image=identity_file,
                prompt=prompt,
                size=IMAGE_SIZE,
                quality=IMAGE_QUALITY,
                output_format="png",
            )
        if not result.data or not result.data[0].b64_json:
            raise ValueError("The image model returned no image data")
        output_path.write_bytes(base64.b64decode(result.data[0].b64_json))
        return output_path
