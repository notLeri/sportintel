from sportintel.modules.editorial.domain.limits import max_length, plain_length, strip_citations


def test_plain_length_ignores_tags_entities_and_markers() -> None:
    assert plain_length("<b>Olá</b> &amp; mundo [1] [12]") == len("Olá & mundo")
    assert strip_citations("Texto [1].") == "Texto."
    assert (max_length(True), max_length(False)) == (1024, 4096)


def test_plain_length_matches_shared_fixture() -> None:
    import json
    from pathlib import Path

    cases = json.loads(
        (
            Path(__file__).resolve().parents[4] / "fixtures" / "telegram" / "length_cases.json"
        ).read_text()
    )
    assert [(c["html"], plain_length(c["html"])) for c in cases] == [
        (c["html"], c["length"]) for c in cases
    ]
