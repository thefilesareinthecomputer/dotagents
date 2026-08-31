"""Importing the tool modules is what registers them; order is alphabetical
so the registry listing is deterministic."""
from relay.tools.registry import ToolRegistry, ToolSpec, get_registry, tool
from relay.tools import file_tool   # noqa: F401  (registration import)
from relay.tools import shell_tool  # noqa: F401  (registration import)
from relay.tools import sql_tool    # noqa: F401  (registration import)
from relay.tools import web_tool    # noqa: F401  (registration import)

__all__ = ["ToolRegistry", "ToolSpec", "get_registry", "tool"]
