"""Human-readable formatting of durations, speeds and remaining time."""


def fmt_duration(seconds):
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return ""
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def fmt_speed(bps):
    if not bps:
        return ""
    mb = bps / 1_000_000
    if mb >= 1:
        return f"{mb:.1f} MB/s"
    return f"{bps / 1000:.0f} KB/s"


def fmt_bytes(count):
    """Downloaded-size display used when the total size is unknown."""
    try:
        count = int(count)
    except (TypeError, ValueError):
        return ""
    if count <= 0:
        return ""
    if count >= 1_000_000_000:
        return f"{count / 1_000_000_000:.2f} GB"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f} MB"
    return f"{count / 1000:.0f} KB"


def fmt_eta(seconds):
    """Remaining-time display: whole minutes, or whole seconds under a minute - never fractional."""
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return ""
    if seconds < 0:
        return ""
    if seconds < 60:
        return f"{seconds} sn"
    return f"{round(seconds / 60)} dk"
