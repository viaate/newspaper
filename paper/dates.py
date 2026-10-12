def fmt(d, pattern):
    """strftime with %-d (day without a leading zero) on every platform, Windows included."""
    return d.strftime(pattern.replace("%-d", str(d.day))) if d else ""
