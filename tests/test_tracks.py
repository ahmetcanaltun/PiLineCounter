"""Tests for track memory and its eviction."""

import tracks


def store(**kwargs):
    return tracks.TrackStore(**kwargs)


class TestHistory:
    def test_remembers_where_a_track_has_been(self):
        s = store()
        s.seen(1, (10, 20), now=0)
        s.seen(1, (11, 21), now=1)
        assert s.trail(1) == [(10, 20), (11, 21)]

    def test_trail_is_capped(self):
        s = store(trail_length=3)
        for i in range(10):
            s.seen(1, (i, i), now=i)
        assert s.trail(1) == [(7, 7), (8, 8), (9, 9)]

    def test_movement_needs_two_sightings(self):
        s = store()
        s.seen(1, (10, 20), now=0)
        assert s.previous_and_current(1) is None
        s.seen(1, (11, 21), now=1)
        assert s.previous_and_current(1) == ((10, 20), (11, 21))


class TestEviction:
    def test_first_sweep_only_starts_the_clock(self):
        s = store(ttl=60, sweep_every=30)
        s.seen(1, (0, 0), now=0)
        assert s.sweep(now=0) == 0
        assert len(s) == 1

    def test_sweeps_are_rate_limited(self):
        s = store(ttl=10, sweep_every=30)
        s.seen(1, (0, 0), now=0)
        s.sweep(now=0)
        # The track is stale, but it is not yet time to look.
        assert s.sweep(now=20) == 0
        assert len(s) == 1

    def test_stale_tracks_are_forgotten(self):
        s = store(ttl=60, sweep_every=30)
        s.seen(1, (0, 0), now=0)
        s.mark_counted(1)
        s.sweep(now=0)

        assert s.sweep(now=100) == 1
        assert len(s) == 0
        assert s.trail(1) == []
        assert not s.is_counted(1)

    def test_active_tracks_survive(self):
        s = store(ttl=60, sweep_every=30)
        s.seen(1, (0, 0), now=0)
        s.seen(2, (5, 5), now=0)
        s.sweep(now=0)

        s.seen(2, (6, 6), now=95)  # track 2 is still around
        assert s.sweep(now=100) == 1
        assert len(s) == 1
        assert s.trail(2) != []

    def test_memory_stays_bounded_over_a_long_run(self):
        # Each passer-by gets a fresh id. Without eviction this is the leak that
        # eventually takes the device down; with it, only live tracks are held.
        s = store(ttl=60, sweep_every=30)
        s.sweep(now=0)
        for track_id in range(10_000):
            moment = track_id * 1.0
            s.seen(track_id, (0, 0), now=moment)
            s.mark_counted(track_id)
            s.sweep(now=moment)
        assert len(s) < 100

    def test_clear_forgets_everything(self):
        s = store()
        s.seen(1, (0, 0), now=0)
        s.mark_counted(1)
        s.clear()
        assert len(s) == 0
        assert not s.is_counted(1)
