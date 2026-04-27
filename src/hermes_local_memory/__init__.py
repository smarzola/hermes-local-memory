"""Local-first SQLite memory for Hermes Agent."""

from hermes_local_memory.provider import LocalMemoryProvider
from hermes_local_memory.store import LocalMemoryStore

__version__ = "0.3.0"

__all__ = ["LocalMemoryProvider", "LocalMemoryStore", "__version__"]
