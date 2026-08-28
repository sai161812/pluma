with open('tests/unit/test_phase13_5_regression.py', 'r') as f:
    c = f.read()

c = c.replace('reg.register(snap2)', 'import pytest\n        with pytest.raises(ValueError):\n            reg.register(snap2)')

with open('tests/unit/test_phase13_5_regression.py', 'w') as f:
    f.write(c)
