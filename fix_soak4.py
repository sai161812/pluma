import os

with open('tests/benchmarks/test_memory_soak.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

out = []
skip = False
for line in lines:
    if "print(" in line and skip == False:
        out.append(line)
        if "delta_temp" not in line and "Children" not in line and "SOAK TEST" not in line:
            # wait, it's just a print( f" ... \n " )
            pass
    
    # I'll just write a script to fix it directly.
