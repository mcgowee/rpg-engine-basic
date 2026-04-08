"""Subgraph registry — loads compiled subgraphs from DB, caches them."""

import json
import logging
from graphs.builder import build_graph_from_json

logger = logging.getLogger(__name__)


class SubgraphRegistry:
    """Loads subgraph definitions from DB, compiles and caches them."""

    def __init__(self):
        self._compiled = {}

    def load_from_db(self, db_conn):
        """Load all subgraphs from the database and compile them."""
        rows = db_conn.execute("SELECT name, definition FROM subgraphs").fetchall()
        for row in rows:
            name = row["name"]
            try:
                definition = json.loads(row["definition"])
                self._compiled[name] = build_graph_from_json(definition)
                logger.info("Compiled subgraph: %s", name)
            except Exception as e:
                logger.error("Failed to compile subgraph %s: %s", name, e)

    def get(self, name: str):
        """Get a compiled subgraph by name, or None if missing."""
        return self._compiled.get(name)

    def require(self, name: str):
        """Return compiled graph or raise KeyError."""
        g = self._compiled.get(name)
        if g is None:
            raise KeyError(f"unknown subgraph: {name}")
        return g

    def reload_one(self, name: str, definition: dict):
        """Compile and cache a single subgraph definition."""
        self._compiled[name] = build_graph_from_json(definition)

    def remove(self, name: str):
        """Remove a subgraph from the cache."""
        self._compiled.pop(name, None)

    def list_names(self) -> list[str]:
        """Return sorted list of available subgraph names."""
        return sorted(self._compiled.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._compiled


# Global singleton
registry = SubgraphRegistry()
