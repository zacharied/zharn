"""User-editable logic. Edit while the app runs; it hot-reloads."""

def next_value(current: int) -> int:
    return current + 1

def describe(v: int) -> str:
    return f"counter is now {v}"
