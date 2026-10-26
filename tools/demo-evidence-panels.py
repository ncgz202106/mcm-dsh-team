#!/usr/bin/env python3
"""Synthetic two-panel evidence example; never a contest result or approval."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--skill-root',type=Path,required=True)
    a=p.parse_args();repo=Path(__file__).resolve().parents[1];out=a.output.resolve()
    if out.exists():raise ValueError('Use a new output directory to retain fixed evidence')
    out.mkdir(parents=True)
    sys.path.insert(0,str(repo/'project-template/scripts'))
    sys.path.insert(0,str(a.skill_root/'scripts'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from figure_demo import demo_rows,new_plot_canvas
    from figure_check import audit_pdf
    from audit_panel_alignment import require_matplotlib_panel_alignment
    style_path=repo/'bundle/src/figure-style.json';style=json.loads(style_path.read_text())
    guidance=[a.skill_root/x for x in ['SKILL.md','references/mcm-adaptation.md','static/core/contract.md','static/fragments/backend/python.md','references/qa-contract.md']]
    readback=[]
    for path in guidance:
        if not path.read_text(encoding='utf-8').strip():raise ValueError('Empty skill guidance')
        readback.append({'document':path.name,'sha256':digest(path)})
    rows=demo_rows();times=[x['time'] for x in rows];colors=style['palette']
    fig,axes=new_plot_canvas(style,panels=2)
    for column,label,color,linestyle in [('exact','Analytical',colors['neutral'],'-'),('euler','Euler',colors['orange'],'--'),('rk4','RK4',colors['blue'],':')]:
        axes[0].plot(times,[x[column] for x in rows],label=label,color=color,ls=linestyle,lw=2)
    for column,label,color,linestyle in [('euler','Euler',colors['orange'],'--'),('rk4','RK4',colors['blue'],':')]:
        axes[1].plot(times,[abs(x[column]-x['exact']) for x in rows],label=label,color=color,ls=linestyle,lw=2)
    axes[0].set_ylabel('Remaining fraction');axes[1].set_ylabel('Absolute error')
    for ax,label in zip(axes,['(a) Synthetic trajectories','(b) Error against reference']):
        ax.set_xlabel('Time (dimensionless)');ax.set_xlim(0,4);ax.legend(frameon=False,loc='upper right')
        ax.set_title(label,loc='left',pad=10)
    axes[0].set_ylim(0,1.05);axes[1].set_ylim(0,0.023)
    fig.canvas.draw();require_matplotlib_panel_alignment(fig,json_out=out/'alignment.json')
    for extension in ['pdf','svg','png']:fig.savefig(out/('evidence-panels.'+extension),dpi=300)
    plt.close(fig)
    mechanical=audit_pdf(out/'evidence-panels.pdf',{'width':style['final_width_mm'],'height':177.8},12)
    (out/'font-audit.json').write_text(json.dumps(mechanical,indent=2)+'\n')
    checks=[]
    for script,args in [('audit_pdf_text.py',['--min-pt','12','--json']),('audit_figure_collisions.py',['--json'])]:
        result=subprocess.run([sys.executable,str(a.skill_root/'scripts'/script),str(out/'evidence-panels.pdf'),*args],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        # Logs are local; the portable report retains hashes rather than command paths.
        (out/(script+'.log')).write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
        checks.append({'tool':script,'exit_code':result.returncode})
    metadata={'synthetic':True,'style_sha256':digest(style_path),'skill_read':readback,'data_rows':41,
        'panel_plan':[{'panel':'a','role':'shared-input comparison'},{'panel':'b','role':'reference-error evidence'}],
        'passed_mechanical':mechanical['ok'] and all(x['exit_code']==0 for x in checks),'checks':checks,
        'visual_status':'pending','caption':'Synthetic decay y\u2032=-y with initial value 1 and shared step 0.1. Panel a compares trajectories; panel b shows absolute error against the analytical reference. All 41 time points are used; deterministic solver errors are not confidence intervals.',
        'outputs':[{'file':'evidence-panels.'+ext,'sha256':digest(out/('evidence-panels.'+ext))} for ext in ['pdf','svg','png']]}
    (out/'demo.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed_mechanical':metadata['passed_mechanical'],'visual_status':'pending','output':str(out)}))
    return 0 if metadata['passed_mechanical'] else 1
if __name__=='__main__':raise SystemExit(main())
