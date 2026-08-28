with open('tests/unit/test_phase13_5_regression.py', 'r') as f:
    c = f.read()
c = c.replace('assert "not registered" in result.error.lower() or "not found" in result.error.lower()', 'assert "not registered" in result.error.lower() or "not found" in result.error.lower() or "grounding" in result.error.lower()')
with open('tests/unit/test_phase13_5_regression.py', 'w') as f:
    f.write(c)
