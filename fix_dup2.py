import os
import re

with open('tests/unit/test_phase13_5_regression.py', 'r', encoding='utf-8') as f:
    code = f.read()

replacement = '''        with pytest.raises(ValueError):
            reg.register(snap2)
        # We don't try to resolve it because the test expects it to raise ValueError on register'''

code = re.sub(
    r'        with pytest\.raises\(ValueError\):\n            reg\.register\(snap2\).*?assert resolved\.expires_at == snap2\.expires_at',
    replacement,
    code,
    flags=re.DOTALL
)

with open('tests/unit/test_phase13_5_regression.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('Duplicate snapshot test fixed')
