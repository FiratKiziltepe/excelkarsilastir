"""Excel sürüm karşılaştırma çekirdeği."""
from .compare import Settings, compare_tables
from .columns import auto_map, guess_roles
from .loader import read_table, sheet_names

__all__ = ["Settings", "compare_tables", "auto_map", "guess_roles", "read_table", "sheet_names"]
