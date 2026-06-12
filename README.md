# Image Recreator

A private, responsive Streamlit app for recreating the visual blueprint of a scene with a separate identity reference. It works from a phone or laptop through a Streamlit web link and keeps the scene and identity sources strictly separated.

## Workflow

1. Upload a **scene reference image**, or paste a direct image/Pinterest-style page URL.
2. Upload an **identity reference image**.
3. Click **Analyze Scene** to create `analysis.json` from the scene only.
4. Click **Build Prompt** to create `generation_prompt.txt`.
5. Click **Generate Image** to generate from the original identity image plus the scene-derived prompt.
6. Use **Carousel Mode** to make up to 10 independent variations from the original identity and original blueprint.

The scene image is never passed to the image-generation call. The identity image is the only image passed to generation. Carousel outputs are never used as inputs for later outputs.

## Features

- Single `app.py` Streamlit application
- Responsive layout for mobile and desktop
- Password gate using `APP_PASSWORD`
- Local `.env` support
- Streamlit Community Cloud secrets support
- Scene upload or server-side image URL download
- Direct JPG, JPEG, PNG, and WEBP support
- Pinterest-style/Open Graph page image extraction where available
- Binary image validation, download limits, redirect limits, and private-network URL blocking
- Editable prompt templates in `prompts/`
- JSON, prompt, and image previews and downloads
- Project-scoped files in `inputs/` and `outputs/`
- Casual smartphone negative-prompt safeguards

## Project structure

```text
image-recreator/
├── app.py                              # Streamlit UI and workflow
├── app/
│   ├── file_utils.py                   # Local storage and safe URL downloads
│   ├── openai_client.py                # OpenAI Responses and image APIs
│   └── prompt_builder.py               # Source guards and carousel prompts
├── prompts/
│   ├── analyze_scene.txt
│   ├── convert_json_to_generation_prompt.txt
│   └── carousel_variation_prompt.txt
├── inputs/                             # Saved source images, by project ID
├── outputs/                            # JSON, prompts, and generated images
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
├── .env.example
└── requirements.txt
```

## Run locally

### 1. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure local secrets

Copy the example file:

```bash
cp .env.example .env
```

Set at least these two values:

```dotenv
OPENAI_API_KEY=sk-your-real-key
APP_PASSWORD=choose-a-strong-private-password
```

Optional model/output overrides are already documented in `.env.example`.

### 4. Start Streamlit

```bash
streamlit run app.py
```

Open the local URL shown by Streamlit, normally [http://localhost:8501](http://localhost:8501). To use the app from a phone on the same Wi-Fi network, open the network URL printed by Streamlit and allow the port through the computer firewall if necessary.

## Using a scene image URL

Paste a URL into **Scene image URL** and leave the scene uploader empty. When **Analyze Scene** is clicked, the server:

1. validates the URL and blocks private/local/reserved network destinations;
2. follows a limited number of validated redirects;
3. downloads the response locally rather than hotlinking it;
4. accepts a direct image, or extracts `og:image`/`twitter:image` from a page such as a Pinterest pin page;
5. validates the downloaded binary as JPG, PNG, or WEBP;
6. saves it as `inputs/<project-id>/scene_reference.<ext>` before analysis.

If a site prevents server-side downloads, use the direct image address or download the image to your device and use the uploader. If both an upload and URL are supplied, the uploaded file takes precedence.

## Password protection

The app will not render the workflow until `APP_PASSWORD` is configured and entered correctly. This is a lightweight password gate suitable for private personal use; do not treat it as enterprise authentication or multi-user authorization.

Local configuration uses `.env`. Deployed configuration uses Streamlit secrets. Secret files are excluded from Git.

## Deploy to Streamlit Community Cloud

### 1. Push the project to GitHub

A private GitHub repository is recommended. Confirm that `.env` and `.streamlit/secrets.toml` are not committed.

### 2. Create the Streamlit app

1. Sign in at [share.streamlit.io](https://share.streamlit.io/).
2. Click **Create app**.
3. Select the GitHub repository and branch.
4. Set the main file path to `app.py`.
5. Open **Advanced settings** before deploying.

### 3. Add Streamlit secrets

Paste the following into the app's **Secrets** field:

```toml
OPENAI_API_KEY = "sk-your-real-key"
APP_PASSWORD = "choose-a-strong-private-password"

OPENAI_VISION_MODEL = "gpt-5.5"
OPENAI_TEXT_MODEL = "gpt-5.5"
OPENAI_IMAGE_MODEL = "gpt-image-2"
OPENAI_IMAGE_SIZE = "1024x1536"
OPENAI_IMAGE_QUALITY = "medium"
```

Only `OPENAI_API_KEY` and `APP_PASSWORD` are required. The rest override defaults.

### 4. Deploy and open the link

Click **Deploy**. Once the build finishes, open the generated `https://<app-name>.streamlit.app` link from your phone or laptop and enter `APP_PASSWORD`.

### Important storage note

Streamlit Community Cloud's local filesystem is ephemeral. Files are saved under `inputs/` and `outputs/` while the app instance is running, but they may disappear after a reboot, redeploy, or sleep cycle. Use the download buttons to keep important JSON, prompts, and images. For permanent server-side history, add object storage later.

## Carousel mode

Set **Carousel count** from 1 to 10 and click **Carousel Mode**. Each image:

- receives the original identity upload as its only image reference;
- receives the original scene analysis and generation prompt;
- preserves scene DNA, location type, camera, lighting, processing, outfit logic, palette, and aesthetic;
- changes pose, micro-expression, limb placement, framing, placement, and small camera/body angles;
- is generated with a separate API call;
- never uses an earlier generated image.

The app saves each image and its exact prompt:

```text
outputs/<project-id>/carousel_01.png
outputs/<project-id>/carousel_01_prompt.txt
```

## Output files

A browser session receives a random project ID. Artifacts are stored as:

```text
inputs/<project-id>/scene_reference.<ext>
inputs/<project-id>/identity_reference.<ext>
outputs/<project-id>/analysis.json
outputs/<project-id>/generation_prompt.txt
outputs/<project-id>/generated_image.png
outputs/<project-id>/carousel_01_prompt.txt
outputs/<project-id>/carousel_01.png
```

## Edit prompt templates

The app loads these files from disk each time the corresponding action runs:

- `prompts/analyze_scene.txt`
- `prompts/convert_json_to_generation_prompt.txt`
- `prompts/carousel_variation_prompt.txt`

You can edit them without changing the Streamlit code.

## Tests

Install development dependencies and run:

```bash
pip install -r requirements-dev.txt
pytest -q
```

The tests validate prompt guards, supported image signatures, direct URL downloads, Pinterest-style Open Graph extraction, invalid responses, and private-network URL blocking without spending OpenAI credits.

## Troubleshooting

- **APP_PASSWORD is not configured**: add it to `.env` locally or the deployed app's Streamlit secrets.
- **OPENAI_API_KEY is not configured**: add the key to the same location and restart/redeploy.
- **The URL could not be downloaded**: try the direct image address or upload the image from your device.
- **The page did not expose a downloadable image**: Pinterest or the source site may have changed its page metadata or blocked automated requests.
- **The selected scene changed**: run **Analyze Scene** again before building or generating.
- **Model access error**: change the relevant model override to one available to your OpenAI account.
- **Images disappeared after deployment restarted**: Community Cloud storage is temporary; retrieve important artifacts with the download buttons.
