"""FastAPI entry point for the local Image Recreator application."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .file_utils import (
    ROOT_DIR,
    artifact_url,
    ensure_directories,
    find_input,
    new_project_id,
    project_input_dir,
    project_output_dir,
    prompt_text,
    read_json,
    safe_project_id,
    save_upload,
    write_json,
    write_text,
)
from .openai_client import ImageRecreatorClient
from .prompt_builder import apply_generation_guards, build_carousel_prompt

load_dotenv(ROOT_DIR / ".env")
ensure_directories()

app = FastAPI(title="Image Recreator", version="1.0.0")
app.mount("/static", StaticFiles(directory=ROOT_DIR / "frontend"), name="static")
app.mount("/files/inputs", StaticFiles(directory=ROOT_DIR / "inputs"), name="input-files")
app.mount("/files/outputs", StaticFiles(directory=ROOT_DIR / "outputs"), name="output-files")


class ProjectRequest(BaseModel):
    project_id: str


class CarouselRequest(ProjectRequest):
    count: int = Field(default=5, ge=1, le=10)


def openai_service() -> ImageRecreatorClient:
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured. Add it to .env and restart the server.")
    return ImageRecreatorClient()


def output_artifact(project_id: str, filename: str) -> Path:
    path = project_output_dir(project_id) / filename
    if not path.exists():
        raise HTTPException(status_code=409, detail=f"{filename} has not been created yet")
    return path


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT_DIR / "frontend" / "index.html")


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"status": "ok", "api_key_configured": bool(os.getenv("OPENAI_API_KEY"))}


@app.post("/api/projects")
async def create_project(
    scene_reference: UploadFile = File(...),
    identity_reference: UploadFile = File(...),
) -> dict[str, str]:
    project_id = new_project_id()
    try:
        directory = project_input_dir(project_id)
        scene_path = await save_upload(scene_reference, directory, "scene_reference")
        identity_path = await save_upload(identity_reference, directory, "identity_reference")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "project_id": project_id,
        "scene_reference_url": artifact_url(scene_path),
        "identity_reference_url": artifact_url(identity_path),
    }


@app.post("/api/analyze")
def analyze_scene(request: ProjectRequest) -> dict[str, object]:
    try:
        safe_project_id(request.project_id)
        scene_path = find_input(request.project_id, "scene_reference")
        analysis = openai_service().analyze_scene(scene_path, prompt_text("analyze_scene.txt"))
        path = project_output_dir(request.project_id) / "analysis.json"
        write_json(path, analysis)
        return {"analysis": analysis, "download_url": artifact_url(path)}
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Scene analysis failed: {exc}") from exc


@app.post("/api/build-prompt")
def build_prompt(request: ProjectRequest) -> dict[str, str]:
    try:
        safe_project_id(request.project_id)
        analysis = read_json(output_artifact(request.project_id, "analysis.json"))
        raw_prompt = openai_service().convert_blueprint(
            analysis, prompt_text("convert_json_to_generation_prompt.txt")
        )
        final_prompt = apply_generation_guards(raw_prompt, analysis)
        path = project_output_dir(request.project_id) / "generation_prompt.txt"
        write_text(path, final_prompt)
        return {"prompt": final_prompt, "download_url": artifact_url(path)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Prompt generation failed: {exc}") from exc


@app.post("/api/generate")
def generate_image(request: ProjectRequest) -> dict[str, str]:
    try:
        safe_project_id(request.project_id)
        identity_path = find_input(request.project_id, "identity_reference")
        prompt = output_artifact(request.project_id, "generation_prompt.txt").read_text(encoding="utf-8")
        output_path = project_output_dir(request.project_id) / "generated_image.png"
        openai_service().generate_from_identity(identity_path, prompt, output_path)
        return {"image_url": artifact_url(output_path), "download_url": artifact_url(output_path)}
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Image generation failed: {exc}") from exc


@app.post("/api/carousel")
def generate_carousel(request: CarouselRequest) -> dict[str, list[dict[str, str]]]:
    try:
        safe_project_id(request.project_id)
        identity_path = find_input(request.project_id, "identity_reference")
        analysis = read_json(output_artifact(request.project_id, "analysis.json"))
        base_prompt = output_artifact(request.project_id, "generation_prompt.txt").read_text(encoding="utf-8")
        variation_template = prompt_text("carousel_variation_prompt.txt")
        service = openai_service()
        images = []
        for index in range(1, request.count + 1):
            variation_prompt = build_carousel_prompt(base_prompt, analysis, variation_template, index, request.count)
            prompt_path = project_output_dir(request.project_id) / f"carousel_{index:02d}_prompt.txt"
            image_path = project_output_dir(request.project_id) / f"carousel_{index:02d}.png"
            write_text(prompt_path, variation_prompt)
            # Every call receives only the original identity upload. No generated output is reused.
            service.generate_from_identity(identity_path, variation_prompt, image_path)
            images.append(
                {
                    "image_url": artifact_url(image_path),
                    "download_url": artifact_url(image_path),
                    "prompt_url": artifact_url(prompt_path),
                }
            )
        return {"images": images}
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Carousel generation failed: {exc}") from exc
