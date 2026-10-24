from sportintel.composition.ai_load import advise, load_share, need_s_per_day, verdict
from sportintel.modules.editorial.application.autodraft import post_interval_s

TYPICAL = {"post": 50.0, "rewrite": 50.0, "translate": 20.0, "translate_post": 15.0, "brief": 45.0}
CFG = {
    "post_min": "MEDIUM",
    "post_mode": "llm",
    "translate_min": "MEDIUM",
    "brief_min": "HIGH",
    "brief_langs": ["en"],
    "llm_model": "qwen3:14b",
    "translation_model": "gemma3:12b",
}


def test_post_queue_runs_once_a_minute_for_a_slow_model() -> None:
    assert post_interval_s(50) == 60  # медленная модель — пост в минуту, не чаще
    assert post_interval_s(10) == 15  # быстрая — четыре за запуск
    assert post_interval_s(90) == 90


def test_many_sources_overload_the_model_and_advice_says_what_helps() -> None:
    """Много источников → 1000 важных событий в сутки: посты по минуте на каждое не успевают."""
    per_day = {"HIGH": 300.0, "MEDIUM": 700.0, "LOW": 2000.0}
    need = need_s_per_day(per_day, TYPICAL, 3.0, CFG)
    assert need["post_queue"] == 1000 * 60
    assert load_share(need) > 1
    assert verdict(load_share(need), 0) == "overloaded"

    noisy = [{"source_id": "s1", "source_name": "Spam FC", "events": 40}]
    out = advise(per_day, TYPICAL, 3.0, CFG, noisy)
    ids = [a["id"] for a in out]
    assert set(ids) == {
        "posts_high",
        "translate_high",
        "briefs_off",
        "posts_by_button",
        "smaller_model",
        "noisy_source",
    }
    # сильнее всего разгружает «ИИ только по кнопке», ручные советы — в конце
    assert ids[0] == "posts_by_button"
    assert ids[-2:] == ["smaller_model", "noisy_source"]
    high = next(a for a in out if a["id"] == "posts_high")
    assert high["apply"] == {"key": "drafts", "field": "auto_min_relevance", "value": "HIGH"}
    assert high["share_after"] < load_share(need)


def test_a_quiet_newsroom_is_fine() -> None:
    need = need_s_per_day({"HIGH": 10.0, "MEDIUM": 20.0}, TYPICAL, 3.0, CFG)
    assert verdict(load_share(need), 600) == "ok"
    assert verdict(load_share(need), 13 * 3600) == "overloaded"  # но очередь на полсуток — нет


def test_failing_calls_beat_low_load() -> None:
    # Ollama не запущена: вызовы падают мгновенно, нагрузка ≈ 0 — но это не «справляется»
    assert verdict(0.0, 0, failed_share=1.0) == "failing"
    assert verdict(0.0, 0, failed_share=0.1) == "ok"
    assert verdict(0.0, 0, failed_share=None) == "ok"  # вызовов ещё не было
