with open('tests/unit/test_phase13_5_regression.py', 'r') as f:
    c = f.read()

c = c.replace('task_id="test",\n            task_context=ctx,', 'task_context=ctx,')

with open('tests/unit/test_phase13_5_regression.py', 'w') as f:
    f.write(c)
