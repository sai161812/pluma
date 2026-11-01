"""Importable owned wait used only by P18 native shell acceptance."""
import time
from pluma.tools.base import ToolResult, VerifyResult


def execute(args, context):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        context.cancellation_token.raise_if_cancelled()
        time.sleep(.01)
    return ToolResult.failure("fixture_process", "Owned process wait expired.")


def verify(result):
    return VerifyResult(ok=False, method="owned_process_wait", detail="No success is claimed.")
