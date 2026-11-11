"""Owned target-bound native capture seam, never personal foreground selection."""
def native_capture(args,context):
    return native_screen_call(args,context,'execute_capture_target_window')


def native_find(args,context):
    return native_screen_call(args,context,'execute_find_visible_text')


def native_screen_call(args,context,operation):
    from pluma.perception.context import ActiveWindowContext
    from pluma.tools import screen_catalog
    snapshot=context.snapshot_registry.resolve(args['snapshot_id'])
    native=ActiveWindowContext()
    class OwnedContext:
        def get_active_window(self):return native.get_window_info(snapshot.hwnd)
        def get_window_info(self,hwnd):return native.get_window_info(hwnd)
        def get_process_creation_time_ns(self,pid):return native.get_process_creation_time_ns(pid)
    # Runs in this test-owned worker only. Every identity/geometry/pixel read is
    # native; the foreground selector is bound to the explicit fixture target.
    screen_catalog.ActiveWindowContext=OwnedContext
    return getattr(screen_catalog,operation)(args,context)
