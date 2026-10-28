import json
import os
import subprocess
import sys
from pathlib import Path

import manufacturer
import pytest

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "packs" / "manufacturer"


def run_python(source, program, *arguments):
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(source), str(source / "tests"), str(ROOT), str(ROOT.parents[3])]
    )
    return subprocess.run(
        [sys.executable, "-c", program, str(PACK), *map(str, arguments)],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    ).stdout


def test_generated_managed_manifest_roles_and_recipe_are_current():
    data = manufacturer.contract()
    legacy = json.loads((PACK / "pack.json").read_text())
    assert json.loads((PACK / "vertical.json").read_text()) == manufacturer.managed_manifest(legacy)
    assert json.loads((PACK / "sub_agents.json").read_text()) == manufacturer.managed_roles(data)
    assert json.loads((PACK / "recipes/catalogue-readiness.json").read_text()) == manufacturer.managed_recipe(
        data
    )
    assert legacy["schema"] == "rocoto.pack.v1" and legacy["recipes"] == []
    assert [role["model"] for role in manufacturer.managed_roles(data)] == [
        "gpt-5.6-luna",
        "gpt-6-astra",
    ]


def test_stage_plan_distinguishes_declared_roles_from_legacy_planning_metadata():
    index = manufacturer.stage_plan()
    assert (
        next(row for row in index["stages"] if row["id"] == "catalogue")["declared_managed_role"]
        == "catalogue_reader"
    )
    assert manufacturer.stage_plan("store")["model_selection"] == "planning_only"
    assert manufacturer.stage_plan("store")["declared_managed_role"] == "readiness_judge"
    assert manufacturer.stage_plan("pictures")["model_selection"] == "planning_only"
    assert "pinned b512" in manufacturer.contract()["model_binding"]


def test_current_and_pinned_harness_load_their_own_manifest_contracts(tmp_path):
    current = os.environ.get("ORDERS_MANAGED_HARNESS_SOURCE")
    pinned = os.environ.get("ORDERS_LEGACY_HARNESS_SOURCE")
    if not current or not pinned:
        pytest.skip("Set current and legacy harness sources for the dual-loader proof.")
    current_result = json.loads(
        run_python(
            Path(current),
            """
import json, pathlib, sys
import layout
layout.install()
import pack
loaded=pack.load(pathlib.Path(sys.argv[1]))
print(json.dumps({'manifest':loaded.manifest_path.name,'recipes':[r['id'] for r in loaded.recipes()],
 'roles':[(r['id'],r['model']) for r in loaded.sub_agents()]}))
""",
        )
    )
    assert current_result == {
        "manifest": "vertical.json",
        "recipes": ["catalogue_readiness"],
        "roles": [["catalogue_reader", "gpt-5.6-luna"], ["readiness_judge", "gpt-6-astra"]],
    }
    pinned_result = json.loads(
        run_python(
            Path(pinned),
            """
import json, os, pathlib, sys
from harness_launcher import load_contract
source=pathlib.Path(os.environ['PYTHONPATH'].split(os.pathsep)[0])
pack=load_contract(source)
loaded=pack.load(pathlib.Path(sys.argv[1]))
print(json.dumps({'schema':loaded.manifest['schema'],'recipes':loaded.manifest['recipes']}))
""",
        )
    )
    assert pinned_result == {"schema": "rocoto.pack.v1", "recipes": []}


def test_current_recipe_get_begin_record_scope_and_fake_provider_delegation(tmp_path):
    current = os.environ.get("ORDERS_MANAGED_HARNESS_SOURCE")
    if not current:
        pytest.skip("Set ORDERS_MANAGED_HARNESS_SOURCE for the managed recipe proof.")
    receipt = json.loads(
        run_python(
            Path(current),
            """
import asyncio, copy, dataclasses, json, pathlib, sys
from types import SimpleNamespace
import layout
layout.install()
import pack
from host import Admission
from managed_sessions import ManagedSessions
from recipe_runs import RecipeRuns, call as recipe_call, read as recipe_read
from tool_families import ToolContext, ToolRegistry
from workspace_identity import workspace_scope
import delegated_jobs

vertical=pack.load(pathlib.Path(sys.argv[1]))
state=pathlib.Path(sys.argv[2])
record={'id':'chat','owner_principal_id':'alice','dataset':'company','messages':[],
        'organization_purpose':'organization'}
run={'cancel':asyncio.Event()}
agent=SimpleNamespace(children={'chat':record},active={'chat':run},
    organization_chats=SimpleNamespace(canonical=lambda row: row is record))
ctx=ToolContext(state=state,company_id=workspace_scope(state),actor='alice',data_owner='alice',
    collection='company',chat_id='chat',record=record,run=run,agent=agent,
    admission=Admission(lambda:True))
with pack.use(vertical):
    got=recipe_read(ctx,'get_recipe',{'recipe_id':'catalogue_readiness'})
    saved=recipe_call(ctx,'begin_recipe',{'recipe_id':'catalogue_readiness'})
    saved=recipe_call(ctx,'record_recipe_step',{'run_id':saved['id'],'expected_revision':1,
        'step_id':'catalogue','status':'completed','note':'Observed source rows.',
        'evidence':['catalogue-check.json:passed']})
    saved=recipe_call(ctx,'record_recipe_step',{'run_id':saved['id'],'expected_revision':2,
        'step_id':'readiness','status':'completed','note':'Observed current readiness.',
        'evidence':['store-check.json:passed']})
    foreign=dataclasses.replace(ctx,data_owner='bob',actor='bob',record={**record,'owner_principal_id':'bob'})
    try: RecipeRuns(state).get(foreign,saved['id'])
    except ValueError: foreign_denied=True
    else: foreign_denied=False
    agent.organization_chats.canonical=lambda row:False
    try: recipe_call(ctx,'begin_recipe',{'recipe_id':'catalogue_readiness'})
    except ValueError: launcher_denied=True
    else: launcher_denied=False

role=vertical.sub_agent('catalogue_reader')
class Reads:
    READ_NAMES=frozenset(role['tools']); WRITE_NAMES=frozenset()
    @staticmethod
    def specs(write=True):
        return [{'name':name,'description':'Recorded fake read',
                 'inputSchema':{'type':'object','properties':{},'additionalProperties':False}}
                for name in role['tools']]
    @staticmethod
    def read(context,name,arguments):
        return {'evidence':'recorded-fixture'}
family=Reads()
delegate_state=state/'delegate';scope=workspace_scope(delegate_state)
ledger=ManagedSessions(delegate_state)
binding=ledger.binding(company_id=scope,chat_id='chat',owner='owner',collection='company',
    configuration={'fixture':'recorded-provider'})
request=ledger.request(binding['id'],'request-1',[{'role':'user','content':'Review'}])
parent={'id':'chat','owner_principal_id':'owner','dataset':'company','messages':[],
        'organization_purpose':'organization'}
engine=SimpleNamespace(binding=binding,request=request,require_current=lambda:None)
run={'cancel':asyncio.Event(),'managed_engine':engine,
     'managed_lease':SimpleNamespace(request_id=request['id']),'role_plan':[role],
     'child_ids':set(),'tool_events':asyncio.Queue(),'delegated_tasks':{}}
agent=SimpleNamespace(state=delegate_state,children={'chat':parent},active={'chat':run},
    organization_chats=SimpleNamespace(canonical=lambda row: row is parent),
    tool_registry=ToolRegistry((family,delegated_jobs.FAMILY)),
    _authority_principal=lambda chat_id:'owner',_save_child=lambda child:None)
ctx=ToolContext(delegate_state,scope,'owner','owner','company','chat',parent,run,agent=agent,
    admission=Admission(lambda:True))
store=delegated_jobs.DelegatedJobs(delegate_state)
captured={}
async def recorded_provider(context,job,child,grant):
    captured['configuration']=grant.configuration(agent.tool_registry.specs(True))
    child['messages'][-1]['content']='Recorded catalogue evidence'
    job['status']='completed';child['status']='completed';store.save(job)
store._run=recorded_provider
call={'binding_id':binding['id'],'request_id':request['id'],'turn_id':'turn-1','call_id':'call-1'}
async def execute():
    with pack.use(vertical):
        result=await store.execute(ctx,role,'Read catalogue evidence',call)
        invented={**role,'id':'invented'}
        denied=False
        try: await store.execute(ctx,invented,'Read catalogue evidence',{**call,'call_id':'call-2'})
        except ValueError: denied=True
        return result,denied
result,role_denied=asyncio.run(execute())
print(json.dumps({'recipe':got['recipe']['id'],'roles':[r['id'] for r in got['sub_agents']],
 'recipe_status':saved['status'],'foreign_denied':foreign_denied,'launcher_denied':launcher_denied,
 'delegate_status':result['status'],'child_model':captured['configuration']['agent']['model'],
 'child_tools':[row['name'] for row in captured['configuration']['agent']['tools']],
 'unknown_role_denied':role_denied}))
""",
            tmp_path,
        )
    )
    assert receipt == {
        "recipe": "catalogue_readiness",
        "roles": ["catalogue_reader", "readiness_judge"],
        "recipe_status": "completed",
        "foreign_denied": True,
        "launcher_denied": True,
        "delegate_status": "completed",
        "child_model": "gpt-5.6-luna",
        "child_tools": ["catalog_find", "catalog_read", "run_stage_plan", "run_read"],
        "unknown_role_denied": True,
    }
