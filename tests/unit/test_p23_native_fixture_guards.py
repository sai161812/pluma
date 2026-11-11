"""Exercise actual fixture control/storage without native foreground actions."""
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4


def test_history_diagnostics_does_not_shadow_existing_readback_imports(tmp_path):
    root=Path(__file__).resolve().parents[2]
    env={key:value for key,value in os.environ.items() if not key.startswith('PLUMA_')}
    env.update(APPDATA=str(tmp_path/'roaming'),LOCALAPPDATA=str(tmp_path/'local'),
               TEMP=str(tmp_path),TMP=str(tmp_path))
    owned=tmp_path/'fixture';owned.mkdir()
    result=subprocess.run([sys.executable,str(root/'PLUMA.UI/CoreIpc.Tests/fixture_server.py'),
        'pluma_p23_guard_'+uuid4().hex,str(owned),'history'],cwd=root,env=env,
        input='history_diagnostics\nstop\n',text=True,capture_output=True,timeout=15)
    assert result.returncode==0,result.stderr
    assert 'READY' in result.stdout and 'HISTORY_DIAGNOSTICS' in result.stdout
    evidence=json.loads((owned/'folder-diagnostics.json').read_text())
    assert evidence=={'actions':[],'workers':[]}
