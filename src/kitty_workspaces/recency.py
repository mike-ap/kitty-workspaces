"""Instance-local workspace visits, independent of pane and display ordering."""


class Recency:
    def __init__(self):
        self.visits = {}
        self.sequence = 0
        self.current = None

    def prune(self, live_ids):
        self.visits = {
            key: value for key, value in self.visits.items() if key in live_ids
        }
        if self.current not in live_ids:
            self.current = None

    def visit(self, identity):
        if identity is None or identity == self.current:
            return
        self.sequence += 1
        self.visits[identity] = self.sequence
        self.current = identity
