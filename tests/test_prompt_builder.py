from app.prompt_builder import apply_generation_guards, build_carousel_prompt, needs_casual_negative_prompt


def test_casual_camera_adds_negative_constraints():
    analysis = {"camera": {"appearance": "casual smartphone handheld snapshot"}}
    prompt = apply_generation_guards("IDENTITY LOCK", analysis)
    assert needs_casual_negative_prompt(analysis)
    assert "Avoid a professional DSLR" in prompt
    assert "only identity source" in prompt


def test_dslr_blueprint_does_not_add_casual_constraints():
    analysis = {"camera": {"appearance": "controlled medium-format editorial photograph"}}
    prompt = apply_generation_guards("IDENTITY LOCK", analysis)
    assert not needs_casual_negative_prompt(analysis)
    assert "Avoid a professional DSLR" not in prompt


def test_carousel_prompt_requires_original_sources():
    prompt = build_carousel_prompt("BASE", {"camera": {}}, "Never use a previous image.", 2, 5)
    assert "image 2 of 5" in prompt
    assert "original identity upload" not in prompt  # implementation detail stays out of model prose
    assert "any previously generated image" in prompt


def test_carousel_does_not_duplicate_existing_source_guards():
    base = apply_generation_guards("BASE", {"camera": {}})
    prompt = build_carousel_prompt(base, {"camera": {}}, "Fresh variation.", 1, 3)
    assert prompt.count("SOURCE SEPARATION RULES") == 1
