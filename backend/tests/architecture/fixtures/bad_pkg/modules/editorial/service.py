# Нарушение: editorial импортирует events.domain в обход public.py.
from bad_pkg.modules.events.domain.model import Event  # noqa: F401
