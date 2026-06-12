const state = { projectId: null, uploadedSignature: null };
const $ = (id) => document.getElementById(id);
const sceneInput = $("sceneInput");
const identityInput = $("identityInput");

function setStatus(message, type = "idle") {
  $("statusText").textContent = message;
  $("statusBar").className = `status-bar ${type}`;
}

function setBusy(button, busy, label) {
  button.disabled = busy;
  button.classList.toggle("busy", busy);
  if (label) button.dataset.defaultLabel ||= button.innerHTML;
  button.innerHTML = busy ? `${label} <span>···</span>` : (button.dataset.defaultLabel || button.innerHTML);
}

function showPreview(input, container) {
  const file = input.files[0];
  container.innerHTML = file ? `<img src="${URL.createObjectURL(file)}" alt="Selected reference preview">` : "<span>+</span>";
  state.projectId = null;
  state.uploadedSignature = null;
  $("promptBtn").disabled = true;
  $("generateBtn").disabled = true;
  $("carouselBtn").disabled = true;
}

sceneInput.addEventListener("change", () => showPreview(sceneInput, $("scenePreview")));
identityInput.addEventListener("change", () => showPreview(identityInput, $("identityPreview")));

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status})`);
  return payload;
}

async function ensureProject() {
  if (!sceneInput.files[0] || !identityInput.files[0]) throw new Error("Select both a scene reference and an identity reference.");
  const signature = `${sceneInput.files[0].name}:${sceneInput.files[0].size}|${identityInput.files[0].name}:${identityInput.files[0].size}`;
  if (state.projectId && state.uploadedSignature === signature) return state.projectId;
  const form = new FormData();
  form.append("scene_reference", sceneInput.files[0]);
  form.append("identity_reference", identityInput.files[0]);
  const project = await api("/api/projects", { method: "POST", body: form });
  state.projectId = project.project_id;
  state.uploadedSignature = signature;
  return state.projectId;
}

function jsonRequest(body) {
  return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

function exposeDownload(id, url, filename) {
  const link = $(id);
  link.href = url;
  link.download = filename;
  link.classList.remove("hidden");
}

function addImage(url, downloadUrl, name) {
  const gallery = $("gallery");
  gallery.classList.remove("empty-gallery");
  if (gallery.querySelector(".gallery-placeholder")) gallery.innerHTML = "";
  const card = document.createElement("div");
  card.className = "image-card";
  card.innerHTML = `<img src="${url}?t=${Date.now()}" alt="Generated recreation"><a href="${downloadUrl}" download="${name}">Download ↓</a>`;
  gallery.prepend(card);
}

$("analyzeBtn").addEventListener("click", async () => {
  const button = $("analyzeBtn");
  try {
    setBusy(button, true, "Analyzing scene");
    setStatus("Uploading references and extracting the original scene blueprint…", "working");
    const projectId = await ensureProject();
    const result = await api("/api/analyze", jsonRequest({ project_id: projectId }));
    const output = $("analysisOutput");
    output.textContent = JSON.stringify(result.analysis, null, 2);
    output.classList.remove("empty");
    exposeDownload("analysisDownload", result.download_url, "analysis.json");
    $("promptBtn").disabled = false;
    setStatus("Scene analysis saved as analysis.json.", "success");
  } catch (error) { setStatus(error.message, "error"); }
  finally { setBusy(button, false); }
});

$("promptBtn").addEventListener("click", async () => {
  const button = $("promptBtn");
  try {
    setBusy(button, true, "Building prompt");
    setStatus("Converting the forensic blueprint into a generation prompt…", "working");
    const result = await api("/api/build-prompt", jsonRequest({ project_id: state.projectId }));
    const output = $("promptOutput");
    output.textContent = result.prompt;
    output.classList.remove("empty");
    exposeDownload("promptDownload", result.download_url, "generation_prompt.txt");
    $("generateBtn").disabled = false;
    $("carouselBtn").disabled = false;
    setStatus("Generation prompt saved and identity safeguards applied.", "success");
  } catch (error) { setStatus(error.message, "error"); }
  finally { setBusy(button, false); button.disabled = false; }
});

$("generateBtn").addEventListener("click", async () => {
  const button = $("generateBtn");
  try {
    setBusy(button, true, "Generating image");
    setStatus("GPT Image 2 is creating a fresh image from the original identity reference…", "working");
    const result = await api("/api/generate", jsonRequest({ project_id: state.projectId }));
    addImage(result.image_url, result.download_url, "generated_image.png");
    setStatus("Generated image saved to the project output folder.", "success");
  } catch (error) { setStatus(error.message, "error"); }
  finally { setBusy(button, false); button.disabled = false; }
});

$("carouselBtn").addEventListener("click", async () => {
  const button = $("carouselBtn");
  const count = Number($("carouselCount").value);
  try {
    setBusy(button, true, "Generating carousel");
    setStatus(`Generating ${count} independent variations from the original blueprint…`, "working");
    const result = await api("/api/carousel", jsonRequest({ project_id: state.projectId, count }));
    result.images.forEach((image, index) => addImage(image.image_url, image.download_url, `carousel_${index + 1}.png`));
    setStatus(`${result.images.length} fresh carousel images saved. No generated image was reused.`, "success");
  } catch (error) { setStatus(error.message, "error"); }
  finally { setBusy(button, false); button.disabled = false; }
});

api("/api/health").then((health) => {
  const status = $("apiStatus");
  status.classList.add(health.api_key_configured ? "ready" : "missing");
  status.querySelector("span").textContent = health.api_key_configured ? "OpenAI API ready" : "Add OPENAI_API_KEY to .env";
}).catch(() => { $("apiStatus").querySelector("span").textContent = "Backend unavailable"; });
