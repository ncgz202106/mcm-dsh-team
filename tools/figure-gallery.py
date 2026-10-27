#!/usr/bin/env python3
"""Original synthetic MCM figure families and page examples; never contest evidence."""
from __future__ import annotations
import argparse,csv,hashlib,html,json,math,os,re,shutil,subprocess,sys
from pathlib import Path

IDS=['01-method-interface','02-baseline-difference','03-reference-failure','04-sensitivity-decision','05-uncertainty-semantics','06-cost-effect']

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
def ref(root,path,version=1):
    path=Path(path);return {'path':path.relative_to(root).as_posix(),'version':version,'sha256':digest(path)}
def rows_csv(path,rows):
    with Path(path).open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

def synthetic_data():
    import numpy as np
    loads=np.linspace(60,100,9)
    comparison=[{'load_per_hour':float(x),'baseline_delay_min':float(.08*x+3),'improved_delay_min':float(.05*x+2),'delay_saved_min':float(.03*x+1)} for x in loads]
    time=np.arange(24,dtype=float);pred=50+.3*time+6*np.sin(np.pi*time/12);truth=pred+12*(time>=18)
    forecast=[{'time_h':float(t),'reference_units':float(y),'prediction_units':float(z),'signed_error_units':float(z-y),'shift_window':bool(t>=18)} for t,y,z in zip(time,truth,pred)]
    p=np.linspace(.5,2.5,81)
    sensitivity=[{'parameter':float(x),'cost_A':float(20+12*x),'cost_B':float(34+3*x),'chosen_policy':'A' if 20+12*x<=34+3*x else 'B'} for x in p]
    times=np.linspace(0,10,101)
    envelope=[{'time_h':float(t),'lower_units':float(100*np.exp(-.25*t)),'center_units':float(100*np.exp(-.20*t)),'upper_units':float(100*np.exp(-.15*t))} for t in times]
    mu,sigma,z=6.,1.2,1.6448536269514722
    ys=np.linspace(mu-4*sigma,mu+4*sigma,321)
    density=[{'response_units':float(y),'density_per_unit':float(math.exp(-.5*((y-mu)/sigma)**2)/(sigma*math.sqrt(2*math.pi))),'inside_model_90pct_PI':bool(mu-z*sigma<=y<=mu+z*sigma)} for y in ys]
    costs=[10,14,18,23,30,40,28];effects=[52,61,67,70,76,78,65]
    decisions=[{'policy':chr(65+i),'cost_units':cost,'effect_units':effect,'frontier':i<6,'budget_feasible':cost<=25,'selected':i==3} for i,(cost,effect) in enumerate(zip(costs,effects))]
    return {'comparison':comparison,'forecast':forecast,'sensitivity':sensitivity,'envelope':envelope,'density':density,'decisions':decisions}

def family_specs():
    return [
      {'id':IDS[0],'kind':'schematic','question':'What crosses each modeling interface?',
       'claim':'Each downstream model consumes an explicit state, time grid, units and parameter range.',
       'caption':'Original synthetic workflow. The mechanism supplies stock on the same hourly grid used by the policy model. The interface carries units and a parameter range; comparison precedes the budget-constrained action. Arrows represent data dependencies, not a claim of numerical validation.',
       'data':['interfaces.json'],'columns':[],'uncertainty':'Parameter range is an interface input; no probability is assigned.',
       'panels':[('a','How are subproblems connected?','state-and-unit interface',[],'The same state definition reaches the decision model.')]},
      {'id':IDS[1],'kind':'comparison','question':'How much delay is saved relative to the baseline?',
       'claim':'The synthetic improved policy reduces delay at every shared load, with gains increasing with load.',
       'caption':'Synthetic paired comparison at nine identical hourly loads. Panel a shows delay for both policies; panel b shows baseline minus improved delay at each load. Every generated scenario is retained. The curves are deterministic illustrative formulas, not estimates from observed service data.',
       'data':['comparison.csv'],'columns':['load_per_hour','baseline_delay_min','improved_delay_min','delay_saved_min'],'uncertainty':'None: deterministic scenario comparison.',
       'panels':[('a','Do both policies use the same loads?','paired baseline comparison',['load_per_hour','baseline_delay_min','improved_delay_min'],'The improved curve has lower delay.'),('b','How large is the paired gain?','absolute difference',['load_per_hour','delay_saved_min'],'The delay gain grows with load.')]},
      {'id':IDS[2],'kind':'validation','question':'Where does the fixed synthetic model fail?',
       'claim':'A known regime shift causes a persistent twelve-unit error that the aggregate trajectory alone can obscure.',
       'caption':'Synthetic reference and fixed prediction over 24 hours. A twelve-unit shift is deliberately introduced at hour 18. Panel a shows trajectories; panel b shows prediction minus reference, with a five-unit tolerance. The shaded interval is a known failure scenario, not a fitted confidence interval or evidence of real-world generalization.',
       'data':['forecast.csv'],'columns':['time_h','reference_units','prediction_units','signed_error_units','shift_window'],'uncertainty':'The shading marks a deterministic regime-shift scenario; it is not an uncertainty band.',
       'panels':[('a','Does the prediction follow the reference?','reference comparison',['time_h','reference_units','prediction_units','shift_window'],'The fixed prediction misses the late shift.'),('b','Does the miss exceed the stated tolerance?','signed-error failure window',['time_h','signed_error_units','shift_window'],'The twelve-unit error exceeds the five-unit tolerance.')]},
      {'id':IDS[3],'kind':'sensitivity','question':'Does a parameter change alter the recommended action?',
       'claim':'The lower-cost action switches from A to B at parameter 14/9.',
       'caption':'Synthetic cost sensitivity for two policies across 81 parameter values. Panel a shows both cost functions; panel b maps each value to its lower-cost policy. The analytical crossing is 14/9. The example distinguishes a smooth numerical response from a discrete change in the recommended action.',
       'data':['sensitivity.csv'],'columns':['parameter','cost_A','cost_B','chosen_policy'],'uncertainty':'Specified deterministic parameter sweep, not a sampling distribution.',
       'panels':[('a','How do policy costs respond?','parameter response',['parameter','cost_A','cost_B'],'The cost curves cross once.'),('b','What changes for the decision maker?','decision boundary',['parameter','chosen_policy'],'The preferred action changes at the crossing.')]},
      {'id':IDS[4],'kind':'uncertainty','question':'Which uncertainty statements are justified by each construction?',
       'claim':'A deterministic parameter envelope and a model-defined predictive interval describe different uncertainty objects.',
       'caption':'Two synthetic uncertainty constructions. Panel a spans decay rates from 0.15 to 0.25 per hour, without a probability interpretation. Panel b shades the central 90% interval of an assumed Normal response with mean 6 and standard deviation 1.2. This model-defined interval is not empirical coverage validation or a confidence interval for the mean.',
       'data':['envelope.csv','density.csv'],'columns':['time_h','lower_units','center_units','upper_units','response_units','density_per_unit','inside_model_90pct_PI'],'uncertainty':'Panel a: deterministic parameter envelope. Panel b: known-parameter Normal central predictive interval mu +/- 1.6448536269514722 sigma; its 90% probability is conditional on that assumed distribution.',
       'panels':[('a','What range follows from bounded parameters?','deterministic parameter envelope',['time_h','lower_units','center_units','upper_units'],'The envelope has no assigned coverage probability.'),('b','What does a model-defined 90% interval mean?','distribution-defined predictive interval',['response_units','density_per_unit','inside_model_90pct_PI'],'The probability statement depends on the assumed Normal response.')]},
      {'id':IDS[5],'kind':'decision','question':'Which discrete feasible policy maximizes effect under the stated budget?',
       'claim':'Policy D maximizes synthetic effect under budget 25; higher-effect policies exceed that budget.',
       'caption':'Seven synthetic discrete policies. Panel a shows cost and effect: circles are frontier policies, the cross is dominated G, and the orange star is D. No interpolated actions are implied. Panel b shows costs against budget 25. D is preferred only for this budget and objective.',
       'data':['decisions.csv'],'columns':['policy','cost_units','effect_units','frontier','budget_feasible','selected'],'uncertainty':'No sampling uncertainty. Recommendation is conditional on this finite candidate set, budget and maximize-effect rule.',
       'panels':[('a','Which trade-offs are available?','discrete cost-effect frontier',['policy','cost_units','effect_units','frontier','selected'],'D is a feasible frontier action, while G is dominated.'),('b','Why are higher effects not selected?','budget feasibility',['policy','cost_units','budget_feasible','selected'],'Policies E and F exceed the specified budget.')]}]

def method_svg(style):
    c=style['palette'];font=html.escape(style['font_family']);w,h=624,360
    nodes=[('n1',16,25,'1  Inputs',['stock (units)','hourly grid']),('n2',232,25,'2  Dynamics',['rate k (1/h)','step dt (h)']),('n3',448,25,'3  Interface',['stock at time t','k in [0.15, 0.25]']),('n4',448,205,'4  Policy',['cost and effect','same hourly grid']),('n5',232,205,'5  Compare',['baseline and gain','budget 25']),('n6',16,205,'6  Action',['discrete policy','validity conditions'])]
    s=[f'<svg xmlns="http://www.w3.org/2000/svg" width="165.1mm" height="95.25mm" viewBox="0 0 {w} {h}" data-generator="mcm-gallery-original-python" data-style-id="1" data-quality-profile="standard">',f'<style>text{{font-family:{font};fill:{c["neutral"]}}}</style>','<rect width="624" height="360" fill="white" data-graph-role="decoration"/>']
    for identifier,x,y,title,body in nodes:
        s.append(f'<rect id="{identifier}" data-node-id="{identifier}" data-graph-role="node" x="{x}" y="{y}" width="160" height="78" rx="7" fill="white" stroke="{c["blue"]}" stroke-width="1.5"/>')
        s.append(f'<text x="{x+12}" y="{y+24}" font-size="18" font-weight="bold">{html.escape(title)}</text>')
        for i,line in enumerate(body):s.append(f'<text x="{x+12}" y="{y+46+i*20}" font-size="16">{html.escape(line)}</text>')
    for identifier,source,target,d,tip in [('e1','n1','n2','M176 64 H224','224,64 215,59 215,69'),('e2','n2','n3','M392 64 H440','440,64 431,59 431,69'),('e3','n3','n4','M528 103 V197','528,197 523,188 533,188'),('e4','n4','n5','M448 244 H400','400,244 409,239 409,249'),('e5','n5','n6','M232 244 H184','184,244 193,239 193,249')]:
        s.append(f'<path id="{identifier}" data-graph-role="edge" data-source="{source}" data-target="{target}" d="{d}" fill="none" stroke="{c["blue"]}" stroke-width="2"/>')
        # Explicit geometry survives both the SVG raster and PDF rendering paths.
        s.append(f'<polygon id="{identifier}-head" data-graph-role="decoration" data-owner="{identifier}" points="{tip}" fill="{c["blue"]}"/>')
    s.extend(['<text x="16" y="324" font-size="16">Interfaces retain the same time grid.</text>','<text x="16" y="346" font-size="16">States, units and parameter ranges remain explicit.</text>','</svg>'])
    return '\n'.join(s)+'\n'

def canvas(style):
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(style['final_width_mm']/25.4,6.5))
    fig.subplots_adjust(left=.18,right=.97,bottom=.12,top=.92,hspace=.76)
    for ax in axes:
        ax.spines[['top','right']].set_visible(False);ax.grid(False)
    return fig,axes

def draw_quantitative(identifier,rows,style):
    import numpy as np
    fig,ax=canvas(style);c=style['palette']
    if identifier==IDS[1]:
        d=rows['comparison'];x=[r['load_per_hour'] for r in d]
        ax[0].plot(x,[r['baseline_delay_min'] for r in d],label='Baseline',color=c['neutral'],ls='--',marker='o',ms=4)
        ax[0].plot(x,[r['improved_delay_min'] for r in d],label='Improved',color=c['blue'],marker='s',ms=4)
        ax[0].set(ylabel='Delay (min)',ylim=(4,12));ax[0].legend(loc='upper left',frameon=False)
        ax[1].plot(x,[r['delay_saved_min'] for r in d],color=c['teal'],marker='D',ms=4)
        ax[1].set(ylabel='Delay saved (min)',ylim=(0,4.6))
        for a in ax:a.set(xlabel='Load (arrivals/h)',xlim=(58,102))
        titles=['(a) Shared-load comparison','(b) Paired gain over baseline']
    elif identifier==IDS[2]:
        d=rows['forecast'];x=[r['time_h'] for r in d]
        ax[0].plot(x,[r['reference_units'] for r in d],label='Reference',color=c['neutral'],ls='--')
        ax[0].plot(x,[r['prediction_units'] for r in d],label='Fixed prediction',color=c['blue'])
        ax[0].set(ylabel='Response (units)',ylim=(40,85));ax[0].legend(loc='upper left',frameon=False)
        ax[1].plot(x,[r['signed_error_units'] for r in d],color=c['blue'],marker='o',ms=3)
        ax[1].axhline(-5,color=c['orange'],ls='--',label='Tolerance: +/-5')
        ax[1].axhline(5,color=c['orange'],ls='--');ax[1].set(ylabel='Signed error (units)',ylim=(-16,9));ax[1].legend(loc='lower left',frameon=False)
        for a in ax:a.axvspan(18,23,color=c['orange'],alpha=.12);a.set(xlabel='Time (h)',xlim=(0,23),xticks=[0,6,12,18,23])
        titles=['(a) Reference and fixed model','(b) Failure interval after hour 18']
    elif identifier==IDS[3]:
        d=rows['sensitivity'];x=[r['parameter'] for r in d]
        ax[0].plot(x,[r['cost_A'] for r in d],label='Policy A',color=c['blue'])
        ax[0].plot(x,[r['cost_B'] for r in d],label='Policy B',color=c['orange'],ls='--')
        ax[0].set(ylabel='Cost (units)',ylim=(20,56));ax[0].legend(loc='upper left',frameon=False)
        ax[1].step(x,[0 if r['chosen_policy']=='A' else 1 for r in d],where='post',color=c['teal'],lw=2)
        ax[1].set(ylabel='Lower-cost policy',yticks=[0,1],yticklabels=['A','B'],ylim=(-.35,1.35))
        for a in ax:a.axvline(14/9,color=c['neutral'],ls=':',lw=1.5);a.set(xlabel='Parameter p (dimensionless)',xlim=(.5,2.5))
        titles=['(a) Parameter response','(b) Action changes near p = 1.556']
    elif identifier==IDS[4]:
        d=rows['envelope'];x=[r['time_h'] for r in d]
        ax[0].fill_between(x,[r['lower_units'] for r in d],[r['upper_units'] for r in d],color=c['blue'],alpha=.16,label='Parameter envelope')
        ax[0].plot(x,[r['center_units'] for r in d],color=c['blue'],label='Rate k = 0.20')
        ax[0].set(xlabel='Time (h)',ylabel='Stock (units)',xlim=(0,10),ylim=(0,120));ax[0].legend(loc='upper right',frameon=False)
        d=rows['density'];x=np.array([r['response_units'] for r in d]);y=np.array([r['density_per_unit'] for r in d]);mask=np.array([r['inside_model_90pct_PI'] for r in d])
        ax[1].plot(x,y,color=c['neutral'],label='Assumed Normal law')
        ax[1].fill_between(x,0,y,where=mask,color=c['teal'],alpha=.3,label='Central 90% model PI')
        ax[1].set(xlabel='Response (units)',ylabel='Density (1/unit)',xlim=(1.2,10.8),ylim=(0,.58));ax[1].legend(loc='upper left',frameon=False)
        titles=['(a) Bounded rates; no probability','(b) Distribution-defined uncertainty']
    else:
        d=rows['decisions']
        for r in d:
            color=c['orange'] if r['selected'] else c['blue'] if r['frontier'] else c['neutral'];marker='*' if r['selected'] else 'o' if r['frontier'] else 'x'
            ax[0].scatter(r['cost_units'],r['effect_units'],color=color,marker=marker,s=135 if r['selected'] else 40,zorder=3)
            ax[0].annotate(r['policy'],(r['cost_units'],r['effect_units']),xytext=(4,6),textcoords='offset points',fontsize=12)
        ax[0].set(xlabel='Cost (units)',ylabel='Effect (units)',xlim=(7,44),ylim=(47,85))
        ax[1].barh([r['policy'] for r in d],[r['cost_units'] for r in d],color=[c['orange'] if r['selected'] else c['blue'] if r['budget_feasible'] else c['neutral'] for r in d],height=.58)
        ax[1].axvline(25,color=c['neutral'],ls='--',lw=1.5);ax[1].set(xlabel='Cost (units)',ylabel='Policy',xlim=(0,44));ax[1].invert_yaxis();ax[1].grid(False)
        titles=['(a) Discrete cost-effect choices','(b) Feasibility under budget 25']
    for a,title in zip(ax,titles):a.set_title(title,loc='left',pad=10)
    fig.canvas.draw();return fig

def command_record(tool,arguments,output,timeout=60):
    run=subprocess.run([sys.executable,str(tool),*map(str,arguments)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
    # Only portable structured tool output is kept; no raw local command paths.
    try:result=json.loads(run.stdout)
    except json.JSONDecodeError:result={'exit_code':run.returncode,'diagnostic':re.sub(r'[A-Za-z]:[\\/][^\n\r]+','<LOCAL_PATH>',(run.stdout+run.stderr)[-3000:])}
    def portable(value):
        if isinstance(value,dict):return {key:portable(item) for key,item in value.items()}
        if isinstance(value,list):return [portable(item) for item in value]
        if isinstance(value,str):
            for original,alias in [(str(Path(__file__).resolve().parents[1]),'<CANDIDATE>'),(str(Path.home()),'<USER_HOME>')]:
                value=value.replace(original,alias).replace(original.replace('\\','/'),alias)
        return value
    save(output,portable(result));return {'tool':Path(tool).name,'status':'passed' if run.returncode==0 else 'failed','exit_code':run.returncode}

def build_pages(out,summary):
    latex=out/'latex';build=out/'pages';latex.mkdir(exist_ok=True);build.mkdir(exist_ok=True)
    macros='\n'.join([r'\newcommand{\SwitchValue}{'+f'{14/9:.3f}'+r'}',r'\newcommand{\SelectedCost}{23}',r'\newcommand{\SelectedEffect}{70}',r'\newcommand{\MeanDelaySaved}{'+f'{summary["mean_delay_saved_min"]:.2f}'+r'}'])+'\n'
    (latex/'numbers.tex').write_text(macros,encoding='utf-8',newline='\n')
    header=r'''% Original synthetic teaching pages; not a competition submission.
\documentclass[12pt]{article}
\usepackage[a4paper,textwidth=165.1mm,top=18mm,bottom=18mm,centering]{geometry}
\usepackage{newtxtext}
\usepackage{amsmath,amssymb}
\usepackage{newtxmath}
\usepackage{graphicx,booktabs,fancyhdr}
\usepackage[hidelinks]{hyperref}
\pagestyle{fancy}\fancyhf{}\fancyhead[L]{Synthetic page examples}\fancyhead[R]{\thepage}\setlength{\headheight}{15pt}
\setlength{\parindent}{0pt}\setlength{\parskip}{5pt}
\input{numbers.tex}
\newcommand{\GalleryFigure}[3]{\begin{figure}[!ht]\centering\includegraphics[width=165.1mm]{../figures/#1.pdf}\caption{#2}\label{#3}\end{figure}}
\begin{document}
\section*{Model page: explicit interfaces}
This synthetic page explains what is passed between questions before presenting an algorithm. Figure~\ref{fig:method} distinguishes a physical state from a policy decision; the hourly grid and units remain unchanged at the interface.
\begin{equation}\label{eq:decay}
\operatorname{stock}(t)=100\exp(-kt),\qquad 0.15\leq k\leq0.25.
\end{equation}
The rate has units of inverse hours. The parameter range expresses a scenario assumption, without assigning probabilities. Equation~\eqref{eq:decay} supplies the state, not the optimization objective.
'''
    specs=family_specs();parts=[header]
    def figure(i,label):
        caption=specs[i]['caption'].replace('%',r'\%').replace('_',r'\_')
        return r'\GalleryFigure{'+specs[i]['id']+'}{'+caption+'}{'+label+'}\n'
    parts.append(figure(0,'fig:method'))
    parts.append(r'''\begin{center}\begin{tabular}{lll}\toprule
Quantity & Unit & Interface meaning\\\midrule
Stock & units & State at the shared hour\\
Rate & inverse hours & Bounded model parameter\\
Cost & cost units & Policy objective\\\bottomrule
\end{tabular}\end{center}
\clearpage
\section*{Result page: comparison and magnitude}
Both policies use the same nine loads. The mean delay saved is \MeanDelaySaved\ minutes across these deterministic scenarios. Figure~\ref{fig:comparison} separates the performance comparison from the magnitude of the paired gain; it does not establish performance on an external population.
''')
    parts.append(figure(1,'fig:comparison'))
    parts.append(r'''\clearpage
\section*{Result page: show the failure window}
A fixed synthetic prediction follows the reference until an imposed shift at hour 18. Figure~\ref{fig:failure} makes the missed regime visible in both the trajectories and signed error. The failure exceeds the stated five-unit tolerance, so an unconditional reliability claim would be unsupported.
''')
    parts.append(figure(2,'fig:failure'))
    parts.append(r'''\clearpage
\section*{Sensitivity page: numerical and action changes}
Two cost functions cross at \(p=14/9\), approximately \SwitchValue. Figure~\ref{fig:sensitivity} connects the continuous responses to a discrete action change. A small cost variation near the crossing can change the recommendation even when both response curves remain smooth.
''')
    parts.append(figure(3,'fig:sensitivity'))
    parts.append(r'''\clearpage
\section*{Sensitivity page: identify the uncertainty object}
Figure~\ref{fig:uncertainty} gives two deliberately different constructions. A range over assumed rates is not a confidence interval. The central predictive interval has a probability interpretation only conditional on the stated Normal response model; no empirical coverage claim is made.
''')
    parts.append(figure(4,'fig:uncertainty'))
    parts.append(r'''\clearpage
\section*{Decision page: a conditional recommendation}
Among the seven discrete policies, D maximizes effect subject to budget 25. Its cost is \SelectedCost\ and effect is \SelectedEffect. Figure~\ref{fig:decision} displays both the trade-off and the feasibility reason. The choice is conditional on this candidate set, objective and budget.
''')
    parts.append(figure(5,'fig:decision'));parts.append('\n\\end{document}\n')
    (latex/'page-examples.tex').write_text(''.join(parts),encoding='utf-8',newline='\n')
    commands=[]
    for iteration in range(2):
        run=subprocess.run(['xelatex','-no-shell-escape','-interaction=nonstopmode','-halt-on-error','-output-directory',str(build),'page-examples.tex'],cwd=latex,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
        commands.append({'engine':'xelatex','iteration':iteration+1,'exit_code':run.returncode})
        if run.returncode:raise RuntimeError('XeLaTeX failed; inspect the local build log.')
    import fitz
    pdf=build/'page-examples.pdf';doc=fitz.open(pdf);text='\n'.join(p.get_text() for p in doc)
    log=(build/'page-examples.log').read_text(encoding='utf-8',errors='replace')
    warnings=[line for line in log.splitlines() if re.search(r'Overfull|Underfull|undefined|Missing character|LaTeX Warning|Font Warning',line)]
    page_info=[]
    for i,page in enumerate(doc,1):
        pix=page.get_pixmap(matrix=fitz.Matrix(1.4,1.4),alpha=False);pix.save(build/f'page-{i:02d}.png')
        spans=[span for block in page.get_text('dict')['blocks'] if 'lines'in block for line in block['lines'] for span in line['spans'] if span['text'].strip()]
        outside=[s['text'] for s in spans if s['bbox'][0]<0 or s['bbox'][1]<0 or s['bbox'][2]>page.rect.width+.5 or s['bbox'][3]>page.rect.height+.5]
        page_info.append({'page':i,'text_spans':len(spans),'minimum_text_span_pt':min(s['size'] for s in spans),'text_outside_page':outside,'render':f'pages/page-{i:02d}.png'})
    result={'status':'compiled_visual_pending' if not warnings and len(doc)==6 and all(not p['text_outside_page'] for p in page_info) else 'needs_repair','page_count':len(doc),'commands':commands,'warnings':warnings,'pages':page_info,'pdf_sha256':digest(pdf),'source_sha256':digest(latex/'page-examples.tex'),'formula_policy':'Native LaTeX equations at 12 TeX pt, no resizebox/scalebox; 12 TeX pt is approximately 11.955 PDF pt. Figures are inserted at their authored 165.1 mm width.','visual_status':'pending','human_approval':False,'latexmk_status':'Not used: the installed wrapper cannot find its Perl engine. No external bibliography is needed; XeLaTeX was run twice.','full_competition_paper':False}
    save(build/'build-report.json',result)
    # Raw TeX logs contain machine paths; the portable report retains only warnings and hashes.
    for suffix in ['.aux','.out','.log']:
        local=build/('page-examples'+suffix)
        if local.is_file():local.unlink()
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--skill-root',type=Path,required=True);p.add_argument('--diagram-skill-root',type=Path,required=True);p.add_argument('--compile-pages',action='store_true');p.add_argument('--force',action='store_true');a=p.parse_args()
    repo=Path(__file__).resolve().parents[1];out=(a.output or repo/'gallery').resolve()
    if (out/'manifest.json').exists() and not a.force:raise ValueError('Existing fixed gallery; use --force only for an explicitly authorized regeneration.')
    for name in ['config','source','data','figures','contracts','checks']: (out/name).mkdir(parents=True,exist_ok=True)
    style_source=repo/'bundle/src/figure-style.json';style=json.loads(style_source.read_text(encoding='utf-8-sig'));shutil.copyfile(style_source,out/'config/figure-style.json');shutil.copyfile(Path(__file__).resolve(),out/'source/figure-gallery.py')
    documents=['SKILL.md','manifest.yaml','references/mcm-adaptation.md','static/core/contract.md','static/core/stance.md','static/fragments/backend/python.md','references/multipanel-evidence-architecture.md','references/qa-contract.md']
    guidance=[]
    for name in documents:
        path=a.skill_root/name;assert path.read_text(encoding='utf-8-sig').strip();guidance.append({'skill':'nature-figure','document':name,'sha256':digest(path)})
    diagram_read=[]
    for name in ['SKILL.md','references/style-1-flat-icon.md','references/composition-quality-contract.md']:
        path=a.diagram_skill_root/name;assert path.read_text(encoding='utf-8-sig').strip();diagram_read.append({'skill':'fireworks-tech-graph','document':name,'sha256':digest(path)})
    sys.path.insert(0,str(a.skill_root/'scripts'));sys.path.insert(0,str(repo/'project-template/scripts'))
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from audit_panel_alignment import require_matplotlib_panel_alignment
    from figure_check import audit_pdf,check_contract
    matplotlib.rcParams.update({'font.family':'sans-serif','font.sans-serif':[style['font_family']],'font.size':style['tick_font_pt'],'axes.labelsize':style['axis_font_pt'],'axes.titlesize':style['title_font_pt'],'legend.fontsize':style['tick_font_pt'],'xtick.labelsize':style['tick_font_pt'],'ytick.labelsize':style['tick_font_pt'],'svg.fonttype':'none','svg.hashsalt':'mcm-v022-gallery','pdf.fonttype':42,'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.8,'lines.linewidth':2,'savefig.facecolor':'white'})
    data=synthetic_data()
    for name,rows in data.items():rows_csv(out/'data'/f'{name}.csv',rows)
    save(out/'data/interfaces.json',{'synthetic':True,'clock':'hourly','state':{'name':'stock','unit':'units'},'rate':{'unit':'1/h','range':[.15,.25]},'objective':'maximize effect among discrete feasible policies','budget':25,'interfaces':[{'from':'dynamics','to':'policy','values':['stock','time_h','rate_range']}]})
    manifest={'version':'0.2.2','synthetic':True,'status':'generating','style_source':{'path':'bundle/src/figure-style.json','sha256':digest(style_source)},'style_snapshot':ref(out,out/'config/figure-style.json'),'source_script':ref(out,out/'source/figure-gallery.py'),'figures':[],'visual_status':'pending','human_approval':False,'uses_heldout_answers':False}
    save(out/'manifest.json',manifest)
    source_preflight=command_record(a.skill_root/'scripts/validate_figure.py',[Path(__file__).resolve(),'--json'],out/'checks/source-preflight.json')
    for spec in family_specs():
        identifier=spec['id'];base=out/'figures'/identifier;checks=out/'checks'/identifier;checks.mkdir(exist_ok=True)
        height=95.25 if spec['kind']=='schematic' else 165.1
        contract={'format_version':2,'_template_only':False,'figure_id':identifier,'version':1,'owner_role':'mcm-figure','claim_id':'SYNTHETIC-'+identifier,'argument_sentence':spec['claim'],'figure_type':'schematic' if spec['kind']=='schematic' else 'quantitative','figure_level_question':spec['question'],'data_inputs':[ref(out,out/'data'/name) for name in spec['data']]+[ref(out,out/'config/figure-style.json')],'columns_and_units':spec['columns'],'comparison_groups':[],'transformation':'All generated rows retained; the paired gain is baseline minus improved; other constructions are explicitly defined in source.','uncertainty_definition':spec['uncertainty'],'sample_or_scenario_count':{name:len(data[name.removesuffix('.csv')]) for name in spec['data'] if name.endswith('.csv')},'size_mm':{'width':style['final_width_mm'],'height':height},'style_profile':style['profile'],'style_config_ref':ref(out,out/'config/figure-style.json'),'script_path':'source/figure-gallery.py','script_sha256':digest(out/'source/figure-gallery.py'),'generation_command':'python tools/figure-gallery.py --output gallery --skill-root <nature-figure> --diagram-skill-root <fireworks-tech-graph> --compile-pages','caption_english':spec['caption'],'synthetic':True,'backend':'python','minimum_final_glyph_pt':style['minimum_final_glyph_pt'],'panel_plan':[{'panel':x[0],'question':x[1],'evidence_role':x[2],'input_fields':x[3],'main_takeaway':x[4]} for x in spec['panels']],'skill_read':guidance+(diagram_read if spec['kind']=='schematic' else []),'skill_executed':[],'outputs':[],'status':'draft','approval_state':'draft','qa_readback':{'visual_reviewed':False}}
        save(out/'contracts'/f'{identifier}.json',contract)
        executions=[]
        if spec['kind']=='schematic':
            import cairosvg
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.graphics import renderPDF
            from reportlab import rl_config
            from svglib.svglib import svg2rlg
            from matplotlib.font_manager import findfont
            from PIL import Image
            base.with_suffix('.svg').write_text(method_svg(style),encoding='utf-8',newline='\n')
            executions.append(command_record(a.diagram_skill_root/'scripts/fireworks.py',['check',base.with_suffix('.svg')],checks/'diagram-check.json'))
            pdfmetrics.registerFont(TTFont(style['font_family'],findfont(style['font_family'])))
            pdfmetrics.registerFont(TTFont(style['font_family']+'-Bold',findfont(matplotlib.font_manager.FontProperties(family=style['font_family'],weight='bold'))))
            pdfmetrics.registerFontFamily(style['font_family'],normal=style['font_family'],bold=style['font_family']+'-Bold')
            # Use ordinary Flate streams so the independent text audit can inspect the PDF.
            rl_config.useA85=0
            renderPDF.STATE_DEFAULTS['fontSize']=style['minimum_final_glyph_pt']
            drawing=svg2rlg(str(base.with_suffix('.svg')))
            drawing.initialFontSize=style['minimum_final_glyph_pt']
            renderPDF.drawToFile(drawing,str(base.with_suffix('.pdf')))
            cairosvg.svg2png(url=str(base.with_suffix('.svg')),write_to=str(base.with_suffix('.png')),dpi=300)
            with Image.open(base.with_suffix('.png')) as im:im.save(base.with_suffix('.png'),dpi=(300,300))
            save(checks/'alignment.json',{'status':'not_applicable','reason':'One original method panel; internal semantic diagram geometry audited by Fireworks.'})
        else:
            fig=draw_quantitative(identifier,data,style)
            alignment=require_matplotlib_panel_alignment(fig,json_out=checks/'alignment.json',strict=True)
            for ext in ['pdf','svg','png']:fig.savefig(base.with_suffix('.'+ext),dpi=300,metadata={'Creator':'MCM synthetic gallery'} if ext=='pdf' else None)
            plt.close(fig)
        font=audit_pdf(base.with_suffix('.pdf'),contract['size_mm'],12);save(checks/'font-audit.json',font)
        executions.extend([command_record(a.skill_root/'scripts/audit_pdf_text.py',[base.with_suffix('.pdf'),'--min-pt','12','--json'],checks/'pdf-text.json'),command_record(a.skill_root/'scripts/audit_figure_collisions.py',[base.with_suffix('.pdf'),'--json'],checks/'collisions.json')])
        for execution in executions:
            lookup={'fireworks.py':'diagram-check.json','audit_pdf_text.py':'pdf-text.json','audit_figure_collisions.py':'collisions.json'}
            execution['output_refs']=[ref(out,checks/lookup[execution['tool']])]
        contract['skill_executed']=executions;contract['outputs']=[ref(out,base.with_suffix('.'+ext)) for ext in ['pdf','svg','png']]
        contract['status']='mechanical_passed_visual_pending' if font['ok'] and all(x['status']=='passed' for x in executions) else 'mechanical_failed'
        contract['qa_readback']['mechanical_report_sha256']=digest(checks/'font-audit.json')
        save(out/'contracts'/f'{identifier}.json',contract)
        own_check=check_contract(out,contract);save(checks/'contract-check.json',own_check)
        manifest['figures'].append({'id':identifier,'contract':ref(out,out/'contracts'/f'{identifier}.json'),'passed_mechanical':contract['status']=='mechanical_passed_visual_pending' and own_check['ok'],'visual_status':'pending'})
        save(out/'manifest.json',manifest)
    summary={'mean_delay_saved_min':sum(r['delay_saved_min'] for r in data['comparison'])/len(data['comparison']),'switch_parameter':14/9,'selected_policy':'D','selected_cost':23,'selected_effect':70,'parameter_envelope_has_probability':False,'model_PI_assumptions':{'distribution':'Normal','mu':6.,'sigma':1.2,'central_probability':.9}}
    save(out/'data/summary.json',summary)
    if a.compile_pages:
        pages=build_pages(out,summary);manifest['pages']={'pdf':ref(out,out/'pages/page-examples.pdf'),'build_report':ref(out,out/'pages/build-report.json'),'page_count':pages['page_count'],'status':pages['status'],'visual_status':'pending'}
    manifest['source_preflight']=source_preflight
    manifest['status']='mechanical_passed_visual_pending' if source_preflight['status']=='passed' and all(f['passed_mechanical'] for f in manifest['figures']) and (not a.compile_pages or pages['status']=='compiled_visual_pending') else 'needs_repair'
    save(out/'manifest.json',manifest)
    print(json.dumps({'status':manifest['status'],'figures':len(manifest['figures']),'pages':manifest.get('pages',{}).get('page_count'),'visual_status':'pending'}))
    return 0 if manifest['status']=='mechanical_passed_visual_pending' else 1

if __name__=='__main__':raise SystemExit(main())
