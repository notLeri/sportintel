from tests.factories import make_article, make_event, make_source

from sportintel.modules.events import public as events
from sportintel.modules.sources.domain.values import SourceTier
from sportintel.platform.db import Database


async def test_pack_orders_by_tier(db: Database) -> None:
    async with db.uow() as u:
        b = await make_source(u, domain="evp-b.example.com", tier=SourceTier.B)
        off = await make_source(u, domain="evp-o.example.com", tier=SourceTier.OFFICIAL)
        a1 = await make_article(u, b, title="Matéria B", lead="Lead B.")
        a2 = await make_article(u, off, title="Nota oficial", lead="Lead O.")
        ev = await make_event(u, [a1, a2])
        pack = await events.build_evidence_pack(u, ev.id, 12)
    assert [f.text for f in pack.fragments][:2] == ["Nota oficial. Lead O.", "Matéria B. Lead B."]
    assert pack.title == "Matéria B"
