"""Private, mobile-friendly Streamlit interface for Image Recreator."""

from __future__ import annotations

import hmac
import json
import os
from pathlib import Path
from typing import Any

import streamlit as st
from dotenv import load_dotenv

from app.file_utils import (
    ImageDownloadError,
    ROOT_DIR,
    download_scene_image,
    ensure_directories,
    new_project_id,
    project_input_dir,
    project_output_dir,
    prompt_text,
    save_image_bytes,
    write_json,
    write_text,
)
from app.openai_client import ImageRecreatorClient
from app.prompt_builder import apply_generation_guards, build_carousel_prompt

load_dotenv(ROOT_DIR / ".env")
ensure_directories()

st.set_page_config(
    page_title="Image Recreator",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .stApp { background: #f5f3ed; color: #191a17; }
      [data-testid="stHeader"] { background: transparent; }
      .block-container { max-width: 1180px; padding-top: 2rem; padding-bottom: 5rem; }
      h1 { letter-spacing: -0.055em !important; font-size: clamp(2.7rem, 7vw, 5.4rem) !important; line-height: .92 !important; }
      h2, h3 { letter-spacing: -0.035em !important; }
      .hero-copy { color: #696c65; max-width: 720px; font-size: 1.05rem; margin: .5rem 0 1.5rem; }
      .privacy-note { border-left: 4px solid #d8ff45; padding: .15rem 0 .15rem .85rem; color: #595c55; font-size: .9rem; margin: .7rem 0 1.4rem; }
      .step-label { font: 600 .72rem/1.2 monospace; letter-spacing: .12em; text-transform: uppercase; color: #72756d; margin-bottom: -.45rem; }
      div[data-testid="stFileUploader"] { background: #fbfaf6; border: 1px solid #dedbd1; padding: .5rem .75rem; }
      div[data-testid="stVerticalBlockBorderWrapper"] { background: #fbfaf6; border-color: #d9d6cc !important; }
      .stButton > button { min-height: 3rem; font-weight: 700; border-radius: 2px; border-color: #1d1e1b; }
      .stButton > button[kind="primary"] { background: #1d1e1b; color: white; }
      .stDownloadButton > button { width: 100%; border-radius: 2px; }
      [data-testid="stJson"] { background: #20221e; border-radius: 2px; }
      .gallery-title { margin-top: 2.2rem; }
      @media (max-width: 640px) {
        .block-container { padding: 1rem .8rem 3rem; }
        h1 { font-size: 3rem !important; }
        .hero-copy { font-size: .94rem; }
        div[data-testid="column"] { min-width: 100% !important; }
        .stButton > button { width: 100%; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def setting(name: str, default: str | None = None) -> str | None:
    """Read Streamlit secrets first, then local environment variables."""
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    if value is not None:
        return str(value)
    return os.getenv(name, default)


def require_password() -> None:
    configured_password = setting("APP_PASSWORD")
    if not configured_password:
        st.error("APP_PASSWORD is not configured. Add it to .env locally or Streamlit secrets when deployed.")
        st.code("APP_PASSWORD=choose-a-private-password", language="bash")
        st.stop()

    if st.session_state.get("authenticated"):
        return

    st.title("Image Recreator")
    st.caption("Private access")
    with st.form("password_form", clear_on_submit=True):
        entered_password = st.text_input("Password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Unlock", type="primary", use_container_width=True)
    if submitted:
        if hmac.compare_digest(entered_password, configured_password):
            st.session_state.authenticated = True
            st.rerun()
        st.error("Incorrect password")
    st.stop()


def initialize_state() -> None:
    defaults: dict[str, Any] = {
        "project_id": new_project_id(),
        "analysis": None,
        "analysis_path": None,
        "analyzed_scene_signature": None,
        "generation_prompt": None,
        "prompt_path": None,
        "generated_images": [],
        "scene_path": None,
        "identity_path": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def openai_service() -> ImageRecreatorClient:
    api_key = setting("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not configured in .env or Streamlit secrets")
    return ImageRecreatorClient(
        api_key=api_key,
        vision_model=setting("OPENAI_VISION_MODEL", "gpt-5.5"),
        text_model=setting("OPENAI_TEXT_MODEL", "gpt-5.5"),
        image_model=setting("OPENAI_IMAGE_MODEL", "gpt-image-2"),
        image_size=setting("OPENAI_IMAGE_SIZE", "1024x1536"),
        image_quality=setting("OPENAI_IMAGE_QUALITY", "medium"),
    )


def scene_signature(scene_upload: Any, scene_url: str) -> str:
    if scene_upload is not None:
        return f"upload:{scene_upload.name}:{scene_upload.size}"
    return f"url:{scene_url.strip()}" if scene_url.strip() else ""


def save_current_inputs(scene_upload: Any, scene_url: str, identity_upload: Any) -> tuple[Path, Path]:
    input_dir = project_input_dir(st.session_state.project_id)
    if scene_upload is not None:
        scene_path = save_image_bytes(scene_upload.getvalue(), input_dir, "scene_reference")
    elif scene_url.strip():
        scene_path = download_scene_image(scene_url, input_dir)
    else:
        raise ValueError("Upload a scene reference or enter a scene image URL")

    if identity_upload is None:
        raise ValueError("Upload an identity reference image")
    identity_path = save_image_bytes(identity_upload.getvalue(), input_dir, "identity_reference")
    st.session_state.scene_path = scene_path
    st.session_state.identity_path = identity_path
    return scene_path, identity_path


def save_current_identity(identity_upload: Any) -> Path:
    if identity_upload is None:
        raise ValueError("Upload an identity reference image")
    path = save_image_bytes(
        identity_upload.getvalue(),
        project_input_dir(st.session_state.project_id),
        "identity_reference",
    )
    st.session_state.identity_path = path
    return path


def register_image(path: Path, label: str) -> None:
    item = {"path": str(path), "label": label}
    existing = [image for image in st.session_state.generated_images if image["path"] != str(path)]
    st.session_state.generated_images = [item, *existing]


def render_download(path: Path, label: str, mime: str) -> None:
    st.download_button(
        label,
        data=path.read_bytes(),
        file_name=path.name,
        mime=mime,
        use_container_width=True,
        key=f"download-{path}-{label}",
    )


require_password()
initialize_state()

st.markdown('<p class="step-label">Private creative workbench</p>', unsafe_allow_html=True)
st.title("Image Recreator")
st.markdown(
    '<p class="hero-copy">Rebuild the scene DNA of a reference image with your chosen identity, then create a single image or a fresh carousel.</p>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="privacy-note"><strong>Identity lock:</strong> the identity upload is the only identity source. The scene reference supplies only composition, pose, camera, lighting, outfit, environment, and style.</div>',
    unsafe_allow_html=True,
)

with st.container(border=True):
    st.markdown('<p class="step-label">01 · References</p>', unsafe_allow_html=True)
    st.subheader("Choose your source images")
    source_col, identity_col = st.columns(2, gap="large")
    with source_col:
        scene_upload = st.file_uploader(
            "Scene reference image",
            type=["jpg", "jpeg", "png", "webp"],
            help="If both an upload and URL are supplied, the upload wins.",
        )
        scene_url = st.text_input(
            "Scene image URL",
            placeholder="https://i.pinimg.com/.../image.jpg",
            help="Direct image URLs and pages exposing an Open Graph image are downloaded server-side before analysis.",
        )
        if scene_upload is not None:
            st.image(scene_upload, caption="Scene reference · upload selected", use_container_width=True)
        elif scene_url.strip():
            st.caption("The URL image will be downloaded and validated when you click Analyze Scene. It is never hotlinked for analysis.")
    with identity_col:
        identity_upload = st.file_uploader(
            "Identity reference image",
            type=["jpg", "jpeg", "png", "webp"],
            help="Use a clear image of the person whose identity must be preserved.",
        )
        if identity_upload is not None:
            st.image(identity_upload, caption="Identity reference · identity only", use_container_width=True)

current_scene_signature = scene_signature(scene_upload, scene_url)
scene_changed = bool(
    st.session_state.analysis
    and current_scene_signature != st.session_state.analyzed_scene_signature
)
if scene_changed:
    st.warning("The selected scene source changed. Click Analyze Scene again before building or generating.")

st.markdown('<p class="step-label">02 · Workflow</p>', unsafe_allow_html=True)
button_cols = st.columns(4)
with button_cols[0]:
    analyze_clicked = st.button("Analyze Scene", type="primary", use_container_width=True)
with button_cols[1]:
    build_clicked = st.button(
        "Build Prompt",
        use_container_width=True,
        disabled=not st.session_state.analysis or scene_changed,
    )
with button_cols[2]:
    generate_clicked = st.button(
        "Generate Image",
        use_container_width=True,
        disabled=not st.session_state.generation_prompt or scene_changed,
    )
with button_cols[3]:
    carousel_count = st.number_input("Carousel count", min_value=1, max_value=10, value=5, step=1)
    carousel_clicked = st.button(
        "Carousel Mode",
        use_container_width=True,
        disabled=not st.session_state.generation_prompt or scene_changed,
    )

if analyze_clicked:
    try:
        with st.status("Downloading and analyzing the scene…", expanded=True) as status:
            scene_path, _ = save_current_inputs(scene_upload, scene_url, identity_upload)
            st.write("References saved locally.")
            analysis = openai_service().analyze_scene(scene_path, prompt_text("analyze_scene.txt"))
            analysis_path = project_output_dir(st.session_state.project_id) / "analysis.json"
            write_json(analysis_path, analysis)
            st.session_state.analysis = analysis
            st.session_state.analysis_path = analysis_path
            st.session_state.analyzed_scene_signature = current_scene_signature
            st.session_state.generation_prompt = None
            st.session_state.prompt_path = None
            st.session_state.generated_images = []
            status.update(label="Scene analysis complete", state="complete", expanded=False)
        st.success("Saved analysis.json")
    except (ValueError, ImageDownloadError) as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f"Scene analysis failed: {exc}")

if build_clicked:
    try:
        with st.spinner("Building the GPT Image 2 prompt…"):
            raw_prompt = openai_service().convert_blueprint(
                st.session_state.analysis,
                prompt_text("convert_json_to_generation_prompt.txt"),
            )
            final_prompt = apply_generation_guards(raw_prompt, st.session_state.analysis)
            prompt_path = project_output_dir(st.session_state.project_id) / "generation_prompt.txt"
            write_text(prompt_path, final_prompt)
            st.session_state.generation_prompt = final_prompt
            st.session_state.prompt_path = prompt_path
        st.success("Saved generation_prompt.txt")
    except Exception as exc:
        st.error(f"Prompt generation failed: {exc}")

if generate_clicked:
    try:
        with st.spinner("Generating a fresh image from the original identity reference…"):
            identity_path = save_current_identity(identity_upload)
            output_path = project_output_dir(st.session_state.project_id) / "generated_image.png"
            openai_service().generate_from_identity(
                identity_path,
                st.session_state.generation_prompt,
                output_path,
            )
            register_image(output_path, "Generated image")
        st.success("Generated image saved in outputs.")
    except Exception as exc:
        st.error(f"Image generation failed: {exc}")

if carousel_clicked:
    try:
        identity_path = save_current_identity(identity_upload)
        output_dir = project_output_dir(st.session_state.project_id)
        variation_template = prompt_text("carousel_variation_prompt.txt")
        service = openai_service()
        progress = st.progress(0, text="Starting carousel…")
        for index in range(1, int(carousel_count) + 1):
            variation_prompt = build_carousel_prompt(
                st.session_state.generation_prompt,
                st.session_state.analysis,
                variation_template,
                index,
                int(carousel_count),
            )
            prompt_path = output_dir / f"carousel_{index:02d}_prompt.txt"
            image_path = output_dir / f"carousel_{index:02d}.png"
            write_text(prompt_path, variation_prompt)
            # Every request uses only the original identity upload; generated outputs are never reused.
            service.generate_from_identity(identity_path, variation_prompt, image_path)
            register_image(image_path, f"Carousel {index}")
            progress.progress(index / int(carousel_count), text=f"Generated {index} of {int(carousel_count)}")
        progress.empty()
        st.success(f"Saved {int(carousel_count)} independent carousel images.")
    except Exception as exc:
        st.error(f"Carousel generation failed: {exc}")

analysis_tab, prompt_tab = st.tabs(["Analysis JSON", "Generation Prompt"])
with analysis_tab:
    if st.session_state.analysis:
        st.json(st.session_state.analysis, expanded=False)
        render_download(st.session_state.analysis_path, "Download analysis.json", "application/json")
    else:
        st.info("Analyze a scene to create analysis.json.")
with prompt_tab:
    if st.session_state.generation_prompt:
        st.text_area(
            "Final prompt",
            st.session_state.generation_prompt,
            height=360,
            label_visibility="collapsed",
        )
        render_download(st.session_state.prompt_path, "Download generation_prompt.txt", "text/plain")
    else:
        st.info("Build the prompt after scene analysis.")

st.markdown('<div class="gallery-title"><p class="step-label">03 · Outputs</p></div>', unsafe_allow_html=True)
st.subheader("Generated image gallery")
valid_images = [
    image for image in st.session_state.generated_images if Path(image["path"]).exists()
]
if not valid_images:
    st.info("Your generated images will appear here.")
else:
    gallery_columns = st.columns(3)
    for index, image in enumerate(valid_images):
        path = Path(image["path"])
        with gallery_columns[index % 3]:
            st.image(str(path), caption=image["label"], use_container_width=True)
            render_download(path, f"Download {image['label']}", "image/png")

with st.expander("Session and storage details"):
    st.write(f"Project ID: `{st.session_state.project_id}`")
    st.write(f"Inputs: `{project_input_dir(st.session_state.project_id)}`")
    st.write(f"Outputs: `{project_output_dir(st.session_state.project_id)}`")
    st.caption("Streamlit Community Cloud storage is temporary. Download files you want to keep.")
