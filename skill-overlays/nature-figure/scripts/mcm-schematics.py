#!/usr/bin/env python3
"""Original, explicitly synthetic scientific schematic recipes.

Single vector route: Matplotlib, with editable SVG text. This is not a
Fireworks generator, scientific simulator, trained ensemble or safety proof.
Requires the existing matplotlib/Pillow environment; never installs or calls a model.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch, Ellipse
from matplotlib.colors import to_rgb
from matplotlib.path import Path as MplPath

RECIPES = ('taxonomy', 'ensemble', 'feedback')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pale(color, strength=.09):
    return tuple(1-strength+strength*c for c in to_rgb(color))


def topology(recipe):
    if recipe == 'taxonomy':
        return {'nodes': [{'id': x, 'label': label} for x, label in [
            ('answer', 'Answer evidence'), ('model', 'Model'), ('validation', 'Validation'),
            ('choice', 'Recommendation'), ('states', 'Defined states'), ('terms', 'Mechanism terms'),
            ('baseline', 'Baseline tests'), ('error', 'Error bounds'),
            ('options', 'Feasible choices'), ('limits', 'Failure conditions')]],
            'edges': [{'source': s, 'target': t, 'kind': 'classification', 'directed': False}
                      for s,t in [('answer','model'), ('answer','validation'), ('answer','choice'),
                                  ('model','states'), ('model','terms'), ('validation','baseline'),
                                  ('validation','error'), ('choice','options'), ('choice','limits')]],
            'scope': 'Organizational taxonomy only; links do not establish causation or exclusivity.'}
    if recipe == 'ensemble':
        weights = [.50, .30, .20]
        return {'nodes': [{'id': x, 'label': label} for x,label in [
            ('input','Shared input'), ('a','Candidate A'), ('b','Candidate B'),
            ('c','Candidate C'), ('mix','Weighted estimate'), ('output','Combined output')]],
            'edges': ([{'source':'input','target':x,'kind':'shared_input','directed':True} for x in 'abc']+
                      [{'source':x,'target':'mix','kind':'weighted_prediction','weight':w,'directed':True}
                       for x,w in zip('abc',weights)]+
                      [{'source':'mix','target':'output','kind':'estimate','directed':True}]),
            'scope': 'Scalar-output weighted aggregation with fixed illustrative weights; no training, accuracy or benefit is demonstrated.'}
    if recipe == 'feedback':
        return {'nodes':[{'id':x,'label':label} for x,label in [
            ('agent','Decision rule'), ('gate','Action\nconstraint'), ('environment','System')]],
            'edges':[
                {'source':'agent','target':'gate','kind':'proposed_action','directed':True},
                {'source':'gate','target':'environment','kind':'admissible_action','directed':True},
                {'source':'environment','target':'agent','kind':'observed_state','directed':True},
                {'source':'environment','target':'agent','kind':'measured_feedback','directed':True}],
            'scope':'The constraint acts on actions only. Observation and feedback are distinct return channels. The feasible-set sketch is illustrative, not a safety guarantee.'}
    raise ValueError('Unknown schematic recipe')


def validate_topology(graph):
    ids=[n['id'] for n in graph['nodes']]
    if len(set(ids)) != len(ids) or not ids:
        raise ValueError('Node identities must be unique and nonempty')
    for edge in graph['edges']:
        if edge['source'] not in ids or edge['target'] not in ids:
            raise ValueError('Every edge endpoint must be a declared node')
        if edge['source']==edge['target']:
            raise ValueError('Self-loop not used by these recipes')
        if not isinstance(edge.get('directed'), bool):
            raise ValueError('Edge direction must be explicit')
        if edge['kind']=='classification' and edge['directed']:
            raise ValueError('Classification links must not imply causal flow')
    weighted=[e for e in graph['edges'] if e['kind']=='weighted_prediction']
    if weighted:
        w=[e.get('weight') for e in weighted]
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in w) or not math.isclose(sum(w),1,abs_tol=1e-12):
            raise ValueError('Nonnegative finite aggregation weights must sum to one')
    if any(n['id']=='gate' for n in graph['nodes']):
        incident=[e['kind'] for e in graph['edges'] if e['source']=='gate' or e['target']=='gate']
        if sorted(incident)!=['admissible_action','proposed_action']:
            raise ValueError('The action gate must not intercept state or feedback')


def build(recipe, style):
    graph=topology(recipe);validate_topology(graph)
    minimum=max(12,float(style.get('minimum_final_glyph_pt',12)))
    width=float(style.get('final_width_mm',165.1))
    if not math.isfinite(width) or width<=0:
        raise ValueError('Positive finite final width required')
    height={'taxonomy':73.66,'ensemble':81.28,'feedback':96.52}[recipe]
    colors=style['palette'];ink='#263445'
    plt.rcParams.update({'font.family':style['font_family'], 'font.size':minimum,
                         'svg.fonttype':'none','pdf.fonttype':42,
                         'figure.facecolor':'white','savefig.facecolor':'white'})
    fig=plt.figure(figsize=(width/25.4,height/25.4))
    ax=fig.add_axes([0,0,1,1]);ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
    boxes={};node_text={};texts=[];routes=[]

    def text(x,y,label,**kwargs):
        kwargs.setdefault('color',ink);kwargs.setdefault('fontsize',minimum)
        t=ax.text(x,y,label,ha=kwargs.pop('ha','center'),va='center',
                  linespacing=1.3,**kwargs);texts.append(t);return t
    def box(identifier,x,y,w,h,color):
        node=next(n for n in graph['nodes'] if n['id']==identifier)
        patch=Rectangle((x,y),w,h,facecolor=pale(color,.045) if identifier=='gate' else 'white',
                        edgecolor=color,linewidth=.65)
        ax.add_patch(patch);boxes[identifier]=(x,y,w,h)
        node_text[identifier]=text(x+w/2,y+h/2,node['label'])
    def line(points,color,arrow=True,dashed=False):
        routes.append(points)
        x,y=zip(*points)
        ax.plot(x,y,color=color,lw=.8,ls=(0,(4,3)) if dashed else '-',solid_capstyle='butt')
        if arrow:
            ax.add_patch(FancyArrowPatch(points[-2],points[-1],arrowstyle='-|>',
                mutation_scale=9,lw=.8,color=color,shrinkA=0,shrinkB=0,
                linestyle=(0,(4,3)) if dashed else '-'))

    if recipe=='taxonomy':
        labels={n['id']:n['label'] for n in graph['nodes']}
        text(.02,.52,labels['answer'],ha='left')
        groups=[('model',.78,colors['blue']),('validation',.52,colors['teal']),('choice',.26,colors['orange'])]
        leaves=[('states','terms'),('baseline','error'),('options','limits')]
        for (group,y,color),pair in zip(groups,leaves):
            text(.365,y,labels[group],ha='left',color=color)
            line([(.255,.52),(.305,.52),(.305,y),(.35,y)],colors['neutral'],False)
            for leaf,offset in zip(pair,[.085,-.085]):
                text(.735,y+offset,labels[leaf],ha='left')
                line([(.625,y),(.675,y),(.675,y+offset),(.72,y+offset)],color,False)
    elif recipe=='ensemble':
        for node in graph['nodes']:
            node['label']={'input':'Shared\ninput','mix':'Weighted\nestimate','output':'Output'}.get(node['id'],node['label'])
        box('input',.02,.41,.15,.18,colors['neutral'])
        ys=[.79,.50,.21]
        for name,y,color in zip('abc',ys,[colors['blue'],colors['teal'],colors['orange']]):
            box(name,.27,y-.055,.22,.11,colors['neutral'])
            line([(.17,.5),(.215,.5),(.215,y),(.27,y)],colors['neutral'])
        box('mix',.65,.41,.18,.18,colors['neutral'])
        for y,port,w,label_y,color in zip(ys,[.53,.5,.47],[.5,.3,.2],[.76,.56,.24],[colors['blue'],colors['teal'],colors['orange']]):
            line([(.49,y),(.65,port)],color)
            text(.57,label_y,f'{w:.2f}',color=color)
        box('output',.87,.43,.11,.14,colors['neutral'])
        line([(.83,.5),(.87,.5)],colors['neutral'])
    else:
        for node in graph['nodes']:
            if node['id']=='agent':node['label']='Decision\nrule'
        box('agent',.035,.70,.22,.18,colors['neutral'])
        box('gate',.39,.70,.20,.18,colors['green'])
        box('environment',.77,.70,.20,.18,colors['neutral'])
        line([(.255,.79),(.39,.79)],colors['orange'])
        text(.32,.94,'Action',color=colors['orange'])
        line([(.59,.79),(.77,.79)],colors['orange'])
        text(.68,.94,'Admissible',color=colors['orange'])
        line([(.82,.70),(.82,.49),(.16,.49),(.16,.70)],colors['blue'])
        text(.50,.525,'Observed state',color=colors['blue'])
        line([(.92,.70),(.92,.31),(.08,.31),(.08,.70)],colors['teal'],dashed=True)
        text(.50,.345,'Measured feedback',color=colors['teal'])
        ax.add_patch(Ellipse((.26,.135),.24,.13,facecolor=pale(colors['green'],.045),
                             edgecolor=colors['green'],ls=(0,(3,2)),lw=.7))
        text(.26,.135,'Feasible\nactions')
        ax.plot([.38],[.135],marker='o',color=colors['green'],ms=4)
        ax.plot([.75],[.135],marker='o',color=colors['orange'],ms=4)
        line([(.733,.135),(.397,.135)],colors['orange'])
        text(.75,.215,'Proposed')
        text(.48,.09,'Admissible')
        graph['feasible_set_example']={'geometry':'ellipse, schematic coordinates only',
            'center':[.26,.135],'radii':[.12,.065],'proposed':[.75,.135],
            'mapped':[.38,.135],'claim':'Example boundary mapping only; not a general control or safety proof.'}
    text(.80 if recipe=='feedback' else .5,.06,'Synthetic schematic',color=colors['neutral'])
    fig.canvas.draw()
    renderer=fig.canvas.get_renderer();canvas=fig.bbox
    errors=[]
    for t in texts:
        bounds=t.get_window_extent(renderer)
        if not (canvas.x0<=bounds.x0 and canvas.x1>=bounds.x1 and canvas.y0<=bounds.y0 and canvas.y1>=bounds.y1):
            errors.append('Text exceeds canvas: '+t.get_text())
    for name,t in node_text.items():
        x,y,w,h=boxes[name]
        lower=ax.transData.transform((x,y));upper=ax.transData.transform((x+w,y+h))
        bounds=t.get_window_extent(renderer)
        if not (bounds.x0>lower[0]+2 and bounds.x1<upper[0]-2 and bounds.y0>lower[1]+2 and bounds.y1<upper[1]-2):
            errors.append('Node text lacks internal clearance: '+name)
    for i,a in enumerate(texts):
        a_box=a.get_window_extent(renderer)
        for b in texts[i+1:]:
            b_box=b.get_window_extent(renderer)
            if a_box.overlaps(b_box):
                errors.append('Text overlap: '+a.get_text()+' / '+b.get_text())
    for route in routes:
        pixels=ax.transData.transform(route)
        path=MplPath(pixels)
        for t in texts:
            bounds=t.get_window_extent(renderer).padded(1)
            if path.intersects_bbox(bounds,filled=False) or any(bounds.contains(*p) for p in pixels):
                errors.append('Connector crosses text: '+t.get_text())
    qa={'passed':not errors,'errors':errors,'checked':'Actual Matplotlib rendered text bounds, pairwise text overlap, node internal clearance, connector-versus-text intersection and full canvas containment.',
        'limits':'Semantic interpretation and final-page layout require actual visual inspection. Not the Fireworks semantic SVG validator.'}
    if errors:
        plt.close(fig);raise ValueError('; '.join(errors))
    graph.update({'recipe':recipe,'synthetic':True,'diagram_kind':'conceptual schematic',
        'final_width_mm':width,'final_height_mm':height,'minimum_core_font_pt':minimum,
        'presentation_profile':'compact scientific schematic; thin square outlines or unboxed taxonomy, no in-figure headline',
        'label_manifest':[t.get_text() for t in texts],'boxes':boxes,'routes':routes,'geometry_check':qa})
    return fig,graph


def export(recipe, output, style_path):
    output=Path(output)
    if output.exists():raise ValueError('Output already exists; choose a new directory')
    style_path=Path(style_path);style=json.loads(style_path.read_text(encoding='utf-8'))
    fig,graph=build(recipe,style)
    output.mkdir(parents=True,exist_ok=False)
    for fmt in ['pdf','svg','png']:
        fig.savefig(output/(recipe+'.'+fmt),dpi=max(300,int(style.get('raster_dpi',300))))
    plt.close(fig)
    caption='Synthetic schematic. '+graph['scope']+' Core labels are designed for the stated full insertion width; do not shrink below the project font floor.'
    (output/'caption.md').write_text(caption+'\n',encoding='utf-8')
    graph.update({'script_sha256':digest(__file__),'style_sha256':digest(style_path),
                  'vector_route':'Matplotlib PDF and editable-text SVG; Fireworks generator not invoked',
                  'visual_review':{'status':'pending','author_self_check_not_independent':True},
                  'files':{p.name:digest(p) for p in sorted(output.iterdir()) if p.is_file()}})
    (output/'mapping.json').write_text(json.dumps(graph,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return graph


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe',choices=(*RECIPES,'all'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--style',type=Path,default=Path(__file__).resolve().parents[1]/'assets/mcm-figure-style.json')
    args=parser.parse_args(argv)
    if args.recipe=='all':
        if args.output.exists():parser.error('Output already exists')
        args.output.mkdir(parents=True)
        rows=[export(recipe,args.output/recipe,args.style) for recipe in RECIPES]
    else:rows=[export(args.recipe,args.output,args.style)]
    print(json.dumps({'recipes':[r['recipe'] for r in rows],'geometry_passed':all(r['geometry_check']['passed'] for r in rows),
                      'visual_review':'pending','synthetic':True}))


if __name__=='__main__':main()
