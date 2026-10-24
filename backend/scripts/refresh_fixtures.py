"""Обновить фикстуры профиля и показать расхождения с expected.json (BE-T1.8).

    uv run python scripts/refresh_fixtures.py default https://ge.globo.com/…/x.ghtml …

Запускается вручную (раз в неделю, ARCHITECTURE §31.2). Страницы скачиваются через
SafeHttpFetcher; из HTML удаляются <script> (кроме JSON-LD), <style> и комментарии.
"""

import asyncio
import json
import re
import sys
from pathlib import Path

from sportintel.modules.ingestion.jobs import extract_with_profile
from sportintel.platform.safe_fetch import FetchRequest, SafeHttpFetcher

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "sources"
UA = "SportIntelBot/1.0 (+fixture refresh)"


def strip(html: str) -> str:
    html = re.sub(
        r"<script(?![^>]*application/ld\+json)[^>]*>.*?</script>", "", html, flags=re.S | re.I
    )
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.S | re.I)
    return re.sub(r"<!--.*?-->", "", html, flags=re.S)


async def main(profile: str, urls: list[str]) -> int:
    folder = FIXTURES / profile / "pages"
    folder.mkdir(parents=True, exist_ok=True)
    expected_path = FIXTURES / profile / "expected.json"
    expected = json.loads(expected_path.read_text()) if expected_path.exists() else {}
    fetcher, changed = SafeHttpFetcher(UA), 0
    for url in urls:
        resp = await fetcher.fetch(FetchRequest(url, "html"))
        name = re.sub(r"[^a-z0-9]+", "_", url.lower().split("//", 1)[-1])[:80].strip("_") + ".html"
        (folder / name).write_text(
            strip(resp.body.decode("utf-8", errors="replace")), encoding="utf-8"
        )
        page = extract_with_profile((folder / name).read_bytes(), url, profile)
        got = {
            "url": url,
            "title": page.title,
            "published_at": page.published_at.isoformat() if page.published_at else None,
            "lead_prefix": (page.description or page.text or "")[:50],
            "image_url": page.image_url,
        }
        key = f"pages/{name}"
        old = expected.get(key)
        if old != got:
            changed += 1
            print(f"--- {key}\n  было: {old}\n  стало: {got}")
        expected[key] = got
    expected_path.write_text(
        json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"готово: {len(urls)} страниц, изменений {changed}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(asyncio.run(main(sys.argv[1], sys.argv[2:])))
