with open('update_golden.py', 'r', encoding='utf-8') as f:
    c = f.read()

c = c.replace("'rename_file': {'source': 'a.txt', 'new_name': 'b.txt'}", "'rename_file': {'path': 'a.txt', 'new_name': 'b.txt'}")

with open('update_golden.py', 'w', encoding='utf-8') as f:
    f.write(c)
