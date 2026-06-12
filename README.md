# Image Recreator

A local FastAPI web app that turns a scene reference into a forensic reconstruction blueprint, combines that blueprint with a separate identity reference, and generates a fresh image or a set of carousel variations with GPT Image 2.

## What it does

1. Upload a **scene reference** for composition, pose, camera, lighting, outfit, environment, and visual style.
2. Upload an **identity reference** as the only source for the generated person's identity.
3. Analyze the scene with a vision-capable OpenAI model and save `analysis.json`.
4. Convert the JSON blueprint into a clean generation prompt and save `generation_prompt.txt`.
5. Generate a new image with GPT Image 2 by passing only the original identity image plus the scene prompt.
6. Optionally generate 1–10 independent carousel variations from the same original identity and blueprint.

The scene image is never sent to the image-generation call. A generated image is never used as the input for another generated image.

## Project layout

```text
app/        FastAPI routes, OpenAI integration, prompt logic, file helpers
frontend/   Plain HTML, CSS, and JavaScript UI
inputs/     Uploaded references, grouped by project ID
outputs/    JSON, prompts, generated images, and carousel prompts
prompts/    Editable analysis/conversion/carousel templates
tests/      Workflow and prompt-guard tests
```

## Requirements

- Python 3.10 or newer
- An OpenAI API key with access to the configured vision, text, and image models

The defaults are `gpt-5.5` for scene analysis and prompt conversion, and `gpt-image-2` for generation.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

For tests, install the development requirements instead:

```bash
pip install -r requirements-dev.txt
```

## Configure `.env`

Copy the example and add your key:

```bash
cp .env.example .env
```

Then edit `.env`:

```dotenv
OPENAI_API_KEY=sk-your-real-key
```

Optional settings:

```dotenv
OPENAI_VISION_MODEL=gpt-5.5
OPENAI_TEXT_MODEL=gpt-5.5
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_IMAGE_SIZE=1024x1536
OPENAI_IMAGE_QUALITY=medium
```

Restart the server after changing `.env`.

## Run

From the repository root:

```bash
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Use the workflow

1. Select a scene reference and an identity reference.
2. Click **Analyze Scene**. The app uploads both files and writes `outputs/<project-id>/analysis.json`.
3. Review the JSON, then click **Build GPT Image 2 Prompt**. The prompt is written to `outputs/<project-id>/generation_prompt.txt`.
4. Click **Generate Image**. The app sends the original identity upload and the generated prompt to GPT Image 2 and saves `generated_image.png`.
5. Use the download links beside the JSON, prompt, and image cards to save artifacts from the browser.

If the analysis identifies a casual smartphone, selfie, snapshot, or social-media look, the app appends negative constraints that discourage DSLR bokeh, studio lighting, campaign retouching, and overly polished commercial rendering.

## Carousel mode

Choose a count from 1 to 10 and click **Generate Carousel**. For every variation, the backend:

- starts from the original identity reference;
- starts from the original `analysis.json` and `generation_prompt.txt`;
- keeps the scene DNA, camera, lighting, environment, outfit logic, palette, and processing aesthetic;
- varies only pose, expression, limb placement, framing, subject placement, and small camera/body angles;
- makes a separate GPT Image 2 request;
- never passes a prior output into the next request.

Each variation saves both an image (`carousel_01.png`, etc.) and the exact independent prompt used (`carousel_01_prompt.txt`, etc.).

## Output locations

Each browser workflow gets a random 12-character project ID:

```text
inputs/<project-id>/scene_reference.<ext>
inputs/<project-id>/identity_reference.<ext>
outputs/<project-id>/analysis.json
outputs/<project-id>/generation_prompt.txt
outputs/<project-id>/generated_image.png
outputs/<project-id>/carousel_01_prompt.txt
outputs/<project-id>/carousel_01.png
```

`inputs/` and `outputs/` contents are ignored by Git, except for their `.gitkeep` placeholders.

## Prompt customization

The three templates in `prompts/` are loaded from disk for each request, so you can edit them without changing Python code:

- `analyze_scene.txt`
- `convert_json_to_generation_prompt.txt`
- `carousel_variation_prompt.txt`

## Test

```bash
pytest -q
```

The tests use a fake OpenAI service and do not spend API credits.

## Troubleshooting

- **“OPENAI_API_KEY is not configured”**: create `.env`, add the key, and restart Uvicorn.
- **Model access error**: set the relevant model override in `.env` to a model available to your account.
- **Generation is slow**: reduce `OPENAI_IMAGE_QUALITY` or the carousel count.
- **A prompt/image is missing**: complete the workflow in order—analyze, build prompt, then generate.
- **Port 8000 is busy**: run `uvicorn app.main:app --reload --port 8001`.
