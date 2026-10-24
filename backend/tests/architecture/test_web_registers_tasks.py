"""Web ставит задачи сам: каждая задача каталога должна быть зарегистрирована в своей очереди.

Иначе procrastinate кладёт незарегистрированную задачу в очередь `default`, которую никто не слушает.
"""

import sportintel.main  # noqa: F401 — как при старте web
from sportintel.platform import jobs


def test_tasks_enqueued_by_web_are_registered_in_their_queues() -> None:
    assert jobs.JOBS.tasks["editorial.build_brief"].queue == "ai"
    assert jobs.JOBS.tasks["intelligence.relink_entities"].queue != "default"
    assert jobs.JOBS.tasks["events.refresh_event"].queue != "default"
