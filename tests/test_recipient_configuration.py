"""Private-key and recipient-origin contracts, without provider calls."""
from pathlib import Path
import importlib.util,json,os,sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));import private
sys.path.insert(0,str(ROOT/'app/src/prototypes/orders'));from origin_config import configured_origin

def test_generated_settings_are_private_and_round_trip(tmp_path,capsys):
 values={'ROCOTO_OPENAI_API_KEY':'synthetic-example-value-for-test'};path=private.write(tmp_path/'owned',values)
 assert private.read(tmp_path/'owned')==values
 assert path.stat().st_mode&0o777==0o600 and path.parent.stat().st_mode&0o777==0o700
 assert not capsys.readouterr().out

def test_key_file_symlink_and_hardlink_are_rejected(tmp_path):
 own=tmp_path/'owned';path=private.write(own,{})
 path.rename(own/'original.json');path.symlink_to(own/'original.json')
 with pytest.raises(ValueError):private.read(own)
 path.unlink();os.link(own/'original.json',path)
 with pytest.raises(ValueError):private.read(own)

def test_private_config_keeps_recipient_namespace(tmp_path):
 p=private.directory(tmp_path/'owned')/'credentials.json';p.write_text(json.dumps({'schema':private.SCHEMA,'values':{'UNRELATED_PROVIDER_KEY':'synthetic-test'}}));p.chmod(0o600)
 with pytest.raises(ValueError):private.read(p.parent)

@pytest.mark.parametrize('value',['http://127.0.0.1:18581','http://localhost:8000','https://orders.example.test'])
def test_recipient_origin_accepts_owned_https_and_loopback(value,monkeypatch):
 monkeypatch.setenv('MANUFACTURER_ORDERS_ORIGIN',value);assert configured_origin()==value

@pytest.mark.parametrize('value',['http://example.test','https://name:password@example.test','https://example.test/path','https://example.test/?x=1','file:///tmp/db','https://example.test;script-src*','https://example.test bad','https://example.test:bad'])
def test_recipient_origin_rejects_ambiguous_or_insecure_addresses(value,monkeypatch):
 monkeypatch.setenv('MANUFACTURER_ORDERS_ORIGIN',value)
 with pytest.raises(ValueError):configured_origin()
