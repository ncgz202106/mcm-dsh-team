"""Public, keyless metadata smoke; never reads credentials or downloads full text."""
from pathlib import Path
import argparse, hashlib, json, os, subprocess, sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.parse import quote, urlencode

def fetch(url):
    with urlopen(Request(url,headers={'User-Agent':'MCM-preset-isolated-smoke/0.2.0'}),timeout=20) as r:
        return json.load(r)

def main():
    p=argparse.ArgumentParser();p.add_argument('--skill-root',type=Path,required=True);a=p.parse_args()
    reads={}
    resources={'nature-academic-search':['SKILL.md','manifest.yaml','static/core/tools.md','static/core/routing-and-ops.md','references/workflows/wf1-multi-source-search.md','references/source-tiers.md','references/search-strategy.md','references/dedup-engine.md','scripts/academic_search.py'], 'nature-ref-verifier':['SKILL.md']}
    for name,paths in resources.items():
        for part in paths:
            path=a.skill_root/name/part
            data=path.read_bytes();reads[f'{name}/{part}']=hashlib.sha256(data).hexdigest()
    env={k:v for k,v in os.environ.items() if k.upper() not in {'OPENALEX_API_KEY','CROSSREF_API_KEY','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY'}}
    query='A family of embedded Runge-Kutta formulae'
    search=subprocess.run([sys.executable,str(a.skill_root/'nature-academic-search/scripts/academic_search.py'),query,'--limit','3'],capture_output=True,text=True,encoding='utf-8',env=env,timeout=35)
    observations=[];found=[]
    try:
        found=json.loads(search.stdout) if search.returncode==0 else []
        observations.append({'source':'OpenAlex installed fallback','exit_code':search.returncode,'records':len(found),'error':search.stderr[:800] if search.returncode else None})
    except ValueError:
        observations.append({'source':'OpenAlex installed fallback','error':'non-JSON output','exit_code':search.returncode})
    doi='10.1016/0771-050X(80)90013-3'
    cross=fetch('https://api.crossref.org/works?'+urlencode({'query.title':query,'rows':3}))['message']['items']
    observations.append({'source':'Crossref title search','records':len(cross)})
    record=fetch('https://api.crossref.org/works/'+quote(doi,safe=''))['message']
    fields={'doi':record['DOI'],'title':record['title'][0],'authors':[x.get('family') for x in record.get('author',[])],'year':record.get('published',record.get('issued'))['date-parts'][0][0],'volume':record.get('volume'),'pages':record.get('page')}
    expected={'doi':doi.lower(),'title':query.lower(),'authors':['Dormand','Prince'],'year':1980,'volume':'6','pages':'19-26'}
    matched={k:(str(fields[k]).lower()==str(v).lower()) for k,v in expected.items()}
    independent=None
    try:
        oa=fetch('https://api.openalex.org/works/https://doi.org/'+quote(doi,safe=''))
        independent={'source':'OpenAlex DOI lookup','title':oa.get('title'),'year':oa.get('publication_year'),'doi':oa.get('doi'),'matches':oa.get('publication_year')==1980 and (oa.get('title') or '').casefold()==query.casefold()}
    except Exception as e:independent={'source':'OpenAlex DOI lookup','matches':None,'error':str(e)[:350]}
    out={'checked_at':datetime.now(timezone.utc).isoformat(),'passed':all(matched.values()) and len(cross)>0,'query':query,'skills_read_sha256':reads,'main_skills':['nature-academic-search','nature-ref-verifier'],'execution':'installed no-MCP fallback discovery plus public Crossref search/DOI field checks','sources':observations,'fields':fields,'expected':expected,'field_matches':matched,'independent_crosscheck':independent,'full_text_obtained':False,'human_verification':False,'mcp_search_server_mounted':False,'limitations':['Metadata verification does not establish the accuracy of the paper methods or justify a modeling choice.','Installed optional literature MCP is absent in this isolated test; native tool execution uses the documented public HTTP fallback.']}
    if independent['matches'] is not True:out['limitations'].append('Second-source metadata crosscheck unavailable or inconsistent; full multi-source verification remains incomplete.')
    dest=Path('evidence/public-source-probe.json');dest.parent.mkdir(exist_ok=True);dest.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':out['passed'],'crosscheck':independent['matches'],'output':str(dest)}));return 0 if out['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
