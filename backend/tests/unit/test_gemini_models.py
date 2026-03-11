from __future__ import annotations

def test_model_registry_reads_override_settings(monkeypatch, test_settings):
    test_settings.gemini_live_model = "live-override"
    test_settings.gemini_fast_text_model = "fast-override"
    test_settings.gemini_reasoning_model = "reasoning-override"
    test_settings.gemini_image_model = "image-override"
    test_settings.gemini_tts_model = "tts-override"
    test_settings.gemini_premium_tts_model = "premium-override"

    import config

    config.get_settings.cache_clear()
    monkeypatch.setattr(config, "get_settings", lambda: test_settings)

    import services.gemini.models as models_mod
    monkeypatch.setattr(models_mod, "get_settings", lambda: test_settings)

    models = models_mod.get_gemini_models()

    assert models.live_audio == "live-override"
    assert models.fast_text == "fast-override"
    assert models.reasoning == "reasoning-override"
    assert models.image_generation == "image-override"
    assert models.tts == "tts-override"
    assert models.premium_tts == "premium-override"


def test_services_use_registry_model_constants(patch_settings):
    import services.gemini.models as models_mod
    import services.gemini.agent as agent_mod
    import services.gemini.audio as audio_mod
    import services.gemini.edit_voice as edit_voice_mod
    import services.gemini.image as image_mod
    import services.gemini.interleaved as interleaved_mod
    import services.gemini.live as live_mod
    import services.gemini.reasoning as reasoning_mod
    import services.gemini.tts as tts_mod
    import services.gemini.voice_agent as voice_agent_mod

    assert agent_mod.MODEL == models_mod.MODELS.fast_text
    assert audio_mod.MODEL == models_mod.MODELS.reasoning
    assert edit_voice_mod._LIVE_MODEL == models_mod.MODELS.live_audio
    assert edit_voice_mod._TEXT_MODEL == models_mod.MODELS.fast_text
    assert image_mod.MODEL == models_mod.MODELS.image_generation
    assert image_mod._TEXT_MODEL == models_mod.MODELS.fast_text
    assert interleaved_mod.MODEL == models_mod.MODELS.image_generation
    assert live_mod.MODEL == models_mod.MODELS.live_audio
    assert reasoning_mod.MODEL == models_mod.MODELS.reasoning
    assert tts_mod.MODEL == models_mod.MODELS.tts
    assert voice_agent_mod.MODEL == models_mod.MODELS.live_audio
