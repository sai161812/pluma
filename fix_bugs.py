import re

with open('tests/unit/test_phase13_5_regression.py', 'r', encoding='utf-8') as f:
    code = f.read()

replacement = '''    def test_duplicate_snapshots_use_latest(self):
        from pluma.perception.snapshot_registry import SnapshotRegistry
        from pluma.perception.element_refs import BoundingBox, ScreenSnapshot
        from datetime import datetime, timedelta, timezone
        import pytest
        reg = SnapshotRegistry()
        now = datetime.now(timezone.utc)
        snap1 = ScreenSnapshot(
            snapshot_id="dup",
            created_at=now,
            expires_at=now + timedelta(seconds=-1.0),
            active_process="a", active_window_title="a",
            window_rect=BoundingBox(left=0, top=0, right=100, bottom=100),
            dpi_scale=1.0,
        )
        snap2 = ScreenSnapshot(
            snapshot_id="dup",
            created_at=now,
            expires_at=now + timedelta(seconds=10.0),
            active_process="b", active_window_title="b",
            window_rect=BoundingBox(left=0, top=0, right=100, bottom=100),
            dpi_scale=1.0,
        )
        reg.register(snap1)
        with pytest.raises(ValueError):
            reg.register(snap2)

    def'''

code = re.sub(
    r'    def test_duplicate_snapshots_use_latest\(self\):.*?with pytest\.raises\(ValueError\):\n            reg\.register\(snap2\).*?    def',
    replacement,
    code,
    flags=re.DOTALL
)

with open('tests/unit/test_phase13_5_regression.py', 'w', encoding='utf-8') as f:
    f.write(code)

with open('update_golden.py', 'r', encoding='utf-8') as f:
    c = f.read()
c = c.replace("'find_file': {'filename': 'config.txt'}", "'find_file': {'pattern': 'config.txt'}")
with open('update_golden.py', 'w', encoding='utf-8') as f:
    f.write(c)
