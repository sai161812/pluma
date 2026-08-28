with open('update_golden.py', 'r') as f:
    c = f.read()
c = c.replace("'list_files': {'directory': '.'}", "'list_files': {'path': '.'}")
with open('update_golden.py', 'w') as f:
    f.write(c)
