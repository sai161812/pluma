"""Check P00 traceability against locked source documents, without loading PLUMA.

This verifies documentation completeness, never product acceptance. Run from
any directory: python docs/completion/verify_requirements_matrix.py
"""
from collections import Counter
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
STATUSES = {"IMPLEMENTED", "UNWIRED", "UNVERIFIED", "DEFECTIVE", "MISSING", "OPTIONAL"}
SOURCE_COUNTS = {
    "A": 7, "B": 7, "C": 10, "D": 10, "E": 10, "F": 10, "G": 10,
    "H": 8, "I": 7, "J": 17, "S28": 18, "CAT": 73, "CAP": 8,
    "LAW": 14, "UI": 26, "BA": 9, "BP": 39, "PLACE": 15,
}


def normalize(value):
    return " ".join(value.replace("\\|", "/").replace("|", "/").split())


def bullets(value):
    return [normalize(part) for part in re.findall(r"^- (.*(?:\n(?!\n|[-#]).*)*)", value, re.M)]


def source_requirements(root=ROOT):
    master = (root / "PLUMA_MASTER_SPEC.md").read_text(encoding="utf-8")
    acceptance = (root / "PLUMA_ACCEPTANCE_TESTS.md").read_text(encoding="utf-8")
    surfaces = (root / "PLUMA.UI/PLUMA.UI/docs/phase14_ui_surfaces.md").read_text(encoding="utf-8")
    plan = (root / "PLUMA_BUILD_PLAN.md").read_text(encoding="utf-8")
    expected = {}
    for rid, title, result in re.findall(r"^\| ([A-H]-\d{2}) \| (.*?) \| (.*?) \|$", acceptance, re.M):
        expected[rid] = (normalize(title + ": " + result), "acceptance A-H")
    metrics = acceptance.split("## I.", 1)[1].split("```text", 1)[1].split("```", 1)[0].strip().splitlines()
    for i, metric in enumerate(metrics, 1):
        expected[f"I-{i:02}"] = (normalize(metric), "acceptance I (derived IDs)")
    for i, item in enumerate(bullets(acceptance.split("## J.", 1)[1]), 1):
        expected[f"J-{i:02}"] = (item, "acceptance J (derived IDs)")
    done = master.split('# **28.', 1)[1].split('<table>', 1)[0]
    for i, item in enumerate(re.findall(r"^☐ (.*?)(?=\n\s*\n|\Z)", done, re.M | re.S), 1):
        expected[f"S28-{i:02}"] = (normalize(item), "master section 28 (derived IDs)")
    catalog = master.split('# **21.', 1)[1].split('# **22.', 1)[0]
    for category, names in re.findall(r"^\| ([A-Za-z][^|]*?)\s*\| (.*?)\s*\|$", catalog, re.M):
        for name in names.split(';', 1)[0].split(','):
            name = name.strip()
            expected["CAT-" + name] = (name, "master section 21 / " + category.strip())
    caps = master.split('## **1.1', 1)[1].split('## **1.2', 1)[0]
    for i, item in enumerate(bullets(caps), 1):
        expected[f"CAP-{i:02}"] = (item, "master section 1.1")
    laws = master.split('# **3.', 1)[1].split('# **4.', 1)[0].split('\n', 1)[1]
    for i, item in enumerate(re.findall(r"^\d+\\\. (.*?)(?=\n\s*\n|\Z)", laws, re.M | re.S), 1):
        expected[f"LAW-{i:02}"] = (normalize(item), "master section 3")
    for i, title in re.findall(r"^### (\d+)\. (.+)$", surfaces, re.M):
        expected[f"UI-{int(i):02}"] = (title.strip(), "surface reference / " + i)
    audit = (root / "PLUMA.UI/PLUMA.UI/docs/backend_wiring_audit.md").read_text(encoding="utf-8")
    for severity, rid, title in re.findall(r"^\| (P[12]) \| (BA-\d{2}) \| (.*?) \|", audit, re.M):
        expected[rid] = (title, "backend audit / " + severity)
    for phase, block in re.findall(r"^## Phase (\d+) (.*?)(?=^## Phase |^## Commit sequence|\Z)", plan, re.M | re.S):
        if '### Gate' not in block:
            continue
        gate = block.split('### Gate', 1)[1].split('### ', 1)[0]
        for i, item in enumerate(bullets(gate), 1):
            expected[f"BP-{int(phase):02}-{i:02}"] = (item, "build plan / Phase " + phase + " gate")
    placement = (root / 'PLUMA.UI/PLUMA.UI/docs/popup_placement_contract.md').read_text(encoding='utf-8')
    for number, case, result in re.findall(r"^\| P-(\d{2}) \| (.*?) \| (.*?) \|$", placement, re.M):
        expected['PLACE-' + number] = (normalize(case + ': ' + result), 'owner placement / P-' + number)
    counts = Counter(rid.split('-')[0] for rid in expected)
    if dict(counts) != SOURCE_COUNTS:
        raise ValueError(f'Source extraction changed; inspect parser/source before accepting coverage: {dict(counts)}')
    return expected


def inspect_rows(content, expected):
    """Return structural/source errors; also usable with inert negative fixtures."""
    rows = {}
    errors = []
    for line in content.splitlines():
        if not re.match(r"^\| (?:[A-Z][A-Z0-9]*-)", line):
            continue
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        if len(cells) != 8:
            errors.append("Expected 8 cells: " + line[:100])
            continue
        rid, source, requirement, implementation, evidence, status, owner, gap = cells
        if rid in rows:
            errors.append("Duplicate ID " + rid)
        rows[rid] = cells
        if any(not value for value in cells):
            errors.append("Empty traceability cell " + rid)
        if status not in STATUSES:
            errors.append("Unknown status " + rid)
        if not re.search(r"P\d{2}", owner):
            errors.append("Missing next prompt " + rid)
    for rid, (requirement, _) in expected.items():
        if rid not in rows:
            errors.append("Omitted source item " + rid)
        elif normalize(rows[rid][2]) != requirement:
            errors.append("Source requirement changed/truncated " + rid)
    return rows, errors


def validate(root=ROOT):
    matrix = root / "docs/completion/requirements_matrix.md"
    expected = source_requirements(root)
    rows, errors = inspect_rows(matrix.read_text(encoding="utf-8"), expected)
    for doc in (matrix, root / 'docs/completion/p00_evidence.md'):
        for link in re.findall(r"\]\(([^)]+)\)", doc.read_text(encoding='utf-8')):
            if re.match(r"https?://|#", link):
                continue
            if not (doc.parent / link.split('#')[0]).resolve().exists():
                errors.append("Broken local link " + link)
    if errors:
        raise SystemExit('\n'.join(errors))
    groups = Counter(rid.split('-')[0] for rid in expected)
    print(f"PASS: {len(expected)} source items, {len(rows)} traceable rows; unique IDs, full requirement text, statuses, next prompts and local links.")
    print(', '.join(f'{key}={value}' for key, value in sorted(groups.items())))
    return rows


if __name__ == '__main__':
    validate()
