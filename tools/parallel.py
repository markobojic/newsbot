"""Run one call per source in parallel and collect results and failures separately.

Plumbing only: it never decides what a failure MEANS. The adapter does that
(partial results + failed sources, 5.3).
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar

from errors import ToolError

T = TypeVar("T")


def fetch_all(
    sources: list[str], fetch: Callable[[str], T]
) -> tuple[dict[str, T], dict[str, ToolError]]:
    """Call fetch(source) for every source at once; return (results, failures).

    Only ToolError is collected as a failure. Anything else is a bug and is raised,
    so it reaches the loop's safety net instead of looking like an outage.
    """
    results: dict[str, T] = {}
    failures: dict[str, ToolError] = {}
    # Threads, because the work is waiting on the network. Worst case is now one
    # slow feed (~33s with retries), not the sum of all of them.
    with ThreadPoolExecutor(max_workers=max(len(sources), 1)) as pool:
        futures = {source: pool.submit(fetch, source) for source in sources}
        for source, future in futures.items():
            try:
                results[source] = future.result()
            except ToolError as err:
                failures[source] = err
    return results, failures
