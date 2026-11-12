"""A cooperative wall-clock budget with time reserved for the final report."""
import time


class RunBudget:
    def __init__(self, minutes=0, clock=time.monotonic):
        self.clock = clock
        self.started = clock()
        self.total = max(0, minutes * 60)
        reserve = min(600, self.total / 5)
        self.deadlines = {
            "research": self.started + self.total - reserve,
            "financial": self.started + self.total - reserve / 2,
            "synthesis": self.started + self.total,
        }
        self.phase = "research"
        self.exhausted = set()

    def remaining(self):
        if not self.total:
            return float("inf")
        return max(0, self.deadlines[self.phase] - self.clock())

    def available(self):
        if self.remaining() < 1:
            self.exhausted.add(self.phase)
            return False
        return True

