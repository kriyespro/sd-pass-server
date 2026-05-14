from apps.logs.models import LogEntry


def append_project_log(project, kind: str, message: str) -> None:
    max_len = 100_000
    text = message if len(message) <= max_len else message[:max_len] + '\n…(truncated)'
    LogEntry.objects.create(project=project, kind=kind, message=text)
