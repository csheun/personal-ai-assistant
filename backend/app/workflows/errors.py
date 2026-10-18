"""Domain errors. The HTTP layer maps them to status codes (see app/main.py)."""


class NotFound(Exception):
    """404: unknown conversation, run or approval."""


class WorkflowConflict(Exception):
    """409: the request doesn't fit the run's current state."""


class AssistantUnavailable(Exception):
    """503: the assistant can't respond right now."""
