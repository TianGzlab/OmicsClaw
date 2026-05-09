"""MemoryURI value object — see docs/CONTEXT.md → "Memory URI"."""

from dataclasses import dataclass

DEFAULT_DOMAIN = "core"
SCHEME_SEPARATOR = "://"


@dataclass(frozen=True, slots=True)
class MemoryURI:
    """Stable identifier for a memory location, independent of row id.

    Invariants (enforced in ``__post_init__``):
      - ``domain`` is non-empty, contains no ``://``, no control chars
      - ``path`` contains no ``://`` (slashes are fine; they delimit segments)

    Construct via ``parse(raw)`` for ``"domain://path"`` strings, or
    via ``root(domain)`` for the root URI of a domain.
    """

    domain: str
    path: str

    def __post_init__(self) -> None:
        if not self.domain:
            raise ValueError("MemoryURI domain must be non-empty")
        if SCHEME_SEPARATOR in self.domain:
            raise ValueError(f"MemoryURI domain must not contain '://': {self.domain!r}")
        if any(ord(c) < 0x20 for c in self.domain):
            raise ValueError(f"MemoryURI domain must not contain control characters: {self.domain!r}")
        if SCHEME_SEPARATOR in self.path:
            raise ValueError(f"MemoryURI path must not contain '://': {self.path!r}")

    @classmethod
    def parse(cls, raw: str) -> "MemoryURI":
        if SCHEME_SEPARATOR in raw:
            domain, path = raw.split(SCHEME_SEPARATOR, 1)
        else:
            domain, path = DEFAULT_DOMAIN, raw
        return cls(domain=domain, path=path)

    @classmethod
    def root(cls, domain: str = DEFAULT_DOMAIN) -> "MemoryURI":
        return cls(domain=domain, path="")

    def __str__(self) -> str:
        return f"{self.domain}{SCHEME_SEPARATOR}{self.path}"

    @property
    def is_root(self) -> bool:
        return self.path == ""

    def child(self, name: str) -> "MemoryURI":
        new_path = f"{self.path}/{name}" if self.path else name
        return MemoryURI(domain=self.domain, path=new_path)

    def parent(self) -> "MemoryURI | None":
        if self.is_root:
            return None
        head, _, _ = self.path.rpartition("/")
        return MemoryURI(domain=self.domain, path=head)
