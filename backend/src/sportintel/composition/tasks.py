"""Регистрация всех фоновых задач (CONV §10). Импортируют worker и web.

Web тоже ставит задачи (бриф по кнопке, правка справочника): незарегистрированная задача
ушла бы в очередь `default`, которую никто не слушает.
"""

from sportintel.composition import health_watch as _health_watch  # noqa: F401
from sportintel.modules.analytics import jobs as _analytics_jobs  # noqa: F401
from sportintel.modules.editorial import jobs as _editorial_jobs  # noqa: F401
from sportintel.modules.events import jobs as _events_jobs  # noqa: F401
from sportintel.modules.identity import jobs as _identity_jobs  # noqa: F401
from sportintel.modules.ingestion import jobs as _ingestion_jobs  # noqa: F401
from sportintel.modules.intelligence import jobs as _intelligence_jobs  # noqa: F401
from sportintel.modules.sources import jobs as _sources_jobs  # noqa: F401
from sportintel.platform import reconcile as _platform_tasks  # noqa: F401
