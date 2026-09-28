"""Merge the per-stream progress of one download into a single job progress (pure logic).

yt-dlp fetches an MP4 as two separate streams (video, then audio) and reports
each one from 0 to 100 %. Shown as-is the bar jumps back to 0 halfway through.
`CombinedProgress` turns that into one monotonic fraction for the whole job.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Combined:
    fraction: object  # float in [0, 1] | None while the size is unknown
    downloaded: int   # bytes of all streams so far
    total: object     # int | None - estimated size of the whole job
    speed: object     # bytes/s | None
    eta: object       # seconds | None


class CombinedProgress:
    """Feed it every progress report of every stream; read one job-wide value back.

    `expected_sizes` are the announced sizes of the streams in download order
    (None where unknown) - with all of them the job total is known before the
    second stream starts. Otherwise each stream counts as an equal share.
    """

    def __init__(self, stream_count=1, expected_sizes=None):
        self._expected = list(expected_sizes or [])
        self._count = max(1, stream_count, len(self._expected))
        self._streams = {}  # key -> [downloaded, total] in first-seen order
        self._last_fraction = 0.0
        # Byte-based only when every size is announced up front; switching modes
        # halfway (a size learned late) would freeze the bar for a long stretch.
        self._by_bytes = bool(self._expected) and len(self._expected) >= self._count and all(self._expected)

    @classmethod
    def for_info(cls, info):
        """Build from a (format-selected) yt-dlp info dict."""
        requested = (info or {}).get("requested_formats") or []
        sizes = [f.get("filesize") or f.get("filesize_approx") for f in requested]
        return cls(stream_count=len(requested) or 1, expected_sizes=sizes)

    def update(self, key, downloaded, total=None, speed=None, eta=None, finished=False):
        downloaded = max(int(downloaded or 0), 0)
        total = int(total) if total else None
        if finished and total is None:
            total = downloaded or None
        stream = self._streams.setdefault(key, [0, None])
        stream[0] = downloaded
        if total:
            stream[1] = total
        if finished and stream[1]:
            stream[0] = stream[1]
        self._count = max(self._count, len(self._streams))

        index = list(self._streams).index(key)
        done_bytes = sum(s[0] for s in self._streams.values())
        sizes = self._sizes()
        fraction = None
        job_total = None
        if self._by_bytes and all(sizes):
            job_total = sum(sizes)
            fraction = done_bytes / job_total
        elif stream[1]:
            fraction = (index + min(stream[0] / stream[1], 1.0)) / self._count

        if fraction is not None:
            fraction = min(max(fraction, self._last_fraction), 1.0)
            self._last_fraction = fraction

        job_eta = None
        if job_total and speed:
            job_eta = max(job_total - done_bytes, 0) / speed
        elif index == self._count - 1:
            job_eta = eta
        return Combined(fraction, done_bytes, job_total, speed, job_eta)

    def _sizes(self):
        streams = list(self._streams.values())
        sizes = []
        for i in range(self._count):
            size = streams[i][1] if i < len(streams) else None
            if size is None and i < len(self._expected):
                size = self._expected[i]
            sizes.append(size)
        return sizes
