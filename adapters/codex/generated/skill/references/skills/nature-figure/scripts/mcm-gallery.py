#!/usr/bin/env python3
"""Original, synthetic MCM layout recipes. Never a production results loader.

Requires existing numpy/matplotlib. Optional QA uses the installed nature-figure
helpers. Outputs are new-directory only; no network, model call or installation.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize

RECIPES = ('prediction', 'sensitivity', 'pareto', 'paired', 'strategies', 'spatial')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def as_json(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def nondominated(cost, benefit):
    """Finite tested set, cost minimized and benefit maximized; duplicates retained."""
    cost, benefit = np.asarray(cost), np.asarray(benefit)
    if cost.ndim != 1 or cost.shape != benefit.shape or not len(cost):
        raise ValueError('Expected nonempty paired cost/benefit vectors')
    if not np.isfinite(cost).all() or not np.isfinite(benefit).all():
        raise ValueError('Nonfinite objective')
    return np.array([not np.any((cost <= c) & (benefit >= b) & ((cost < c) | (benefit > b)))
                     for c, b in zip(cost, benefit)])


def visible(values, bounds):
    v = np.asarray(values)
    if not v.size or not np.isfinite(v).all():
        raise ValueError('Missing/nonfinite demonstration data')
    lo, hi = sorted(bounds)
    if np.min(v) < lo - 1e-10 or np.max(v) > hi + 1e-10:
        raise ValueError('Final axis hides a plotted point or interval endpoint')


def apply_style(style):
    floor = max(12, style['minimum_final_glyph_pt'])
    plt.rcParams.update({
        'font.family': 'sans-serif', 'font.sans-serif': [style['font_family']],
        'font.size': floor, 'axes.labelsize': max(floor, style['axis_font_pt']),
        'axes.titlesize': max(floor, style['title_font_pt']),
        'xtick.labelsize': floor, 'ytick.labelsize': floor, 'legend.fontsize': floor,
        'pdf.fonttype': 42, 'svg.fonttype': 'none', 'axes.spines.top': False,
        'axes.spines.right': False, 'axes.linewidth': .7, 'legend.frameon': False,
        'figure.facecolor': 'white', 'savefig.facecolor': 'white',
    })


def canvas(style, rows=2, cols=1, height=6.5):
    fig, grid = plt.subplots(rows, cols, figsize=(style['final_width_mm']/25.4, height), squeeze=False)
    fig.subplots_adjust(left=.16, right=.94, bottom=.14, top=.91,
                        hspace=.65 if cols > 1 else .48, wspace=.42)
    axes = list(grid.flat)
    for i, ax in enumerate(axes):
        ax.annotate(chr(97+i), xy=(0, 1), xycoords='axes fraction', xytext=(0, 10),
                    textcoords='offset points', weight='bold', ha='left', va='bottom')
        ax.tick_params(length=3, color='#667085')
    fig.text(.16, .035, 'Synthetic design example — not competition results', fontsize=12, color='#667085')
    return fig, axes


def panel(ax, title, xlabel, ylabel):
    ax.set_title(title, loc='left', x=.09, pad=10)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)


def build(recipe, style):
    """Returns figure, JSON-safe evidence, caption, panel roles and raw-domain checks."""
    p = style['palette']; rng = np.random.default_rng(731)
    checks = []
    if recipe == 'prediction':
        fig, (a, b) = canvas(style)
        t = np.arange(36); mu = 12 + .3*t + 1.3*np.sin(t/4)
        observed = mu + rng.normal(0, 1.2, len(t)); lower = mu - 1.96*1.2; upper = mu + 1.96*1.2
        a.fill_between(t[24:], lower[24:], upper[24:], color=p['blue'], alpha=.14)
        a.plot(t, mu, color=p['blue'], lw=2.1, label='Specified mean')
        a.scatter(t, observed, s=20, color=p['neutral'], label='Generated samples', zorder=3)
        a.axvline(23.5, color=p['orange'], ls='--', lw=1.3)
        a.legend(loc='upper left', ncol=1); a.set_ylim(8, 29)
        panel(a, 'Reference and held-out samples', 'Time step', 'Response (units)')
        residual = observed-mu
        b.axhline(0, color=p['neutral'], lw=1)
        b.axvline(23.5, color=p['orange'], ls='--', lw=1.3)
        b.scatter(t, residual, c=[p['neutral'] if x < 24 else p['blue'] for x in t], s=23)
        b.set_ylim(-4, 4); panel(b, 'Error on the same observations', 'Time step', 'Observed − mean')
        for ax in (a, b): ax.set_xlim(-1, 36); ax.set_xticks([0, 12, 24, 35])
        checks = [(a, np.r_[observed, lower[24:], upper[24:]]), (b, residual)]
        evidence = dict(time=t, mean=mu, observed=observed, lower=lower, upper=upper, split=24,
                        test_coverage=float(np.mean((observed[24:] >= lower[24:]) & (observed[24:] <= upper[24:]))))
        caption = ('Synthetic known-mean Gaussian experiment, 36 observations. The dashed line separates '
                   '12 held-out draws. The blue band is a pointwise nominal 95% observation interval from '
                   'the specified generating SD 1.2, not an estimated fitted-model confidence band. '
                   'The lower panel retains every residual. No forecasting skill is inferred.')
        roles = ['Locate observations relative to reference and interval', 'Expose signed errors and test boundary']
    elif recipe == 'sensitivity':
        fig, (a, b) = canvas(style)
        x = np.array([.8, 1, 1.2]); first = np.array([.12, .31, .18]); second = np.array([.22, .24, .27])
        for y, label, color, marker in [(first, 'Strategy A', p['blue'], 'o'), (second, 'Strategy B', p['teal'], 's')]:
            a.plot(x, y, marker=marker, color=color, lw=1.8, label=label)
        a.axhline(.25, color=p['orange'], ls='--', lw=1.3, label='Specified target')
        a.set_ylim(.08, .46); a.set_xticks(x); a.legend(ncol=2, loc='upper left')
        panel(a, 'The middle level changes the ranking', 'Input / baseline', 'Response (units)')
        selected = np.argmax(np.vstack([first, second]), axis=0)
        for i, label in enumerate(['Strategy A', 'Strategy B']):
            b.scatter(x, np.full(3, i), s=450, marker='s', facecolors='none', edgecolors='#D0D5DD')
            mask = selected == i
            b.scatter(x[mask], np.full(mask.sum(), i), s=450, marker='s', color=p['blue'] if i == 0 else p['teal'])
        b.set_yticks([0, 1], ['A', 'B']); b.set_xticks(x); b.set_ylim(-.65, 1.65); b.set_xlim(.72, 1.28)
        panel(b, 'Best tested response at each level', 'Input / baseline', 'Selected strategy')
        checks = [(a, np.r_[first, second])]
        evidence = dict(level=x, strategy_a=first, strategy_b=second, selected=selected, assumed_target=.25)
        caption = ('Synthetic one-factor design at 0.8, 1.0 and 1.2 times baseline. Lines join the three '
                   'tested levels for reading only. The target 0.25 is an assumed rule. Filled cells '
                   'identify the larger response at each tested level; no continuous switch boundary or '
                   'global sensitivity is estimated. These are deterministic values, not confidence intervals.')
        roles = ['Show the baseline reversal missed by endpoint-only spans', 'Translate values to a discrete decision']
    elif recipe == 'pareto':
        fig, (a, b) = canvas(style)
        fig.subplots_adjust(left=.24)
        cost = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 5, 8])
        benefit = np.array([18, 33, 29, 50, 43, 64, 59, 75, 73, 81, 51, 66])
        front = nondominated(cost, benefit)
        a.scatter(cost[~front], benefit[~front], color=p['neutral'], alpha=.55, s=32, label='Dominated')
        a.scatter(cost[front], benefit[front], color=p['blue'], marker='D', s=48, label='Non-dominated')
        # No connecting line: intermediate mixtures have not been tested.
        a.set_xlim(0, 11); a.set_ylim(8, 102); a.legend(loc='upper left', ncol=1)
        panel(a, 'Tested trade-offs', 'Cost (budget units)', 'Benefit (units)')
        chosen = np.array([1, 5, 9]); names = ['Lean', 'Balanced', 'High benefit']
        for idx, name in zip(chosen, names):
            a.annotate(name, (cost[idx], benefit[idx]), xytext=(0, 10), textcoords='offset points', ha='center', fontsize=12)
        increments = np.diff(np.r_[0, benefit[chosen]])
        b.barh(np.arange(3), increments, color=[p['neutral'], p['blue'], p['teal']], height=.5)
        b.set_yticks(np.arange(3), names); b.set_xlim(0, 45); b.invert_yaxis()
        for y, val in enumerate(increments): b.text(val+1, y, f'{val:g}', va='center', fontsize=12)
        panel(b, 'Incremental benefit', 'Benefit added (units)', '')
        checks = [(a, benefit)]; evidence = dict(cost=cost, benefit=benefit, non_dominated=front,
                                                named_indices=chosen, successive_benefit=increments)
        caption = ('Twelve synthetic feasible candidates: cost is minimized and benefit maximized. '
                   'Non-dominance refers only to this tested set. Three named options illustrate preference '
                   'choices, not a unique optimum. Lower bars give successive benefit increases from zero '
                   'to Lean, Lean to Balanced and Balanced to High benefit; they are not benefit/cost ratios.')
        roles = ['Show trade-off and dominated choices', 'Compare incremental benefit of named alternatives']
    elif recipe == 'paired':
        fig, (a, b) = canvas(style)
        baseline = rng.normal(25, 8, 120); difference = rng.normal(2, .9, 120); difference[:8] -= 3
        treatment = baseline+difference
        violin = a.violinplot([difference], positions=[0], widths=.7, showextrema=False, bw_method='scott')
        for body in violin['bodies']:
            vertices = body.get_paths()[0].vertices; vertices[:, 0] = np.minimum(vertices[:, 0], 0)
            body.set_facecolor(p['blue']); body.set_edgecolor(p['blue']); body.set_alpha(.25)
        a.scatter(rng.uniform(.10, .35, 120), difference, color=p['blue'], alpha=.45, s=13)
        quantiles = np.quantile(difference, [.1, .25, .5, .75, .9])
        a.vlines(0, quantiles[0], quantiles[4], color=p['blue'], lw=1.5)
        a.vlines(0, quantiles[1], quantiles[3], color=p['blue'], lw=5)
        a.scatter([0], [quantiles[2]], facecolor='white', edgecolor=p['blue'], s=40, zorder=4)
        a.axhline(0, color=p['neutral'], ls='--', lw=1)
        a.set_xlim(-.65, .65); a.set_ylim(-2.5, 5.5); a.set_xticks([0], ['120 matched units'])
        panel(a, 'Paired gains retain the full distribution', '', 'Treatment − baseline')
        ordered = np.sort(difference); probability = np.arange(1, 121)/120
        b.step(ordered, probability, where='post', color=p['blue'], lw=2)
        b.axvline(0, color=p['neutral'], ls='--', lw=1); b.set_ylim(0, 1.03); b.set_xlim(-2.5, 5.5)
        panel(b, 'How often is the paired gain positive?', 'Treatment − baseline', 'Empirical fraction')
        checks = [(a, difference)]; visible(ordered, b.get_xlim())
        evidence = dict(id=np.arange(120), baseline=baseline, treatment=treatment, difference=difference,
                        quantiles=quantiles, ecdf_x=ordered, ecdf_probability=probability)
        caption = ('Synthetic differences on 120 matched IDs, retaining all observations. Half-violin '
                   'uses Gaussian KDE with Scott bandwidth; dot, thick line and thin line give median, '
                   'IQR and 10–90% quantiles. Jitter affects only horizontal position. The ECDF includes '
                   'all paired differences. Neither distribution display nor quantile is an effect CI.')
        roles = ['Show spread, asymmetry and negative outcomes', 'Read the fraction below any decision threshold']
    elif recipe == 'strategies':
        fig, axes = canvas(style, rows=2, cols=2, height=6.8)
        t = np.arange(13); reference = 24+1.5*t
        curves = np.array([reference+8*(1-np.exp(-t/3)), reference+4*np.sin(t/4),
                           reference+5*(1-np.exp(-t/5)), reference-4*t/12])
        for i, (ax, curve) in enumerate(zip(axes, curves)):
            ax.plot(t, reference, color=p['neutral'], ls='--', lw=1.3)
            ax.plot(t, curve, color=p['blue'], lw=2.1)
            above = curve[-1] >= reference[-1]
            ax.annotate(f'{curve[-1]:.1f}', (12, curve[-1]), xytext=(0, 7 if above else -18),
                        textcoords='offset points', ha='right', va='bottom' if above else 'top', color=p['blue'])
            ax.set_xlim(0, 13); ax.set_ylim(20, 57); ax.set_xticks([0, 6, 12])
            panel(ax, f'Strategy {i+1}', 'Time step', 'Response')
            checks.append((ax, np.r_[reference, curve]))
        evidence = dict(time=t, reference=reference, curves=curves)
        caption = ('Four deterministic synthetic strategies against the same dashed gray reference. '
                   'All panels share time and response limits. Labels give the final tested response. '
                   'No observations are omitted and no uncertainty has been estimated.')
        roles = ['Compare strategy 1 to shared baseline', 'Compare strategy 2 to shared baseline',
                 'Compare strategy 3 to shared baseline', 'Retain the losing strategy 4']
    elif recipe == 'spatial':
        fig, axes = canvas(style, rows=2, cols=2, height=6.8)
        x, y = np.meshgrid(np.arange(8), np.arange(8))
        fields = np.array([.2+.55*np.exp(-((x-(2+i))**2+(y-4)**2)/10) for i in range(4)])
        for i, (ax, field) in enumerate(zip(axes, fields)):
            im = ax.imshow(field, origin='lower', cmap='cividis', norm=Normalize(0, 1), interpolation='nearest')
            panel(ax, f'Step {i+1}', 'Grid column', 'Grid row')
            ax.set_xticks([0, 4, 7]); ax.set_yticks([0, 4, 7])
        fig.subplots_adjust(left=.13, right=.84)
        cb_ax = fig.add_axes([.89, .27, .025, .46])
        fig.colorbar(im, cax=cb_ax, ticks=[0, .5, 1])
        cb_ax.set_title('Index', fontsize=12, pad=10)
        evidence = dict(grid_values=fields, color_range=[0, 1], spatial_unit='non-geographic cell')
        caption = ('Four synthetic 8×8 non-geographic fields, with one fixed 0–1 color range. '
                   'Every cell is shown without spatial interpolation. The design illustrates movement '
                   'on a grid, not any real location, forecast, map boundary or calibrated risk.')
        roles = [f'Locate the field at step {i+1} on the same scale' for i in range(4)]
    else:
        raise ValueError('Unknown recipe')
    for ax, values in checks: visible(values, ax.get_ylim())
    fig.canvas.draw()
    return fig, evidence, caption, roles


def export(recipe, style, out, qa_scripts=None):
    fig, evidence, caption, roles = build(recipe, style)
    path = out/recipe
    data = path.with_suffix('.data.json')
    data.write_text(json.dumps({'synthetic': True, 'seed': 731, 'arrays': evidence}, default=as_json, indent=2)+'\n', encoding='utf-8')
    qa = {}
    if qa_scripts and (qa_scripts/'audit_panel_alignment.py').is_file():
        sys.path.insert(0, str(qa_scripts))
        from audit_panel_alignment import require_matplotlib_panel_alignment
        colorbars = [ax for ax in fig.axes if ax.get_subplotspec() is None]
        require_matplotlib_panel_alignment(fig, json_out=str(path)+'.alignment.json',
                                          exclude_axes=colorbars, strict=True)
        qa['alignment'] = 'passed'
    else:
        qa['alignment'] = 'not_executed_helper_unavailable'
    exports = []
    for ext in ('pdf', 'svg', 'png'):
        target = path.with_suffix('.'+ext)
        fig.savefig(target, dpi=max(300, style['raster_dpi']))
        exports.append({'path': target.name, 'sha256': digest(target)})
    width, height = fig.get_size_inches()*25.4
    plt.close(fig)
    for helper, arguments in [('audit_pdf_text.py', ['--min-pt', str(max(12, style['minimum_final_glyph_pt']))]),
                              ('audit_figure_collisions.py', [])]:
        if not qa_scripts or not (qa_scripts/helper).is_file():
            qa[helper] = 'not_executed_helper_unavailable'; continue
        result = subprocess.run([sys.executable, str(qa_scripts/helper), str(path)+'.pdf', *arguments, '--json'],
                                capture_output=True, text=True, encoding='utf-8', timeout=90)
        (out/(recipe+'.'+helper+'.json')).write_text(result.stdout, encoding='utf-8')
        qa[helper] = {'exit_code': result.returncode}
        if result.returncode:
            raise ValueError(f'{recipe}: {helper} failed; inspect recorded report')
    record = {'recipe': recipe, 'synthetic': True, 'caption_english': caption, 'panel_roles': roles,
              'size_mm': [float(width), float(height)], 'minimum_final_glyph_pt': max(12, style['minimum_final_glyph_pt']),
              'data': {'path': data.name, 'sha256': digest(data)}, 'outputs': exports, 'qa': qa,
              'visual_review': 'pending_actual_inspection', 'independent_acceptance': 'not_claimed',
              'production_use': 'Adapt one drawing function to frozen results; replace data contract and caption.'}
    path.with_suffix('.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe', choices=(*RECIPES, 'all'), default='all')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--style', type=Path)
    parser.add_argument('--qa-scripts', type=Path)
    args = parser.parse_args(); own = Path(__file__).resolve()
    style_path = args.style or own.parent.parent/'assets/mcm-figure-style.json'
    style = json.loads(style_path.read_text(encoding='utf-8')); apply_style(style)
    out = args.output.resolve()
    if out.exists(): parser.error('Use a new output directory; existing outputs are never overwritten')
    out.mkdir(parents=True)
    qa = args.qa_scripts or own.parent
    records = [export(r, style, out, qa) for r in (RECIPES if args.recipe == 'all' else [args.recipe])]
    manifest = {'synthetic': True, 'script_sha256': digest(own), 'style_sha256': digest(style_path),
                'recipes': records, 'review_status': 'not_a_visual_or_scientific_approval'}
    (out/'gallery-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'status': 'generated', 'recipes': len(records), 'synthetic': True}))


if __name__ == '__main__':
    main()
