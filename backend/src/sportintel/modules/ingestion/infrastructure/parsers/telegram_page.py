"""Страница t.me/s/<канал> целиком — для превью канала «как в Telegram» во вкладке «Автопостинг».

В отличие от профиля telegram (плоский текст для новостей), здесь сохраняется разметка поста
(Bot API HTML: b, i, u, s, a, code, pre, blockquote, tg-spoiler), альбомы, превью ссылок,
реакции, просмотры. Скрипты не исполняются (stdlib HTMLParser); UI ещё раз чистит HTML.
"""

import re
from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
from typing import Any

_BG_URL = re.compile(r"background-image:url\('([^']+)'\)")
# тег t.me → тег Bot API HTML; остальные теги внутри текста отбрасываются, текст остаётся
_KEEP = {
    "b": "b", "strong": "b", "i": "i", "em": "i", "u": "u", "s": "s", "del": "s",
    "code": "code", "pre": "pre", "blockquote": "blockquote", "a": "a",
}  # fmt: skip
_VOID = {"br", "img", "hr", "wbr"}
_REACTION = re.compile(r"(.*?)(\d[\d.,]*[KM]?)")  # «🔥12», «⭐1», «❤1.2K»


@dataclass
class _Post:
    post: str
    html: str = ""
    published: str | None = None
    edited: bool = False
    views: str = ""
    author: str = ""
    forwarded_from: str = ""
    photos: list[str] = field(default_factory=list)
    video_thumb: str | None = None
    sticker: str | None = None
    unsupported: bool = False
    reactions: list[dict[str, str]] = field(default_factory=list)
    link: dict[str, str] = field(default_factory=dict)
    document: dict[str, str] = field(default_factory=dict)


def _bg(attrs: dict[str, str | None]) -> str | None:
    m = _BG_URL.search(attrs.get("style") or "")
    if not m:
        return None
    url = m.group(1)
    return "https:" + url if url.startswith("//") else url


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.avatar: str | None = None
        self.description = ""
        self.counters: dict[str, str] = {}
        self.posts: list[_Post] = []
        self._cap: tuple[str, str, int] | None = None  # (поле, тег, глубина) — сбор текста
        self._buf = ""
        self._text = 0  # глубина div внутри текста поста
        self._open: list[tuple[str, bool, bool]] = []  # теги в тексте: (тег, вынесен, эмодзи)
        self._reply = 0  # глубина div цитаты-ответа: её текст — не текст поста
        self._photo_icon = False
        self._counter_value = ""

    # --- сбор простого текста элемента (название, просмотры, подписи) ---
    def _start_cap(self, name: str, tag: str) -> None:
        self._cap, self._buf = (name, tag, 1), ""

    def _end_cap(self) -> None:
        if self._cap is None:
            return
        name, value = self._cap[0], " ".join(self._buf.split())
        self._cap = None
        post = self.posts[-1] if self.posts else None
        if name == "title":
            self.title = value
        elif name == "description":
            self.description = value
        elif name == "counter_value":
            self._counter_value = value
        elif name == "counter_type":
            self.counters[value] = self._counter_value
        elif post is None:
            return
        elif name == "reaction":
            m = _REACTION.fullmatch(value.replace(" ", ""))
            if m:
                post.reactions.append({"emoji": m.group(1) or "⭐", "count": m.group(2)})
        elif name in {"views", "author", "forwarded_from"}:
            setattr(post, name, value)
        elif name == "meta":
            post.edited = "edited" in value
        elif name.startswith("link_"):
            post.link[name[5:]] = value
        elif name.startswith("doc_"):
            post.document[name[4:]] = value

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if self._text:
            self._text_tag(tag, a, cls)
            return
        if self._cap:
            if tag == self._cap[1]:
                self._cap = (self._cap[0], tag, self._cap[2] + 1)
            if tag == "i" and "icon-telegram-stars" in cls:
                self._buf += "⭐"
            elif tag == "time" and a.get("datetime") and self.posts:
                self.posts[-1].published = self.posts[-1].published or a["datetime"]
            return
        if self._reply and tag == "div":
            self._reply += 1
            return
        if tag == "div" and a.get("data-post") and "tgme_widget_message" in cls:
            post = "" if "service_message" in cls else a["data-post"] or ""
            self.posts.append(_Post(post=post))
            return
        if not self.posts:
            self._header(tag, a, cls)
            return
        p = self.posts[-1]
        if tag == "div" and "tgme_widget_message_text" in cls:
            self._text = 1
        elif tag in {"div", "a"} and "tgme_widget_message_reply" in cls:
            self._reply = 1 if tag == "div" else 0
        elif tag == "a" and "tgme_widget_message_photo_wrap" in cls:
            url = _bg(a)
            if url:
                p.photos.append(url)
        elif "tgme_widget_message_sticker_wrap" in cls:
            p.sticker = ""  # картинка стикера — следующий <img> (или фон <i>)
        elif p.sticker == "" and tag == "img":
            p.sticker = a.get("src")
        elif p.sticker == "" and tag == "i" and "tgme_widget_message_sticker" in cls:
            p.sticker = _bg(a)
        elif tag == "i" and "tgme_widget_message_video_thumb" in cls:
            p.video_thumb = _bg(a)
        elif tag == "i" and {"link_preview_image", "link_preview_right_image"} & set(cls):
            p.link["image"] = _bg(a) or ""
        elif tag == "div" and "message_media_not_supported" in cls:
            p.unsupported = True
        elif tag == "time" and a.get("datetime") and p.published is None:
            p.published = a["datetime"]
        else:
            for c, name in (
                ("tgme_widget_message_views", "views"),
                ("tgme_widget_message_from_author", "author"),
                ("tgme_widget_message_forwarded_from_name", "forwarded_from"),
                ("tgme_widget_message_meta", "meta"),
                ("tgme_reaction", "reaction"),
                ("link_preview_site_name", "link_site"),
                ("link_preview_title", "link_title"),
                ("link_preview_description", "link_description"),
                ("tgme_widget_message_document_title", "doc_title"),
                ("tgme_widget_message_document_extra", "doc_extra"),
            ):
                if c in cls:
                    self._start_cap(name, tag)
                    break
            if tag == "a" and "tgme_widget_message_link_preview" in cls:
                p.link["url"] = a.get("href") or ""

    def _header(self, tag: str, a: dict[str, str | None], cls: list[str]) -> None:
        if tag == "div" and "tgme_channel_info_header_title" in cls:
            self._start_cap("title", "div")
        elif tag == "div" and "tgme_channel_info_description" in cls:
            self._start_cap("description", "div")
        elif tag == "span" and "counter_value" in cls:
            self._start_cap("counter_value", "span")
        elif tag == "span" and "counter_type" in cls:
            self._start_cap("counter_type", "span")
        elif tag == "img" and self._photo_icon and self.avatar is None:
            self.avatar = a.get("src")
        self._photo_icon = tag == "i" and "tgme_page_photo_image" in cls

    def _text_tag(self, tag: str, a: dict[str, str | None], cls: list[str]) -> None:
        p = self.posts[-1]
        if tag == "br":
            p.html += "\n"
            return
        if tag in _VOID:
            return
        if tag == "div":
            self._text += 1
        emoji = tag == "i" and "emoji" in cls
        in_emoji = any(e for _, _, e in self._open)
        # картинка-эмодзи: <i class="emoji"><b>⚽</b></i> — нужен только сам символ
        keep = tag in _KEEP and not emoji and not in_emoji
        out = ""
        if tag == "span" and "tg-spoiler" in cls:
            out = "<tg-spoiler>"
        elif keep and tag == "a":
            href = a.get("href") or ""
            if href.startswith(("http://", "https://", "tg://")):
                out = f'<a href="{escape(href)}">'
        elif keep:
            out = f"<{_KEEP[tag]}>"
        p.html += out
        self._open.append((tag, bool(out), emoji))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._text:
            if tag in _VOID:
                return
            if tag == "div":
                self._text -= 1
                if not self._text:
                    self._open.clear()
                    return
            if self._open:
                opened, kept, _ = self._open.pop()
                if kept:
                    closing = "tg-spoiler" if opened == "span" else _KEEP.get(opened, opened)
                    self.posts[-1].html += f"</{closing}>"
            return
        if self._cap and tag == self._cap[1]:
            name, t, depth = self._cap
            if depth == 1:
                self._end_cap()
            else:
                self._cap = (name, t, depth - 1)
            return
        if self._reply and tag == "div":
            self._reply -= 1

    def handle_data(self, data: str) -> None:
        if self._text:
            self.posts[-1].html += escape(data, quote=False)
        elif self._cap:
            self._buf += data


def parse_channel_page(body: bytes) -> dict[str, Any]:
    """Шапка канала и сообщения (старые сверху, как на странице); служебные пропущены."""
    page = _Page()
    page.feed(body.decode("utf-8", errors="replace"))
    return {
        "title": page.title,
        "avatar_url": page.avatar,
        "description": page.description,
        "subscribers": page.counters.get("subscribers") or page.counters.get("subscriber"),
        "posts": [
            {
                "url": f"https://t.me/{p.post}",
                "html": p.html.strip(),
                "published_at": p.published,
                "edited": p.edited,
                "views": p.views or None,
                "author": p.author or None,
                "forwarded_from": p.forwarded_from or None,
                "photos": p.photos,
                "video_thumb": p.video_thumb,
                "sticker": p.sticker or None,
                "unsupported": p.unsupported and not (p.photos or p.video_thumb or p.sticker),
                "reactions": p.reactions,
                "link_preview": p.link or None,
                "document": p.document or None,
            }
            for p in page.posts
            if "/" in p.post
        ],
    }
