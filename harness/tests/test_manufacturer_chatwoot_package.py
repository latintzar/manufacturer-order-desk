"""The transferable package isolates customer state and generates private secrets."""
import json
from pathlib import Path
import subprocess
import sys

import yaml
import pytest

PACKAGE=Path(__file__).resolve().parents[1]/'deploy/chatwoot'


@pytest.mark.parametrize("headless", [False, True])
def test_instance_generator_and_compose_defaults(tmp_path,headless):
    output=tmp_path/'instance'
    result=subprocess.run([sys.executable,str(PACKAGE/'prepare_instance.py'),'--out',str(output),
        '--project','customer-chatwoot','--company-id','company-a','--public-origin','https://communications.example.test',
        '--callback-url','https://manufacturer.example.test/hooks/manufacturer-chatwoot/demo',
        '--operator-email','operator@example.test'] + (['--headless-local'] if headless else []),check=True,capture_output=True,text=True)
    env=dict(line.split('=',1) for line in (output/'.env').read_text().splitlines())
    bootstrap=json.loads((output/'operator/bootstrap-input.json').read_text())
    assert bootstrap['origin']==('http://127.0.0.1:3110' if headless else 'https://communications.example.test')
    assert bootstrap['email']=='' and env['FORCE_SSL']==('false' if headless else 'true')
    assert (output/'.env').stat().st_mode&0o777==0o600
    assert (output/'operator/bootstrap-input.json').stat().st_mode&0o777==0o600
    for key in ('POSTGRES_PASSWORD','REDIS_PASSWORD','SECRET_KEY_BASE','ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY'):
        assert len(env[key])>=64 and env[key] not in result.stdout
    compose=yaml.safe_load((output/'compose.yaml').read_text())
    services=compose['services']
    assert '-ce@sha256:' in services['rails']['image']
    assert services['rails']['ports']==['127.0.0.1:${CHATWOOT_PORT:-3110}:3000']
    assert services['rails']['environment']['SMTP_ADDRESS']=='127.0.0.1'
    assert services['rails']['environment']['SMTP_PORT']=='1'
    assert services['rails']['env_file']=='.env'
    assert 'ports' not in services['postgres'] and 'ports' not in services['redis']
    assert compose['networks']['backend']['internal'] is True
    assert 'name' not in compose['volumes']['postgres']
