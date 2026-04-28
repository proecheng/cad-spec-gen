"""
adapters/parts/base.py — Abstract base class for parts library adapters.

The PartsResolver treats every adapter as a black box with this interface.
Subclasses must implement all four methods.

Design notes:
- `is_available()` should be cheap (no heavy imports). Good practice: check
  for a catalog file or a config flag, not the actual optional dependency.
- `can_resolve()` is a fast pre-check used during logging / introspection;
  the resolver itself does not call it before resolve() — resolve() may
  simply return ResolveResult.miss() if nothing matches.
- `resolve()` is the work method. It receives both the PartQuery and the
  adapter-specific `spec` dict from the matching YAML mapping rule. `mode`
  separates read-only inspection from codegen/export work.
- `probe_dims()` is a fast dimension-only query used by Phase 1 envelope
  backfill. Must not build full geometry.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class PartsAdapter(ABC):
    """Interface every parts library adapter must implement."""

    name: str = ""  # subclass sets this to e.g. "bd_warehouse"

    @abstractmethod
    def is_available(self) -> tuple[bool, Optional[str]]:
        """Return (available, reason_if_unavailable).

        available: True if this adapter can be used right now.
        reason_if_unavailable: human-readable string when available=False, else None.

        Prefer lightweight checks (catalog file existence, env flags) over
        optional dependency imports. Exception: adapters whose only availability
        signal is the install itself (e.g. bd_warehouse) may do a fast import
        probe — Python's import cache makes repeated calls a dict lookup.
        """

    @abstractmethod
    def can_resolve(self, query) -> bool:
        """Return True if this adapter has a reasonable shot at resolving query.

        Used for logging / `--verbose` output. The resolver dispatches based
        on YAML rules, not this method.
        """

    @abstractmethod
    def resolve(self, query, spec: dict, mode: str = "codegen"):
        """Return a ResolveResult for this query.

        Parameters
        ----------
        query : PartQuery
            The BOM row being resolved.
        spec : dict
            The `spec:` field of the matching YAML rule. Adapter-specific.
        mode : str
            "inspect" / "probe" must be read-only; "codegen" / "export" may
            create cache files or call external CAD tools.

        Returns
        -------
        ResolveResult with status="hit" on success, status="miss" otherwise.
        """

    @abstractmethod
    def probe_dims(self, query, spec: dict) -> Optional[tuple]:
        """Return (w, d, h) dimensions in mm without building geometry.

        Called during Phase 1 envelope backfill. Fast path — no heavy work.
        Return None if the adapter cannot determine dimensions cheaply.
        """

    def prewarm(self, candidates) -> None:
        """Optional pre-warmup hook called before the BOM resolve loop (Task 14.6).

        candidates: list[tuple[PartQuery, dict]] — (query, rule.spec) tuples that
        PartsResolver pre-matched to this adapter via _match_rule. Adapter can use
        this to batch any expensive setup (e.g. spawn helper subprocess once for
        all sldprt instead of per-part).

        Returns None — fire-and-forget. Failures must not raise (codegen continues
        via fallback paths in resolve()).

        Default implementation is no-op. Adapters override only if they have
        batchable expensive operations to amortize.
        """
        return None
