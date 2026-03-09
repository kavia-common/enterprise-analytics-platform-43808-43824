"""Behavior analytics helpers (in-memory, non-persistent).

This module provides a small starter implementation for analyzing user behavior
events safely:

- Input validation (basic size limits, normalized fields)
- No I/O (no database/network/file writes)
- No sensitive logging (callers decide what to log/persist)

It is designed to be embedded into request handlers, background jobs, or tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# Conservative bounds to reduce abuse/memory blowups if used with untrusted input.
_MAX_EVENTS_DEFAULT = 10_000
_MAX_EVENT_TYPE_LEN = 128
_MAX_SOURCE_LEN = 128
_MAX_METADATA_KEYS = 64
_MAX_METADATA_VALUE_LEN = 2_000

_EVENT_TYPE_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")


class BehaviorAnalyticsError(ValueError):
    """Raised when user behavior analytics input is invalid or unsafe."""


@dataclass(frozen=True)
class BehaviorEvent:
    """A normalized user behavior event.

    Attributes:
        event_type: Event name/type (e.g., "page.view", "widget.click").
        occurred_at: UTC timestamp when the event occurred.
        source: Optional event source (e.g., "frontend", "backend", "mobile").
        metadata: Additional structured data (kept small; strings are truncated).
    """

    event_type: str
    occurred_at: datetime
    source: Optional[str] = None
    metadata: Dict[str, Any] = None  # type: ignore[assignment]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        # Treat naive datetime as UTC to avoid timezone ambiguity.
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _validate_event_type(event_type: str) -> str:
    event_type = (event_type or "").strip()
    if not event_type:
        raise BehaviorAnalyticsError("event_type is required")
    if len(event_type) > _MAX_EVENT_TYPE_LEN:
        raise BehaviorAnalyticsError("event_type too long")
    if not _EVENT_TYPE_RE.match(event_type):
        raise BehaviorAnalyticsError(
            "event_type contains invalid characters; allowed: alnum and . _ : -"
        )
    return event_type


def _validate_source(source: Optional[str]) -> Optional[str]:
    if source is None:
        return None
    source = source.strip()
    if not source:
        return None
    if len(source) > _MAX_SOURCE_LEN:
        raise BehaviorAnalyticsError("source too long")
    return source


def _sanitize_metadata(metadata: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not metadata:
        return {}

    if len(metadata) > _MAX_METADATA_KEYS:
        raise BehaviorAnalyticsError("metadata has too many keys")

    sanitized: Dict[str, Any] = {}
    for k, v in metadata.items():
        key = str(k).strip()
        if not key:
            continue
        # Keep keys modest to reduce misuse
        if len(key) > 128:
            key = key[:128]

        # For values, keep safe JSON-like primitives; convert unknowns to string
        if v is None or isinstance(v, (bool, int, float)):
            sanitized[key] = v
        elif isinstance(v, str):
            sanitized[key] = v[:_MAX_METADATA_VALUE_LEN]
        else:
            # Avoid serializing complex objects; represent compactly.
            s = str(v)
            sanitized[key] = s[:_MAX_METADATA_VALUE_LEN]

    return sanitized


def _normalize_event(
    *,
    event_type: str,
    occurred_at: Optional[datetime] = None,
    source: Optional[str] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> BehaviorEvent:
    normalized_type = _validate_event_type(event_type)
    normalized_source = _validate_source(source)
    ts = _coerce_utc(occurred_at or _utc_now())
    meta = _sanitize_metadata(metadata)
    return BehaviorEvent(
        event_type=normalized_type, occurred_at=ts, source=normalized_source, metadata=meta
    )


class BehaviorAnalyzer:
    """In-memory behavior analyzer for a stream/list of events.

    This class is intentionally simple and side-effect free. It does not persist
    events; callers can store events elsewhere (DB, queue) if needed.

    Security notes:
      - Applies conservative size/format validation to reduce abuse.
      - Does not log or emit event payloads.
    """

    def __init__(self, *, max_events: int = _MAX_EVENTS_DEFAULT) -> None:
        if max_events <= 0:
            raise BehaviorAnalyticsError("max_events must be > 0")
        if max_events > 1_000_000:
            # Hard cap to prevent accidental huge memory usage.
            raise BehaviorAnalyticsError("max_events is unreasonably large")
        self._max_events = max_events
        self._events: List[BehaviorEvent] = []

    # PUBLIC_INTERFACE
    def add_event(
        self,
        *,
        event_type: str,
        occurred_at: Optional[datetime] = None,
        source: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> BehaviorEvent:
        """Add a single event after validation/normalization.

        Args:
            event_type: Event name/type (validated).
            occurred_at: Optional datetime. Naive datetimes are treated as UTC.
            source: Optional source label.
            metadata: Optional mapping of extra properties. Values are sanitized/truncated.

        Returns:
            The normalized `BehaviorEvent` that was added.

        Raises:
            BehaviorAnalyticsError: If inputs are invalid, or if capacity is exceeded.
        """
        if len(self._events) >= self._max_events:
            raise BehaviorAnalyticsError("event buffer is full")
        ev = _normalize_event(
            event_type=event_type, occurred_at=occurred_at, source=source, metadata=metadata
        )
        self._events.append(ev)
        return ev

    # PUBLIC_INTERFACE
    def add_events(self, events: Iterable[Mapping[str, Any]]) -> int:
        """Add multiple events from dictionaries.

        Expected keys per event dict:
          - event_type (required)
          - occurred_at (optional, datetime)
          - source (optional, str)
          - metadata (optional, mapping)

        Args:
            events: Iterable of event-like dicts.

        Returns:
            Number of successfully added events.

        Raises:
            BehaviorAnalyticsError: If any event is invalid or capacity is exceeded.
        """
        count = 0
        for e in events:
            if not isinstance(e, Mapping):
                raise BehaviorAnalyticsError("each event must be a mapping/dict")
            self.add_event(
                event_type=str(e.get("event_type") or ""),
                occurred_at=e.get("occurred_at"),
                source=e.get("source"),
                metadata=e.get("metadata"),
            )
            count += 1
        return count

    # PUBLIC_INTERFACE
    def events(self) -> Sequence[BehaviorEvent]:
        """Return a snapshot view of currently buffered events."""
        # Return an immutable view by copying the list reference (events themselves are frozen).
        return tuple(self._events)

    # PUBLIC_INTERFACE
    def event_counts(self) -> Dict[str, int]:
        """Return counts per event_type."""
        counts: Dict[str, int] = {}
        for ev in self._events:
            counts[ev.event_type] = counts.get(ev.event_type, 0) + 1
        return counts

    # PUBLIC_INTERFACE
    def top_event_types(self, *, limit: int = 10) -> List[Tuple[str, int]]:
        """Return the most frequent event types.

        Args:
            limit: Maximum number of event types to return (must be > 0).

        Returns:
            List of (event_type, count) sorted by count desc then name asc.
        """
        if limit <= 0:
            raise BehaviorAnalyticsError("limit must be > 0")
        counts = self.event_counts()
        items = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        return items[:limit]

    # PUBLIC_INTERFACE
    def funnel_count(self, steps: Sequence[str]) -> int:
        """Count how many times a simple ordered funnel occurs.

        A funnel occurrence is detected when the sequence of event types appears
        in order (not necessarily contiguous) within the current event list.

        Example:
            steps=["page.view","widget.click","purchase.complete"]

        Args:
            steps: Ordered event_type names to match.

        Returns:
            Number of completed funnels found (greedy, non-overlapping).

        Raises:
            BehaviorAnalyticsError: If steps are invalid.
        """
        if not steps:
            raise BehaviorAnalyticsError("steps must not be empty")

        normalized_steps = [_validate_event_type(s) for s in steps]
        step_idx = 0
        completed = 0

        for ev in self._events:
            if ev.event_type == normalized_steps[step_idx]:
                step_idx += 1
                if step_idx == len(normalized_steps):
                    completed += 1
                    step_idx = 0  # greedy reset to count non-overlapping funnels

        return completed


# PUBLIC_INTERFACE
def summarize_events(events: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Summarize a batch of raw event dicts.

    This helper is convenient for one-off analysis without managing a class.

    Args:
        events: Iterable of event-like dicts. See `BehaviorAnalyzer.add_events`.

    Returns:
        A dictionary with summary stats:
          - total_events
          - unique_event_types
          - event_counts (per type)
          - top_event_types (top 10)
    """
    analyzer = BehaviorAnalyzer()
    analyzer.add_events(events)
    counts = analyzer.event_counts()
    return {
        "total_events": sum(counts.values()),
        "unique_event_types": len(counts),
        "event_counts": counts,
        "top_event_types": analyzer.top_event_types(limit=10),
    }


# PUBLIC_INTERFACE
def detect_suspicious_burst(
    events: Sequence[BehaviorEvent],
    *,
    event_type: str,
    window_seconds: int = 60,
    threshold: int = 100,
) -> bool:
    """Detect a suspicious burst of a given event type in a short window.

    This is a basic heuristic that can be used to flag potential automation
    (e.g., repeated login attempts, rapid widget creation clicks, etc.).

    Args:
        events: Sequence of normalized `BehaviorEvent` items (assumed UTC).
        event_type: The event type to evaluate.
        window_seconds: Sliding window size in seconds (> 0).
        threshold: Number of events within window to be considered suspicious (> 0).

    Returns:
        True if a burst is detected, otherwise False.

    Raises:
        BehaviorAnalyticsError: If inputs are invalid.
    """
    normalized_type = _validate_event_type(event_type)
    if window_seconds <= 0:
        raise BehaviorAnalyticsError("window_seconds must be > 0")
    if threshold <= 0:
        raise BehaviorAnalyticsError("threshold must be > 0")
    if not events:
        return False

    # Filter matching type and ensure UTC coercion
    ts: List[datetime] = [_coerce_utc(e.occurred_at) for e in events if e.event_type == normalized_type]
    if len(ts) < threshold:
        return False

    ts.sort()
    start = 0
    for end in range(len(ts)):
        while start <= end and (ts[end] - ts[start]).total_seconds() > window_seconds:
            start += 1
        if (end - start + 1) >= threshold:
            return True
    return False


# PUBLIC_INTERFACE
def safe_event_preview(event: BehaviorEvent) -> Dict[str, Any]:
    """Return a safe-to-display preview of an event.

    This function is designed for admin/debug UIs where you want to show some
    metadata without risking huge payloads.

    It returns only:
      - event_type
      - occurred_at (ISO string)
      - source
      - metadata_keys (list of keys, no values)

    Args:
        event: Normalized `BehaviorEvent`.

    Returns:
        A dictionary suitable for display/debug.
    """
    meta = event.metadata or {}
    return {
        "event_type": event.event_type,
        "occurred_at": _coerce_utc(event.occurred_at).isoformat(),
        "source": event.source,
        "metadata_keys": sorted([str(k) for k in meta.keys()])[:_MAX_METADATA_KEYS],
    }
