with open('tests/benchmarks/test_memory_soak.py', 'r') as f:
    lines = f.readlines()

new_lines = []
in_print = False
for line in lines:
    if 'print(' in line and 'SOAK TEST' in line:
        pass # Wait, it's spread over multiple lines because of \n?
    
with open('tests/benchmarks/test_memory_soak.py', 'r') as f:
    c = f.read()

c = c.replace('f"\\n[SOAK TEST]', 'f"""\\n[SOAK TEST]')
c = c.replace('(Delta: {delta_temp})"', '(Delta: {delta_temp})"""')

with open('tests/benchmarks/test_memory_soak.py', 'w') as f:
    f.write(c)
