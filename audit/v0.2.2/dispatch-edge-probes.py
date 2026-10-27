from pathlib import Path
import importlib.util,json,shutil,tempfile,sys,os
candidate=Path(sys.argv[1]); spec=importlib.util.spec_from_file_location('independent_mcm',candidate/'project-template/scripts/mcm.py');mcm=importlib.util.module_from_spec(spec);spec.loader.exec_module(mcm)
results=[]
def run(name,mutate,expected):
 with tempfile.TemporaryDirectory(prefix='mcm-independent-offline-') as folder:
  root=Path(folder);(root/'.mcm-project').mkdir();shutil.copytree(candidate/'project-template/config',root/'config')
  for name0 in mcm.REGISTRIES:mcm.save_records(root,name0,[])
  (root/'candidate').mkdir();(root/'review').mkdir();(root/'candidate/a.txt').write_text('a');(root/'candidate/handoff.txt').write_text('delivered')
  a={'artifact_id':'A','path':'candidate/a.txt','version':1,'sha256':mcm.file_hash(root/'candidate/a.txt'),'status':'draft','approval_state':'draft','task_id':'AUTHOR','author_agent_id':'author-id','inputs':[]}
  ref={k:a[k] for k in ['artifact_id','path','version','sha256']}
  p={'task_id':'AUTHOR','owner_agent_id':'author-id','status':'in_review','project_root':'.','outputs':[dict(ref)],'output_readback':[dict(ref)],'completion_handoff_path':'candidate/handoff.txt'}
  t={'task_id':'R','owner_role':'mcm-reviewer','owner_agent_id':'pending:child','status':'queued','acceptance_criteria':['Check'],'allowed_write_paths':['review'],'inputs':[ref],'depends_on':[{'task_id':'AUTHOR','relation':'review','output_refs':[dict(ref)],'handoff_ref':{'path':p['completion_handoff_path'],'sha256':mcm.file_hash(root/p['completion_handoff_path'])}}]}
  mutate(root,t,p,a)
  mcm.save_records(root,'tasks',[t,p]);mcm.save_records(root,'artifacts',[a]);before={x:x.read_bytes() for x in root.rglob('*.json')}
  pack=mcm.context_pack(root,'R');assert pack['ready_to_start']==expected,(name,pack['errors']);assert before=={x:x.read_bytes() for x in root.rglob('*.json')}
  results.append({'name':name,'ready_to_start':pack['ready_to_start'],'errors':pack['errors'],'pass':True})
run('valid delivered review ready locally without granting capacity',lambda *x:None,True)
run('producer outside project denied',lambda root,t,p,a:p.update(project_root='candidate'),False)
run('legacy execution delivered but unapproved denied',lambda root,t,p,a:t.update(depends_on=['AUTHOR']),False)
run('read-only review without write scope',lambda root,t,p,a:t.update(read_only=True,allowed_write_paths=[]),True)
run('boolean complete review pin rejected',lambda root,t,p,a:t['depends_on'][0]['output_refs'][0].update(version=True),False)
run('legacy readback with no version accepted',lambda root,t,p,a:p['output_readback'][0].pop('version'),True)
run('hand-off write alias prefix denied',lambda root,t,p,a:t.update(allowed_write_paths=['candidate']),False)
run('boolean version in optional producer readback denied after fix',lambda root,t,p,a:p['output_readback'][0].update(version=True),False)
run('boolean version in optional producer outputs denied after fix',lambda root,t,p,a:p['outputs'][0].update(version=True),False)
print(json.dumps({'scope':'Temporary offline registries only; no Host or model calls','results':results},indent=2))
