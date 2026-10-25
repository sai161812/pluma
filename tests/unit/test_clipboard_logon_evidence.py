"""Test evidence must report pytest failure even if its wrapper exits zero."""
import json

import pytest

from tests.fixtures.clipboard_logon import recorded_test_exit


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
