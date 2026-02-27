"""Simplified cron expression parser (no external dependencies).

Supports standard 5-field cron expressions:
    minute hour day_of_month month day_of_week

Special values:
    *       any value
    */N     every N (step)
    N       exact value
    N-M     range
    N,M,O   list

Examples:
    "*/5 * * * *"     → every 5 minutes
    "0 9 * * 1-5"    → 9 AM weekdays
    "30 2 * * 0"     → 2:30 AM Sundays
    "0 */6 * * *"    → every 6 hours
"""

import time
from datetime import datetime


# Field definitions: (name, min, max)
FIELDS = [
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day_of_month", 1, 31),
    ("month", 1, 12),
    ("day_of_week", 0, 6),  # 0=Monday ... 6=Sunday (ISO)
]


class CronParseError(ValueError):
    """Invalid cron expression."""
    pass


def _parse_field(expr: str, min_val: int, max_val: int) -> set[int]:
    """Parse a single cron field into a set of matching integer values."""
    values = set()

    for part in expr.split(","):
        part = part.strip()

        if part == "*":
            values.update(range(min_val, max_val + 1))

        elif part.startswith("*/"):
            try:
                step = int(part[2:])
            except ValueError:
                raise CronParseError(f"Invalid step: {part}")
            if step <= 0:
                raise CronParseError(f"Step must be positive: {part}")
            values.update(range(min_val, max_val + 1, step))

        elif "-" in part and not part.startswith("-"):
            # Range: N-M or N-M/S
            range_part, *step_parts = part.split("/")
            try:
                low, high = range_part.split("-")
                low, high = int(low), int(high)
            except ValueError:
                raise CronParseError(f"Invalid range: {part}")

            if low < min_val or high > max_val or low > high:
                raise CronParseError(
                    f"Range {low}-{high} out of bounds [{min_val}-{max_val}]"
                )

            step = 1
            if step_parts:
                try:
                    step = int(step_parts[0])
                except ValueError:
                    raise CronParseError(f"Invalid step in range: {part}")

            values.update(range(low, high + 1, step))

        else:
            try:
                val = int(part)
            except ValueError:
                raise CronParseError(f"Invalid value: {part}")
            if val < min_val or val > max_val:
                raise CronParseError(
                    f"Value {val} out of bounds [{min_val}-{max_val}]"
                )
            values.add(val)

    return values


class CronExpression:
    """Parsed cron expression that can check if a datetime matches."""

    def __init__(self, expression: str):
        self.expression = expression.strip()
        parts = self.expression.split()

        if len(parts) != 5:
            raise CronParseError(
                f"Expected 5 fields (minute hour dom month dow), got {len(parts)}: "
                f"'{self.expression}'"
            )

        self.minute = _parse_field(parts[0], *FIELDS[0][1:])
        self.hour = _parse_field(parts[1], *FIELDS[1][1:])
        self.day_of_month = _parse_field(parts[2], *FIELDS[2][1:])
        self.month = _parse_field(parts[3], *FIELDS[3][1:])
        self.day_of_week = _parse_field(parts[4], *FIELDS[4][1:])

    def matches(self, dt: datetime | None = None) -> bool:
        """Check if the given datetime matches this cron expression.

        Uses current time if dt is None. Matching is done at minute resolution.
        day_of_week: 0=Monday ... 6=Sunday (Python convention).
        """
        if dt is None:
            dt = datetime.now()

        return (
            dt.minute in self.minute
            and dt.hour in self.hour
            and dt.day in self.day_of_month
            and dt.month in self.month
            and dt.weekday() in self.day_of_week
        )

    def next_run(self, after: datetime | None = None, max_look_ahead: int = 525600) -> datetime | None:
        """Find the next datetime that matches, searching minute by minute.

        Args:
            after: Start searching after this time (default: now).
            max_look_ahead: Max minutes to search ahead (default: 1 year).

        Returns:
            Next matching datetime or None if not found within look-ahead.
        """
        if after is None:
            after = datetime.now()

        # Start from the next minute
        candidate = after.replace(second=0, microsecond=0)
        # Move to next minute
        candidate = datetime.fromtimestamp(candidate.timestamp() + 60)

        for _ in range(max_look_ahead):
            if self.matches(candidate):
                return candidate
            candidate = datetime.fromtimestamp(candidate.timestamp() + 60)

        return None

    def describe(self) -> str:
        """Human-readable description of the cron expression."""
        parts = self.expression.split()
        descriptions = []

        # Minute
        if parts[0] == "*":
            descriptions.append("every minute")
        elif parts[0].startswith("*/"):
            descriptions.append(f"every {parts[0][2:]} minutes")
        elif parts[0] == "0":
            pass  # will be described with hour
        else:
            descriptions.append(f"at minute {parts[0]}")

        # Hour
        if parts[1] == "*":
            if parts[0] == "0":
                descriptions.append("every hour")
        elif parts[1].startswith("*/"):
            descriptions.append(f"every {parts[1][2:]} hours")
        else:
            minute = parts[0] if parts[0] != "*" else "00"
            descriptions.append(f"at {parts[1]}:{minute.zfill(2)}")

        # Day of week
        dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        if parts[4] != "*":
            if "-" in parts[4]:
                low, high = parts[4].split("-")
                descriptions.append(f"{dow_names[int(low)]}-{dow_names[int(high)]}")
            else:
                days = [dow_names[int(d)] for d in parts[4].split(",")]
                descriptions.append(", ".join(days))

        # Day of month
        if parts[2] != "*":
            descriptions.append(f"on day {parts[2]}")

        # Month
        if parts[3] != "*":
            descriptions.append(f"in month {parts[3]}")

        return " ".join(descriptions) if descriptions else self.expression

    def __repr__(self):
        return f"CronExpression('{self.expression}')"
