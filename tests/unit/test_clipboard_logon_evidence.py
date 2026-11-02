"""Test evidence must report pytest failure even if its wrapper exits zero."""
import json

import pytest

from tests.fixtures.clipboard_logon import recorded_test_exit
from tests.fixtures import clipboard_logon
from docs.completion import run_p01_p13_checks


@pytest.mark.parametrize('code', [0, 1, 2, 5])
def test_recorded_pytest_exit_is_preserved(tmp_path, code):
    report = tmp_path / 'result.json'
    report.write_text(json.dumps({'exit': code}), encoding='utf-8')
    assert recorded_test_exit(report) == code


@pytest.mark.parametrize('payload', [{}, {'exit': False}, {'exit': '0'}, {'exit': -1}])
def test_invalid_report_cannot_claim_success(tmp_path, payload):
    report = tmp_path / 'result.json'
    report.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(ValueError):
        recorded_test_exit(report)


def test_missing_report_cannot_claim_success(tmp_path):
    with pytest.raises(FileNotFoundError):
        recorded_test_exit(tmp_path / 'missing.json')


@pytest.mark.parametrize('module', [clipboard_logon, run_p01_p13_checks])
def test_fresh_audit_directory_refuses_reuse_and_preserves_old_reports(tmp_path, monkeypatch, module):
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    create = (lambda: module.new_output_directory('clipboard-focused-evidence', tmp_path / 'output')) if module is clipboard_logon else (
        lambda: module.new_output_directory(tmp_path / 'output' / 'evidence'))
    directory = create()
    report = directory / 'prior.txt'
    report.write_text('Original failed acceptance evidence', encoding='utf-8')
    with pytest.raises(FileExistsError):
        create()
    assert report.read_text(encoding='utf-8') == 'Original failed acceptance evidence'


@pytest.mark.parametrize('module', [clipboard_logon, run_p01_p13_checks])
def test_audit_directory_must_stay_under_ignored_output(tmp_path, monkeypatch, module):
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    with pytest.raises(ValueError):
        if module is clipboard_logon:
            module.new_output_directory('clipboard-focused-evidence', tmp_path / 'personal')
        else:
            module.new_output_directory(tmp_path / 'personal')
    assert not (tmp_path / 'personal').exists()


@pytest.mark.parametrize('code,suites,expected', [
    (1, [{'tests': '1'}], 1), (0, [], 1), (0, [{'tests': '0'}], 1),
    (0, [{'tests': '1', 'skipped': '1'}], 1),
    (0, [{'tests': '1', 'failures': '1'}], 1),
    (0, [{'tests': '1', 'errors': '1'}], 1),
    (0, [{'tests': '2', 'skipped': '0', 'failures': '0', 'errors': '0'}], 0),
])
def test_acceptance_requires_executed_passing_tests(code, suites, expected):
    assert clipboard_logon.accepted_test_exit(code, suites) == expected
