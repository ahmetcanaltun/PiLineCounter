"""What the counter remembers about objects in motion.

The tracker hands out a fresh id for every object that appears, so anything
keyed by track id grows for as long as the device runs. On a counter that stays
up for weeks that is a leak, not a detail: this store forgets a track once it
has been out of sight long enough that it cannot come back.

Free of OpenCV and the model runtime, so the eviction can be tested directly.
"""

from __future__ import annotations

Point = tuple[int, int]

TRAIL_LENGTH = 30  # points kept per track, enough to draw its recent path
TTL_SECONDS = 60.0  # forget a track this long after it was last seen
SWEEP_SECONDS = 30.0  # how often to look for tracks worth forgetting


class TrackStore:
    """Per-track history and counted state, with stale entries evicted."""

    def __init__(
        self,
        trail_length: int = TRAIL_LENGTH,
        ttl: float = TTL_SECONDS,
        sweep_every: float = SWEEP_SECONDS,
    ) -> None:
        self.trail_length = trail_length
        self.ttl = ttl
        self.sweep_every = sweep_every

        self._history: dict[int, list[Point]] = {}
        self._counted: set[int] = set()
        self._last_seen: dict[int, float] = {}
        self._last_sweep: float | None = None

    def __len__(self) -> int:
        """Number of tracks currently remembered."""
        return len(self._last_seen)

    def seen(self, track_id: int, point: Point, now: float) -> None:
        """Record where a track is at this moment."""
        trail = self._history.setdefault(track_id, [])
        trail.append(point)
        if len(trail) > self.trail_length:
            trail.pop(0)
        self._last_seen[track_id] = now

    def trail(self, track_id: int) -> list[Point]:
        return self._history.get(track_id, [])

    def previous_and_current(self, track_id: int) -> tuple[Point, Point] | None:
        """The last two positions, or None if the track has only been seen once."""
        trail = self._history.get(track_id, ())
        if len(trail) < 2:
            return None
        return trail[-2], trail[-1]

    def is_counted(self, track_id: int) -> bool:
        return track_id in self._counted

    def mark_counted(self, track_id: int) -> None:
        self._counted.add(track_id)

    def sweep(self, now: float) -> int:
        """Forget tracks not seen for `ttl` seconds. Returns how many went.

        Rate-limited to `sweep_every`, since walking every track on every frame
        would cost more than the memory it reclaims.
        """
        if self._last_sweep is None:
            self._last_sweep = now
            return 0
        if now - self._last_sweep < self.sweep_every:
            return 0
        self._last_sweep = now

        stale = [tid for tid, seen in self._last_seen.items() if now - seen > self.ttl]
        for track_id in stale:
            self._last_seen.pop(track_id, None)
            self._history.pop(track_id, None)
            self._counted.discard(track_id)
        return len(stale)

    def clear(self) -> None:
        """Forget everything - used when the line or the mode changes."""
        self._history.clear()
        self._counted.clear()
        self._last_seen.clear()
        self._last_sweep = None
