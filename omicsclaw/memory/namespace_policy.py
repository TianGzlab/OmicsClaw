"""Namespace + version policy — see docs/CONTEXT.md.

Two independent classifications of a Memory URI:

  resolve_namespace(uri, current=N)
    → "__shared__" if uri matches a SHARED_PREFIXES entry, else N

  should_version(uri)
    → True if uri matches a VERSIONED_PREFIXES entry, else False

Prefix semantics for both tables (`(domain, prefix)` tuples):
  - empty prefix matches the whole domain (e.g., all of preference://*)
  - non-empty prefix matches exact path OR "<prefix>/..." sub-paths
  - "kh" does NOT match "khaki" — matching is by path-segment, not raw startswith
"""

from omicsclaw.memory.uri import MemoryURI

SHARED = "__shared__"

SHARED_PREFIXES: tuple[tuple[str, str], ...] = (
    ("core", "agent"),
    ("core", "kh"),
    ("core", "my_user_default"),
)

VERSIONED_PREFIXES: tuple[tuple[str, str], ...] = (
    ("core", "agent"),
    ("core", "my_user"),
    ("preference", ""),
)


def _matches_prefix(uri: MemoryURI, domain: str, prefix: str) -> bool:
    if uri.domain != domain:
        return False
    if prefix == "":
        return True
    return uri.path == prefix or uri.path.startswith(prefix + "/")


def _matches_any(uri: MemoryURI, prefixes: tuple[tuple[str, str], ...]) -> bool:
    return any(_matches_prefix(uri, d, p) for d, p in prefixes)


def resolve_namespace(uri: MemoryURI, *, current: str) -> str:
    return SHARED if _matches_any(uri, SHARED_PREFIXES) else current


def should_version(uri: MemoryURI) -> bool:
    return _matches_any(uri, VERSIONED_PREFIXES)
