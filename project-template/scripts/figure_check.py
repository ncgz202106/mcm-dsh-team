#!/usr/bin/env python3
"""Audit fixed figure files and provenance. Geometry checks do not certify beauty."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def inside(root, relative):
    root=Path(root).resolve(); p=Path(relative)
    result=(root/p).resolve()
    if p.is_absolute() or '..' in p.parts or not result.is_relative_to(root):
        raise ValueError('Figure reference escapes project: '+str(relative))
    return result

def check_optional_design(root, contract):
    """Check declared design metadata without judging the evidence or aesthetics."""
    errors=[]
    panels=contract.get('panel_plan')
    if panels is not None:
        if not isinstance(panels,list):
            errors.append('panel_plan must be a list when supplied')
        else:
            identifiers=set()
            for index,panel in enumerate(panels,1):
                location=f'panel_plan item {index}'
                if not isinstance(panel,dict):
                    errors.append(location+' must be an object');continue
                for field in ('panel','question','evidence_role','main_takeaway'):
                    if not isinstance(panel.get(field),str) or not panel[field].strip():
                        errors.append(location+' has missing/invalid '+field)
                identifier=panel.get('panel')
                if isinstance(identifier,str) and identifier.strip():
                    if identifier.strip() in identifiers:errors.append(location+' duplicates panel identifier')
                    identifiers.add(identifier.strip())
                fields=panel.get('input_fields')
                if not isinstance(fields,list) or any(not isinstance(field,str) or not field.strip() for field in fields):
                    errors.append(location+' input_fields must be a list of non-empty strings')
    style_ref=contract.get('style_config_ref')
    if style_ref is not None:
        if not isinstance(style_ref,dict):
            errors.append('style_config_ref must be a fixed reference object')
        else:
            path=style_ref.get('path');version=style_ref.get('version');sha=style_ref.get('sha256')
            if not isinstance(path,str) or not path.strip():
                errors.append('style_config_ref has missing/invalid path')
            else:
                try:
                    pinned=inside(root,path)
                    if pinned!=(Path(root)/'config/figure-style.json').resolve():
                        errors.append('style_config_ref must pin the project config/figure-style.json')
                    if not pinned.is_file() or digest(pinned)!=sha:
                        errors.append('style_config_ref is missing or changed')
                except (OSError,ValueError) as exc:errors.append(str(exc))
            if not isinstance(version,int) or isinstance(version,bool) or version<1:
                errors.append('style_config_ref version must be a positive artifact version')
            if not isinstance(sha,str) or len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):
                errors.append('style_config_ref sha256 must be a lowercase SHA256 digest')
            inputs=contract.get('data_inputs',[])
            if not isinstance(inputs,list) or not any(isinstance(ref,dict) and all(ref.get(key)==style_ref.get(key) for key in ('path','version','sha256')) for ref in inputs):
                errors.append('style_config_ref must also be the same fixed path/version/sha256 task input in data_inputs')
    return errors

def audit_pdf(pdf, size_mm=None, min_font_pt=12):
    from pypdf import PdfReader
    reader=PdfReader(pdf); errors=[]; runs=[]
    if len(reader.pages)!=1:errors.append('Figure PDF must have one page')
    for index,page in enumerate(reader.pages,1):
        box=page.cropbox
        left,bottom,right,top=map(float,(box.left,box.bottom,box.right,box.top))
        width,height=right-left,top-bottom
        scale=1.0
        if size_mm:
            wanted_w=float(size_mm['width'])/25.4*72
            wanted_h=float(size_mm['height'])/25.4*72
            if wanted_w<=0 or wanted_h<=0:raise ValueError('Figure dimensions must be positive')
            scale=wanted_w/width
            if abs(height*scale-wanted_h)>1.5:
                errors.append('Figure PDF aspect ratio differs from final dimensions')
        def visit(text,cm,tm,font,size):
            if not text.strip():return
            # Effective font size includes PDF text and graphics transforms and
            # the final insertion scale, rather than only the raw Tf operator.
            a=tm[0]*cm[0]+tm[1]*cm[2];b=tm[0]*cm[1]+tm[1]*cm[3]
            c=tm[2]*cm[0]+tm[3]*cm[2];d=tm[2]*cm[1]+tm[3]*cm[3]
            effective=abs(size)*min(math.hypot(a,b),math.hypot(c,d))*scale
            x=tm[4]*cm[0]+tm[5]*cm[2]+cm[4]
            y=tm[4]*cm[1]+tm[5]*cm[3]+cm[5]
            runs.append({'text':text.strip()[:60],'final_size_pt':round(effective,3)})
            if effective<min_font_pt-0.03:
                errors.append(f'Page {index}: font below {min_font_pt}pt at final size: {text.strip()[:35]} ({effective:.2f}pt)')
            if x<left-1 or x>right+1 or y<bottom-1 or y>top+1:
                errors.append(f'Page {index}: text origin outside CropBox: {text.strip()[:35]}')
        page.extract_text(visitor_text=visit)
    if not runs:errors.append('No auditable text in figure PDF; raster/outlined text needs manual size verification')
    return {'ok':not errors,'errors':errors,'minimum_final_font_pt':min((x['final_size_pt'] for x in runs),default=None),
            'text_runs':runs,'visual_status':'pending','limitations':['Text-origin checks do not prove complete glyph/line/image containment.','No automated aesthetic or scientific correctness certification.']}

def check_contract(root,contract,release=False):
    root=Path(root).resolve()
    if not isinstance(contract,dict):contract=json.loads(inside(root,contract).read_text(encoding='utf-8'))
    design_errors=check_optional_design(root,contract);errors=list(design_errors);checks=[]
    if contract.get('_template_only'):errors.append('Figure contract is still a template')
    for key in ('figure_id','argument_sentence','figure_type','transformation','caption_english','script_path','size_mm'):
        if not contract.get(key):errors.append('Missing figure contract field: '+key)
    if release and contract.get('synthetic'):errors.append('Synthetic demonstration cannot be released as competition evidence')
    if contract.get('figure_type')!='schematic' and not contract.get('data_inputs'):errors.append('Quantitative figure has no fixed data inputs')
    formats={Path(x.get('path','')).suffix.lower() for x in contract.get('outputs',[])}
    if not {'.pdf','.svg','.png'}.issubset(formats):errors.append('Figure bundle requires PDF, SVG and PNG outputs')
    minimum=12
    style_path=root/'config/figure-style.json'
    if style_path.is_file():minimum=float(json.loads(style_path.read_text(encoding='utf-8')).get('minimum_final_glyph_pt',12))
    if contract.get('minimum_final_glyph_pt',minimum)<minimum:errors.append('Contract font floor weakens the project style requirement')
    for ref in contract.get('data_inputs',[])+contract.get('outputs',[]):
        try:
            p=inside(root,ref.get('path',''))
            if not p.is_file() or digest(p)!=ref.get('sha256'):errors.append('Missing/changed figure input or output: '+ref.get('path',''))
            elif p.suffix.lower()=='.pdf' and ref in contract.get('outputs',[]):
                result=audit_pdf(p,contract.get('size_mm'),max(minimum,contract.get('minimum_final_glyph_pt',minimum)));checks.append(result);errors.extend(result['errors'])
            elif p.suffix.lower()=='.png' and ref in contract.get('outputs',[]):
                from PIL import Image
                with Image.open(p) as image:
                    dpi=image.info.get('dpi',(0,0))
                    if len(dpi)!=2 or min(dpi)<299:
                        errors.append('Figure PNG does not record at least 300dpi: '+ref.get('path',''))
                    dimensions=contract.get('size_mm',{})
                    if dimensions and min(dpi)>0:
                        actual=[image.width/dpi[0]*25.4,image.height/dpi[1]*25.4]
                        if any(abs(actual[i]-dimensions.get(k,0))>.3 for i,k in enumerate(('width','height'))):
                            errors.append('Figure PNG dimensions differ from contracted final size: '+ref.get('path',''))
        except (OSError,ValueError) as exc:errors.append(str(exc))
    try:
        script=inside(root,contract.get('script_path',''))
        if not script.is_file() or digest(script)!=contract.get('script_sha256'):errors.append('Plotting script missing or changed')
    except (OSError,ValueError) as exc:errors.append(str(exc))
    if not contract.get('skill_read'):errors.append('No record of the figure guidance actually read')
    executed=contract.get('skill_executed',[])
    if not executed or not all(x.get('status') in ('passed','not_applicable') for x in executed):errors.append('Figure QA execution is missing or failed')
    for item in executed:
        for ref in item.get('output_refs',[]):
            try:
                p=inside(root,ref.get('path',''))
                if not p.is_file() or digest(p)!=ref.get('sha256'):errors.append('QA readback digest changed: '+ref.get('path',''))
            except (OSError,ValueError) as exc:errors.append(str(exc))
    # Declaring a path is different from actually observing a review. This tool
    # leaves visual status pending; paper release validates an independent file.
    return {'ok':not errors,'errors':errors,'pdf_checks':checks,'figure_id':contract.get('figure_id'),
            'visual_status':'pending','design_metadata_status':'valid' if not design_errors else 'invalid',
            'design_metadata_scope':'Structure and fixed references only; panel complementarity and aesthetics remain unassessed.',
            'synthetic':contract.get('synthetic',False)}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('contract');p.add_argument('--release',action='store_true');a=p.parse_args()
    try:r=check_contract(a.root,a.contract,a.release)
    except (OSError,ValueError,ImportError) as exc:r={'ok':False,'errors':[str(exc)]}
    print(json.dumps(r,ensure_ascii=False,indent=2));return 0 if r['ok'] else 1
if __name__=='__main__':raise SystemExit(main())
