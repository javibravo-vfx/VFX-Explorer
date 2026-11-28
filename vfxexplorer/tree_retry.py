"""Retry bookkeeping distinguishes cache hits from authoritative reads.

Tickets invalidate callbacks from a previous tree generation or a successful
read. A recorded attempt is not necessarily a scheduled retry.
"""
class TreeRetries:
    def __init__(self, limit=8):
        self.limit = limit
        self.attempts = {}
        self.pending = {}

    def schedule(self, key):
        if key in self.pending:
            return None
        n = self.attempts.get(key, 0)
        if n >= self.limit:
            return None
        ticket = object()
        self.attempts[key] = n + 1
        self.pending[key] = ticket
        return ticket, min(30, 2 ** (n + 1)) * 1000

    def consume(self, key, ticket):
        if self.pending.get(key) is not ticket:
            return False
        del self.pending[key]
        return True

    def reset(self, key):
        self.attempts.pop(key, None)
        self.pending.pop(key, None)

    def clear(self):
        self.attempts.clear()
        self.pending.clear()
