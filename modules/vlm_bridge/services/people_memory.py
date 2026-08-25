from __future__ import annotations

try:
    from modules.cognitive_memory.services.people_memory import PeopleMemory
except Exception:  # pragma: no cover
    class PeopleMemory:  # type: ignore
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def __getattr__(self, name):
            raise AttributeError(name)

__all__ = ["PeopleMemory"]
