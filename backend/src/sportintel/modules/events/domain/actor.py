import uuid
from dataclasses import dataclass

from sportintel.modules.events.domain.values import Role


@dataclass(frozen=True)
class Actor:
    id: uuid.UUID | None
    role: Role | None

    @property
    def is_system(self) -> bool:
        return self.id is None


SYSTEM = Actor(None, None)
