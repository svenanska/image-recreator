"""Build final generation and carousel prompts from the saved blueprint."""

from __future__ import annotations

import json
from typing import Any

CASUAL_CAMERA_MARKERS = (
    "smartphone",
    "phone camera",
    "front camera",
    "rear camera",
    "social media",
    "snapshot",
    "handheld",
    "casual",
    "compression",
    "beauty filter",
    "selfie",
)


def blueprint_as_text(analysis: dict[str, Any]) -> str:
    return json.dumps(analysis, indent=2, ensure_ascii=False)


def needs_casual_negative_prompt(analysis: dict[str, Any]) -> bool:
    camera_and_dna = json.dumps(
        {
            "camera": analysis.get("camera", {}),
            "image_dna": analysis.get("image_dna", {}),
            "image_processing": analysis.get("image_processing", {}),
            "scene_recipe": analysis.get("scene_recipe", {}),
        },
        ensure_ascii=False,
    ).lower()
    return any(marker in camera_and_dna for marker in CASUAL_CAMERA_MARKERS)


def apply_generation_guards(prompt: str, analysis: dict[str, Any]) -> str:
    guards = [
        "SOURCE SEPARATION RULES",
        "- The identity reference image is the only identity source.",
        "- The scene blueprint is the only source for scene, composition, pose logic, camera, lighting, outfit, environment, and style.",
        "- Do not borrow, average, or blend identity from the original scene subject.",
        "- Do not use memory, assumptions, or any previously generated image.",
    ]
    if needs_casual_negative_prompt(analysis):
        guards.extend(
            [
                "",
                "CASUAL CAMERA NEGATIVE CONSTRAINTS",
                "Avoid a professional DSLR or studio-production look: no cinematic bokeh, no artificially shallow depth of field, no editorial polish, no luxury campaign retouching, no studio-perfect lighting, and no over-clean commercial sharpness unless directly required by the blueprint.",
                "Preserve the visible smartphone/social-media snapshot qualities, including natural imperfections, processing, compression, noise, and handheld character described in the blueprint.",
            ]
        )
    return f"{prompt.strip()}\n\n" + "\n".join(guards)


def build_carousel_prompt(
    base_prompt: str,
    analysis: dict[str, Any],
    variation_template: str,
    index: int,
    total: int,
) -> str:
    variation = (
        f"{variation_template.strip()}\n\n"
        f"VARIATION NUMBER\nCreate image {index} of {total}. Choose a distinct, natural pose and framing variation "
        "that remains faithful to the original scene DNA. Do not repeat the default pose verbatim."
    )
    carousel_prompt = f"{base_prompt.strip()}\n\nCAROUSEL INSTRUCTION\n{variation}"
    if "SOURCE SEPARATION RULES" in base_prompt:
        return carousel_prompt
    return apply_generation_guards(carousel_prompt, analysis)
