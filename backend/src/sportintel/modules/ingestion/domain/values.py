from enum import StrEnum


class ArticleState(StrEnum):
    DISCOVERED = "discovered"
    EXTRACTED = "extracted"
    ENRICHED = "enriched"
    CLUSTERED = "clustered"
    FAILED = "failed"
