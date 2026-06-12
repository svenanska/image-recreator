"""Regression checks for the resolved Streamlit project architecture."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_streamlit_is_the_canonical_entry_point():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()

    assert "import streamlit as st" in app_source
    assert "st.set_page_config" in app_source
    assert "streamlit" in requirements
    assert "fastapi" not in requirements
    assert "uvicorn" not in requirements


def test_legacy_fastapi_frontend_is_not_present():
    assert not (ROOT / "app" / "main.py").exists()
    assert not (ROOT / "frontend").exists()


def test_required_prompt_templates_are_preserved():
    required_prompts = {
        "analyze_scene.txt",
        "convert_json_to_generation_prompt.txt",
        "carousel_variation_prompt.txt",
    }
    prompt_directory = ROOT / "prompts"

    available_prompts = {path.name for path in prompt_directory.glob("*.txt")}
    assert required_prompts.issubset(available_prompts)
    for filename in required_prompts:
        assert (prompt_directory / filename).read_text(encoding="utf-8").strip()


def test_streamlit_command_is_documented():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "streamlit run app.py" in readme
