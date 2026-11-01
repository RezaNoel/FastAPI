"""Plain-text counters in the Prometheus exposition format."""

from collections import Counter
from threading import Lock

from app import __version__


class Metrics:
    def __init__(self) -> None:
        self._requests: Counter[tuple[str, str, str]] = Counter()
        self._lock = Lock()

    def observe(self, method: str, path: str, status: int) -> None:
        with self._lock:
            self._requests[(method, path, str(status))] += 1

    def render(self) -> str:
        lines = [
            "# HELP grove_app_info Grove build information.",
            "# TYPE grove_app_info gauge",
            f'grove_app_info{{version="{__version__}"}} 1',
            "# HELP grove_http_requests_total HTTP requests handled by Grove.",
            "# TYPE grove_http_requests_total counter",
        ]
        with self._lock:
            items = sorted(self._requests.items())
        for (method, path, status), count in items:
            lines.append(
                f'grove_http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}'
            )
        return "\n".join(lines) + "\n"


metrics = Metrics()
