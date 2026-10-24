from dataclasses import replace

import pytest

from sportintel.modules.sources.domain.source import Source, normalize_domain
from sportintel.modules.sources.domain.values import SourceKind
from sportintel.platform.errors import ValidationFailed
from sportintel.platform.ids import new_id

OK = Source(
    id=new_id(),
    name="ge",
    domain="ge.globo.com",
    base_url="https://ge.globo.com",
    kind=SourceKind.RSS,
    feed_urls=["https://ge.globo.com/rss/ge/"],
    owner_group="globo",
)


def fields_of(source: Source) -> set[str]:
    with pytest.raises(ValidationFailed) as e:
        source.validate()
    return {d.field for d in e.value.details}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://WWW.Lance.com.br:443/x", "lance.com.br"),
        ("www.ge.globo.com", "ge.globo.com"),
        ("ge.globo.com/futebol", "ge.globo.com"),
        ("example.com:8080", "example.com"),
        ("https://Bücher.de/", "xn--bcher-kva.de"),
        ("  Example.COM.  ", "example.com"),
    ],
)
def test_normalize_domain(raw: str, expected: str) -> None:
    assert normalize_domain(raw) == expected


def test_valid_source_passes_and_domain_normalized() -> None:
    s = replace(OK, domain="WWW.ge.globo.com")
    s.validate()
    assert s.domain == "ge.globo.com"


def test_tier_may_be_null() -> None:
    replace(OK, tier=None).validate()


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"name": ""}, "name"),
        ({"name": "x" * 121}, "name"),
        ({"domain": "localhost"}, "domain"),
        ({"base_url": "ftp://ge.globo.com"}, "base_url"),
        ({"base_url": "https://evil.com"}, "base_url"),
        ({"feed_urls": []}, "feed_urls"),
        ({"feed_urls": ["javascript:alert(1)"]}, "feed_urls.0"),
        ({"feed_urls": ["https://ge.globo.com/" + "a" * 2050]}, "feed_urls.0"),
        ({"poll_interval_seconds": 59}, "poll_interval_seconds"),
        ({"poll_interval_seconds": 86401}, "poll_interval_seconds"),
        ({"min_request_gap_ms": 499}, "min_request_gap_ms"),
        ({"content_ttl_days": 31}, "content_ttl_days"),
        ({"parser_profile": "cbf_v9"}, "parser_profile"),
        ({"owner_group": "Globo Group"}, "owner_group"),
    ],
)
def test_rule_violations(overrides: dict[str, object], field: str) -> None:
    assert field in fields_of(replace(OK, **overrides))


def test_subdomain_base_url_allowed() -> None:
    replace(OK, domain="globo.com", base_url="https://ge.globo.com").validate()


def test_manual_source_rules() -> None:
    manual = replace(OK, kind=SourceKind.MANUAL, feed_urls=[])
    manual.validate()
    assert not manual.polls
    assert "feed_urls" in fields_of(replace(manual, feed_urls=["https://ge.globo.com/rss"]))


def test_sitemap_needs_feeds() -> None:
    assert "feed_urls" in fields_of(replace(OK, kind=SourceKind.SITEMAP, feed_urls=[]))


def test_page_and_calendar_need_a_url_and_their_own_profile() -> None:
    page = replace(OK, kind=SourceKind.HTML, feed_urls=[], parser_profile="telegram")
    assert "feed_urls" in fields_of(page)  # раньше молча принималось и ничего не собирало
    page = replace(page, feed_urls=["https://ge.globo.com/s/x"])
    page.validate(frozenset({"default", "telegram"}))
    for kind in (SourceKind.HTML, SourceKind.CALENDAR):
        assert "parser_profile" in fields_of(replace(page, kind=kind, parser_profile="default"))


def test_all_errors_reported_at_once() -> None:
    assert fields_of(replace(OK, name="", poll_interval_seconds=1)) == {
        "name",
        "poll_interval_seconds",
    }
