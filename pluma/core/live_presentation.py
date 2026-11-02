"""Task-owned factual presentation state. No OS calls, subscriptions or workers."""
import threading
import time


class LivePresentation:
    def __init__(self):
        self.lock = threading.Lock()
        self.plan_revision = 0
        self.step = None
        self.total = None
        self.tool = None
        self.risk = None
        self.phase = None
        self.entered_at = None
        self.generation = 0
        self.next_generation = 0
        self.parents = []
        self.arguments = None
        self.rollback_step = self.rollback_total = self.rollback_recipe = None

    def plan(self, total):
        with self.lock:
            self.plan_revision += 1
            self.total = total
            self.step = None

    def select(self, step):
        with self.lock:
            self.step = step

    def dispatch(self, tool, risk, arguments):
        from pluma.memory.redaction import sanitise_args_for_ledger
        if "clipboard" in tool or "paste" in tool or tool == "type_text":
            arguments = {key: "[REDACTED]" for key in arguments}
        preview = sanitise_args_for_ledger(tool, arguments).encode("utf-8")
        preview = preview.decode("utf-8") if len(preview) <= 1024 else preview[:1021].decode("utf-8", errors="ignore") + "…"
        with self.lock:
            if self.tool is not None:
                self.parents.append((self.generation, self.tool, self.risk, self.phase, self.entered_at, self.arguments))
            self.next_generation += 1
            self.generation = self.next_generation
            self.tool, self.risk, self.phase = tool, risk, "DISPATCHING"
            self.entered_at = None
            self.arguments = preview
            return self.generation

    def entered(self, generation, started=None):
        with self.lock:
            if self.generation == generation:
                self.phase = "EXECUTING"
                self.entered_at = time.monotonic() if started is None else started

    def verifying(self, generation):
        with self.lock:
            if self.generation == generation:
                self.phase = "VERIFYING"

    def recording(self, generation):
        with self.lock:
            if self.generation == generation:
                self.phase = "RECORDING"

    def complete(self, generation):
        with self.lock:
            if self.generation == generation:
                if self.parents:
                    self.generation, self.tool, self.risk, self.phase, self.entered_at, self.arguments = self.parents.pop()
                else:
                    self.tool = self.risk = self.phase = self.entered_at = None
                    self.arguments = None
            else:
                self.parents = [parent for parent in self.parents if parent[0] != generation]

    def rollback(self, step, total, recipe):
        import re
        with self.lock:
            self.rollback_step, self.rollback_total = step, total
            self.rollback_recipe = recipe if isinstance(recipe, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", recipe) else None

    def snapshot(self):
        if not self.lock.acquire(timeout=.02):
            raise TimeoutError("Live presentation is busy")
        try:
            return dict(plan_revision=self.plan_revision, step=self.step, total=self.total,
                tool=self.tool, risk=self.risk, phase=self.phase,
                arguments=self.arguments, rollback_step=self.rollback_step,
                rollback_total=self.rollback_total, rollback_recipe=self.rollback_recipe,
                tool_elapsed_ms=None if self.entered_at is None else max(0, int((time.monotonic() - self.entered_at) * 1000)))
        finally:
            self.lock.release()
