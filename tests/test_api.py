import base64
from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


class FakeOpenAIService:
    def analyze_scene(self, image_path: Path, analysis_prompt: str):
        assert image_path.read_bytes() == PNG
        assert "ONLY source of truth" in analysis_prompt
        return {"camera": {"style": "smartphone", "confidence": "high"}, "reconstruction_prompt": "scene"}

    def convert_blueprint(self, analysis, conversion_prompt: str):
        assert analysis["reconstruction_prompt"] == "scene"
        return "IDENTITY LOCK\nUse the reference identity.\n\nSCENE RECREATION\nRecreate the scene."

    def generate_from_identity(self, identity_path: Path, prompt: str, output_path: Path):
        assert identity_path.read_bytes() == PNG
        assert "SOURCE SEPARATION RULES" in prompt
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(PNG)
        return output_path


def test_complete_workflow(monkeypatch):
    monkeypatch.setattr(main, "openai_service", lambda: FakeOpenAIService())
    client = TestClient(main.app)

    created = client.post(
        "/api/projects",
        files={
            "scene_reference": ("scene.png", PNG, "image/png"),
            "identity_reference": ("identity.png", PNG, "image/png"),
        },
    )
    assert created.status_code == 200
    project_id = created.json()["project_id"]

    analyzed = client.post("/api/analyze", json={"project_id": project_id})
    assert analyzed.status_code == 200
    assert analyzed.json()["analysis"]["camera"]["style"] == "smartphone"

    built = client.post("/api/build-prompt", json={"project_id": project_id})
    assert built.status_code == 200
    assert "CASUAL CAMERA NEGATIVE CONSTRAINTS" in built.json()["prompt"]

    generated = client.post("/api/generate", json={"project_id": project_id})
    assert generated.status_code == 200
    assert generated.json()["image_url"].endswith("generated_image.png")

    carousel = client.post("/api/carousel", json={"project_id": project_id, "count": 3})
    assert carousel.status_code == 200
    assert len(carousel.json()["images"]) == 3
    assert all(item["image_url"].endswith(".png") for item in carousel.json()["images"])
