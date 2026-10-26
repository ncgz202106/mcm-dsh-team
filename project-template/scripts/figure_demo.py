#!/usr/bin/env python3
"""Isolated, explicitly synthetic figure demonstration; no contest result approval."""
from __future__ import annotations
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def new_plot_canvas(style,panels=1):
    """Reusable final-size templates: one plot or two equal stacked panels.

    Add the claim-specific data, units, labels and legends before export.
    A two-panel caller must run require_matplotlib_panel_alignment() on the
    final rendered geometry; template geometry is not a QA attestation.
    """
    import matplotlib.pyplot as plt
    if panels not in (1,2):raise ValueError('Select the single or double-panel template')
    plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':[style.get('font_family','DejaVu Sans')],
        'font.size':style.get('body_font_pt',13),'axes.labelsize':style.get('axis_font_pt',13),
        'axes.titlesize':style.get('title_font_pt',14),'xtick.labelsize':style.get('tick_font_pt',12),
        'ytick.labelsize':style.get('tick_font_pt',12),'legend.fontsize':max(12,style.get('tick_font_pt',12)),
        'pdf.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False,
        'axes.grid':False,'figure.facecolor':'white','savefig.facecolor':'white'})
    width=float(style['final_width_mm'])/25.4
    fig,axes=plt.subplots(panels,1,figsize=(width,4.0 if panels==1 else 7.0),squeeze=False)
    fig.subplots_adjust(left=.17,right=.96,bottom=.19 if panels==1 else .1,top=.86 if panels==1 else .93,hspace=.48)
    return fig,[row[0] for row in axes]

def demo_rows():
    """Solve y'=-k*y, y(0)=1 at k=1 by Euler and classical RK4."""
    h=.1;euler=rk4=1.;rows=[]
    for i in range(41):
        t=i*h
        parameter_values=sorted(math.exp(-(0.7+j*.6/300)*t) for j in range(301))
        rows.append({'time':t,'exact':math.exp(-t),'euler':euler,'rk4':rk4,
                     'k_0_7':math.exp(-.7*t),'k_1_0':math.exp(-t),'k_1_3':math.exp(-1.3*t),
                     'p10':parameter_values[30],'p90':parameter_values[270]})
        euler*=1-h
        a=-rk4;b=-(rk4+h*a/2);c=-(rk4+h*b/2);d=-(rk4+h*c)
        rk4+=h*(a+2*b+2*c+d)/6
    return rows

def generate(root,output='figures/figure-demo',skill_root=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    from figure_check import audit_pdf,check_contract,inside
    root=Path(root).resolve();out=inside(root,output)
    if out.exists():raise ValueError('Use a new demo output directory; existing evidence is not overwritten')
    out.mkdir(parents=True)
    style_path=root/'config/figure-style.json'
    style=json.loads(style_path.read_text(encoding='utf-8'))
    palette=style['palette'];width=style['final_width_mm']/25.4;height=4.0
    read_files=[style_path,root/'protocols/05-paper-figures-latex.md']
    skill=Path(skill_root).resolve() if skill_root else None
    if skill:
        read_files += [skill/x for x in ['SKILL.md','manifest.yaml','static/core/contract.md',
            'static/core/stance.md','static/fragments/backend/python.md','references/qa-contract.md',
            'references/mcm-adaptation.md']]
    skill_read=[]
    for p in read_files:
        text=p.read_text(encoding='utf-8')
        if not text:raise ValueError('Empty figure guidance: '+p.name)
        skill_read.append({'document':p.name,'sha256':digest(p),'read_at':datetime.now(timezone.utc).isoformat()})
    rows=demo_rows();csvpath=out/'decay-results.csv'
    with csvpath.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    # Independent analytic reference, no imported production solver or borrowed data.
    e_error=max(abs(r['euler']-r['exact']) for r in rows)
    rk_error=max(abs(r['rk4']-r['exact']) for r in rows)
    if not (rk_error<1e-5 and rk_error<e_error):raise ValueError('Synthetic solver validation failed')
    validation=out/'analytic-check.json'
    validation.write_text(json.dumps({'synthetic':True,'equation':"y'=-k*y; y(0)=1",'step':.1,
        'points':41,'parameter_grid_count':301,'euler_max_abs_error':e_error,'rk4_max_abs_error':rk_error,
        'passed':True,'scope':'Analytical comparison for this demo; not an independent agent attestation.'},indent=2)+'\n',encoding='utf-8')
    numbers={'FigureDemoEulerError':f'{e_error:.8f}','FigureDemoRKError':f'{rk_error:.8f}',
        'FigureDemoFinalExact':f'{rows[-1]["exact"]:.8f}','FigureDemoRateCount':'301','FigureDemoStep':'0.1'}
    (out/'numbers.tex').write_text('% Generated from the synthetic run; do not edit numbers by hand.\n'+
        ''.join('\\newcommand{\\'+key+'}{'+value+'}\n' for key,value in numbers.items()),encoding='utf-8')
    script=Path(__file__).resolve();contracts=[];t=[r['time'] for r in rows]
    specs=[('method','schematic','The assumed decay equation has an analytical reference and a numerical validation route.',
        'Synthetic method overview. The equation, analytical reference and two numerical solvers form a verifiable comparison; this is not a real-system claim.'),
      ('comparison','quantitative','RK4 follows the analytical reference more closely than Euler at the same step.',
        'Synthetic decay comparison at k=1 and step 0.1, using 41 shared time points. Solid blue: analytical reference; dashed orange: Euler; green markers: RK4. Values and units are dimensionless.'),
      ('sensitivity','quantitative','The decay curve changes with the assumed rate k.',
        'Synthetic parameter sensitivity at k=0.7, 1.0 and 1.3 with identical initial state. Lines are analytical scenario responses, not fitted observations.'),
      ('uncertainty','quantitative','An assumed range of k produces a time-dependent parameter envelope.',
        'Synthetic uncertainty propagation from 301 equally spaced rate values in [0.7,1.3]. Shading is the pointwise 10th-90th percentile of this specified parameter grid, not a confidence interval or measurement error. The line uses k=1.')]
    for name,kind,claim,caption in specs:
        fig,axes=new_plot_canvas(style);ax=axes[0]
        if kind=='schematic':
            ax.set_axis_off();ax.set_xlim(0,1);ax.set_ylim(0,1)
            for x,y,label,color in [(.02,.57,'Assumed equation\nDecay at rate k',palette['blue']),
                (.53,.57,'Numerical solvers\nEuler and RK4',palette['teal']),
                (.02,.08,'Analytical reference\nExponential decay',palette['green']),
                (.53,.08,'Compare and check\nErrors and sensitivity',palette['orange'])]:
                ax.add_patch(FancyBboxPatch((x,y),.42,.26,boxstyle='round,pad=0.015',facecolor='white',edgecolor=color,linewidth=1.8))
                ax.text(x+.21,y+.13,label,ha='center',va='center',fontsize=12)
            for a,b in [((.46,.70),(.51,.70)),((.23,.54),(.23,.38)),((.46,.21),(.51,.21)),((.74,.54),(.74,.38))]:
                ax.annotate('',xy=b,xytext=a,arrowprops={'arrowstyle':'->','color':palette['neutral'],'lw':1.5})
        else:
            ax.set_xlabel('Time (dimensionless)');ax.set_ylabel('Remaining amount (fraction)')
            ax.set_xlim(0,4);ax.set_ylim(0,1.05);ax.set_xticks([0,1,2,3,4]);ax.set_yticks([0,.25,.5,.75,1])
            if name=='comparison':
                ax.plot(t,[r['exact'] for r in rows],label='Analytical',color=palette['blue'],lw=2.2)
                ax.plot(t,[r['euler'] for r in rows],label='Euler',color=palette['orange'],lw=1.8,ls='--')
                ax.plot(t,[r['rk4'] for r in rows],label='RK4',color=palette['green'],lw=1.2,ls=':',marker='o',ms=4,markevery=4)
            elif name=='sensitivity':
                for column,label,color,ls in [('k_0_7','Rate 0.7','teal','--'),('k_1_0','Rate 1.0','blue','-'),('k_1_3','Rate 1.3','orange',':')]:
                    ax.plot(t,[r[column] for r in rows],label=label,color=palette[color],ls=ls,lw=2)
            else:
                ax.fill_between(t,[r['p10'] for r in rows],[r['p90'] for r in rows],color=palette['teal'],alpha=.22,label='Parameter envelope')
                ax.plot(t,[r['exact'] for r in rows],color=palette['blue'],lw=2.2,label='Rate 1.0')
            ax.legend(loc='upper right',frameon=False)
        ax.set_title('Synthetic demonstration',pad=12)
        fig.canvas.draw()
        alignment=out/(name+'.alignment.json')
        alignment.write_text(json.dumps({'status':'not_applicable','reason':'One plot area; no comparable multi-panel groups.',
            'axes_bounds_points':[[v*72 for v in ax.get_window_extent().transformed(fig.dpi_scale_trans.inverted()).bounds]],
            'tolerance_pt':1.5},indent=2)+'\n',encoding='utf-8')
        # Fixed canvas preserves the contracted physical dimensions. Tight-crop
        # export would change them and silently change insertion font sizes.
        outputs=[]
        for ext in ('.pdf','.svg','.png'):
            p=out/(name+ext);fig.savefig(p,dpi=300)
            outputs.append({'path':p.relative_to(root).as_posix(),'sha256':digest(p),'format':ext[1:]})
        plt.close(fig)
        mechanical=audit_pdf(out/(name+'.pdf'),{'width':width*25.4,'height':height*25.4},12)
        qa=out/(name+'.mechanical.json');qa.write_text(json.dumps(mechanical,indent=2)+'\n',encoding='utf-8')
        executions=[{'tool':'figure_check.audit_pdf','status':'passed' if mechanical['ok'] else 'failed',
            'output_refs':[{'path':qa.relative_to(root).as_posix(),'sha256':digest(qa)}]},
            {'tool':'panel_alignment','status':'not_applicable','output_refs':[{'path':alignment.relative_to(root).as_posix(),'sha256':digest(alignment)}]}]
        if skill:
            for tool,args in [('validate_figure.py',[str(script),'--backend','python','--json']),
                ('audit_pdf_text.py',[str(out/(name+'.pdf')),'--min-pt','12','--json']),
                ('audit_figure_collisions.py',[str(out/(name+'.pdf')),'--json'])]:
                command=[sys.executable,str(skill/'scripts'/tool),*args]
                done=subprocess.run(command,text=True,capture_output=True,encoding='utf-8',errors='replace',timeout=90)
                record=out/(name+'.'+tool+'.log');record.write_text(done.stdout+'\n'+done.stderr,encoding='utf-8')
                executions.append({'tool':tool,'status':'passed' if done.returncode==0 else 'failed','exit_code':done.returncode,
                    'command':command,'output_refs':[{'path':record.relative_to(root).as_posix(),'sha256':digest(record)}]})
        contract={'format_version':2,'figure_id':'SYNTHETIC-'+name,'version':1,'synthetic':True,'status':'draft',
            'argument_sentence':claim,'figure_type':kind,'backend':'python','archetype':'single-panel',
            'data_inputs':[] if kind=='schematic' else [{'path':csvpath.relative_to(root).as_posix(),'sha256':digest(csvpath),'synthetic':True}],
            'columns_and_units':{key:'dimensionless' if key=='time' else 'fraction' for key in rows[0]},
            'column_mapping':{'x':'time','y':{'comparison':['exact','euler','rk4'],'sensitivity':['k_0_7','k_1_0','k_1_3'],'uncertainty':['exact','p10','p90']}.get(name,[])},
            'transformation':'No excluded rows; lines use all 41 time points, RK4 markers every fourth point. Parameter quantiles use all 301 deterministic rate scenarios.',
            'uncertainty_definition':'Pointwise parameter-grid percentiles; not sampling confidence.' if name=='uncertainty' else 'Not applicable; deterministic scenarios.',
            'size_mm':{'width':width*25.4,'height':height*25.4},'minimum_final_glyph_pt':12,
            'style_profile':'mcm-clear-science-v2','script_path':script.relative_to(root).as_posix(),'script_sha256':digest(script),
            'generation_command':'python scripts/figure_demo.py --root PROJECT --output NEW_DIRECTORY [--skill-root INSTALLED_SKILL]',
            'outputs':outputs,'caption_english':caption,'paper_label':'fig:demo-'+name,
            'skill_read':skill_read,'skill_executed':executions,'visual_check_ref':None,'visual_status':'pending',
            'numeric_verification_ref':{'path':validation.relative_to(root).as_posix(),'sha256':digest(validation)},
            'qa_readback':{'mechanical_report_sha256':digest(qa),'visual_reviewed':False}}
        cpath=out/(name+'.contract.json');cpath.write_text(json.dumps(contract,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        contracts.append({'path':cpath.relative_to(root).as_posix(),'check':check_contract(root,contract)})
    manifest={'synthetic':True,'created_at':datetime.now(timezone.utc).isoformat(),'contracts':contracts,'visual_status':'pending',
              'note':'Generated and mechanically audited only. No human gate or independent visual review is fabricated.'}
    (out/'demo-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    return manifest

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--output',default='figures/figure-demo');p.add_argument('--skill-root',type=Path);a=p.parse_args()
    try:r=generate(a.root,a.output,a.skill_root)
    except (OSError,ValueError,ImportError,subprocess.SubprocessError) as exc:print(json.dumps({'error':str(exc)}));return 2
    print(json.dumps(r,indent=2));return 0 if all(x['check']['ok'] for x in r['contracts']) else 1
if __name__=='__main__':raise SystemExit(main())
