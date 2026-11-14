#!/usr/bin/env python3
"""Symbolic scenario and exact-count panels, with explicitly synthetic defaults.

No measurement, model fitting, statistical inference or network calls are made.
Optional --data accepts the documented JSON schema without changing its bytes.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.lines import Line2D
from matplotlib.patches import Ellipse
import numpy as np

RECIPES = ('scenarios', 'counts')
DOMAINS = ('Source A', 'Source B', 'Target')
CATEGORIES = ('Category 1', 'Category 2')
PROTOCOLS = {'Source-only fitting': ('Source A', 'Source B'),
             'Target-assisted fitting': DOMAINS,
             'Held-out evaluation': ('Target',)}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def demo_data(recipe):
    if recipe == 'counts':
        return {'kind': 'count_table', 'years': [2021, 2022, 2023, 2024],
                'categories': ['Flow', 'Balance', 'Choice', 'Forecast'],
                'counts': [[2, 0, 4, None], [3, 5, 1, 2], [6, 2, 3, 1], [4, 3, 5, 2]],
                'category_partition': 'mutually_exclusive_and_exhaustive',
                'unit': 'items'}
    if recipe == 'scenarios':
        # These positions are drawing coordinates, never feature embeddings.
        points = []
        for domain_index, domain in enumerate(DOMAINS):
            for k in range(8):
                points.append({'id': domain[0] + str(domain_index) + '-' + str(k),
                               'domain': domain, 'category': CATEGORIES[k % 2],
                               'partition': ('fit' if k < 4 else 'evaluation') if domain == 'Target' else 'source',
                               'x': 2 + 3 * domain_index + [-.57, -.18, .22, .59][k % 4],
                               'y': 1.4 + (.30 if k < 4 else -.30)})
        return {'kind': 'symbolic_schematic', 'points': points,
                'position_semantics': 'layout_only_not_metric'}
    raise ValueError('Unknown recipe')


def validate_data(recipe, data):
    if recipe == 'scenarios':
        if data.get('kind') != 'symbolic_schematic' or data.get('position_semantics') != 'layout_only_not_metric':
            raise ValueError('Scenario positions must be explicitly declared symbolic, nonmetric layout')
        points = data.get('points', [])
        if not points or len(points) > 36:
            raise ValueError('This symbolic recipe needs 1-36 points; redesign rather than crowd more')
        if len({row.get('id') for row in points}) != len(points):
            raise ValueError('Symbol IDs must be unique')
        for row in points:
            if not isinstance(row.get('id'), str) or not row['id']:
                raise ValueError('Every symbol requires an explicit ID')
            if row.get('domain') not in DOMAINS or row.get('category') not in CATEGORIES:
                raise ValueError('Unknown domain or category: update schema, legend and encoding together')
            expected = ('fit', 'evaluation') if row['domain'] == 'Target' else ('source',)
            if row.get('partition') not in expected:
                raise ValueError('Explicit source/fit/evaluation partition required; held-out IDs cannot enter fitting')
            if any(isinstance(row.get(k), bool) or not isinstance(row.get(k), (int, float)) or not math.isfinite(row[k]) for k in ['x', 'y']):
                raise ValueError('Drawing coordinates must be finite numbers')
            center = 2 + 3 * DOMAINS.index(row['domain'])
            if not (abs(row['x'] - center) <= .8 and .8 <= row['y'] <= 2):
                raise ValueError('Symbol lies outside its assigned schematic group')
        if {row['domain'] for row in points} != set(DOMAINS):
            raise ValueError('All declared source/target groups must be present')
        if {row['partition'] for row in points if row['domain'] == 'Target'} != {'fit', 'evaluation'}:
            raise ValueError('Target fitting and evaluation subsets must both be explicit and nonempty')
        return
    if recipe != 'counts' or data.get('kind') != 'count_table':
        raise ValueError('Expected count_table')
    years, categories, counts = data.get('years', []), data.get('categories', []), data.get('counts', [])
    if not (2 <= len(years) <= 5 and 2 <= len(categories) <= 4):
        raise ValueError('This layout supports 2-5 years and 2-4 categories; split larger tables')
    if any(isinstance(y, bool) or not isinstance(y, int) for y in years) or years != sorted(set(years)):
        raise ValueError('Years must be unique, increasing integers')
    if len(set(categories)) != len(categories) or any(not isinstance(c, str) or not c.strip() or len(c) > 12 for c in categories):
        raise ValueError('Use unique short category labels, up to 12 characters')
    if len(counts) != len(years) or any(not isinstance(row, list) or len(row) != len(categories) for row in counts):
        raise ValueError('Every year/category cell must be explicit; null means not available')
    for row in counts:
        for value in row:
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ValueError('Counts must be nonnegative integers or explicit null; no coercion')
    if data.get('category_partition') != 'mutually_exclusive_and_exhaustive':
        raise ValueError('Composition requires declared mutually exclusive, exhaustive categories')
    if data.get('unit') != 'items':
        raise ValueError('Expected count unit items; change labels, caption and schema together')
    complete = [row for row in counts if all(v is not None for v in row)]
    if not complete or sum(sum(row) for row in complete) <= 0:
        raise ValueError('Composition needs at least one complete year with positive total')


def composition(data):
    validate_data('counts', data)
    complete = [(y, row) for y, row in zip(data['years'], data['counts']) if all(v is not None for v in row)]
    excluded = [y for y, row in zip(data['years'], data['counts']) if any(v is None for v in row)]
    totals = [sum(row[i] for _, row in complete) for i in range(len(data['categories']))]
    denominator = sum(totals)
    return {'included_years': [y for y, _ in complete], 'excluded_incomplete_years': excluded,
            'numerators': totals, 'denominator': denominator,
            'percentages': [100 * n / denominator for n in totals],
            'category_partition': data['category_partition'], 'weighting': 'pooled item counts, not mean annual percentages'}


def apply_style(style):
    floor = max(12., float(style['minimum_final_glyph_pt']))
    plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': [style['font_family']],
                         'font.size': floor, 'axes.labelsize': floor, 'axes.titlesize': floor,
                         'xtick.labelsize': floor, 'ytick.labelsize': floor, 'legend.fontsize': floor,
                         'pdf.fonttype': 42, 'svg.fonttype': 'none', 'axes.linewidth': .7,
                         'figure.facecolor': 'white', 'savefig.facecolor': 'white'})
    return floor


def build(recipe, style, data, synthetic=True):
    validate_data(recipe, data)
    floor = apply_style(style)
    width = float(style['final_width_mm']) / 25.4
    if width < 6.49:
        raise ValueError('This recipe requires at least 165mm at final size; do not shrink labels')
    palette = style['palette']; neutral = palette['neutral']
    footer = 'Synthetic demonstration' if synthetic else 'Supplied JSON; provenance not validated'
    if recipe == 'scenarios':
        fig = plt.figure(figsize=(width, 8.2))
        axes = [fig.add_axes([.08, y, .87, .19]) for y in (.72, .47, .22)]
        colors = dict(zip(DOMAINS, [palette['blue'], palette['teal'], palette['orange']]))
        markers = dict(zip(CATEGORIES, ['o', '^']))
        panels = {}
        for panel, (protocol, available), ax in zip('abc', PROTOCOLS.items(), axes):
            ax.set(xlim=(.5, 9.5), ylim=(.2, 2.5)); ax.axis('off')
            ax.set_title(panel + '  ' + protocol, loc='left', pad=4, fontweight='bold', fontsize=floor)
            for index, domain in enumerate(DOMAINS):
                ax.add_patch(Ellipse((2 + 3 * index, 1.4), 2.25, 1.6, fill=False,
                                    lw=1.1, ec=colors[domain], linestyle='-'))
                ax.text(2 + 3 * index, .37, domain, ha='center', va='center', color=colors[domain], fontsize=floor)
            shown = []
            for point in data['points']:
                if protocol == 'Source-only fitting':
                    active = point['domain'] != 'Target'
                elif protocol == 'Target-assisted fitting':
                    active = point['domain'] != 'Target' or point['partition'] == 'fit'
                else:
                    active = point['domain'] == 'Target' and point['partition'] == 'evaluation'
                ax.scatter(point['x'], point['y'], s=48, marker=markers[point['category']],
                           facecolors=colors[point['domain']] if active else 'white',
                           edgecolors=colors[point['domain']], linewidths=1.1, zorder=3)
                shown.append({'id': point['id'], 'x': point['x'], 'y': point['y'],
                              'category': point['category'], 'domain': point['domain'],
                              'partition': point['partition'],
                              'state': 'available_this_step' if active else 'held_out_this_step'})
            panels[panel] = {'protocol': protocol, 'available_domains': list(available), 'symbols': shown}
        classes = [Line2D([], [], marker=m, linestyle='none', markerfacecolor=neutral,
                          markeredgecolor=neutral, markersize=7, label=c) for c, m in markers.items()]
        fig.legend(handles=classes, loc='lower center', bbox_to_anchor=(.52, .125), ncol=2, frameon=False)
        states = [Line2D([], [], marker='o', linestyle='none', markerfacecolor=fc, markeredgecolor=neutral,
                        markersize=7, label=label) for fc, label in [(neutral, 'Available this step'), ('white', 'Held out this step')]]
        fig.legend(handles=states, loc='lower center', bbox_to_anchor=(.52, .077), ncol=2, frameon=False)
        fig.text(.08, .033, 'Symbolic layout; positions are not measured distances.', fontsize=floor, color=neutral)
        fig.text(.08, .006, footer, fontsize=floor, color=neutral)
        caption = ('Symbolic source/target protocol comparison. Shape encodes category, color and group label '
                   'encode source identity, and fill encodes availability in the named step. The same symbol IDs '
                   'and drawing coordinates are preserved across panels. In the target group, top-row symbols '
                   'form a declared fitting subset and bottom-row symbols a disjoint held-out evaluation subset; '
                   'evaluation IDs never enter either fitting panel. Panel a is the source-only alternative to b, '
                   'and c shows the held-out scoring step, '
                   'not evidence of a learned boundary, distributional distance, accuracy improvement or data access permission. '
                   'Group envelopes are visual containers with no statistical meaning.')
        record = {'panels': panels, 'encoding': {'shape': markers, 'color': colors,
                   'fill': {'filled': 'available_this_step', 'outline': 'held_out_this_step'}},
                  'geometry': {'metric': False, 'fixed_coordinates_across_panels': True,
                               'envelopes': 'Visual containers, not confidence sets or measured distributions'}}
    else:
        fig = plt.figure(figsize=(width, 7.1))
        top = fig.add_axes([.19, .57, .66, .32]); cb_ax = fig.add_axes([.89, .58, .025, .27])
        bottom = fig.add_axes([.20, .17, .57, .26]); axes = [top, bottom]
        comp = composition(data)
        finite = [v for row in data['counts'] for v in row if v is not None]
        largest = max(1, max(finite))
        cmap = LinearSegmentedColormap.from_list('count_blue', ['#F1F5FA', palette['blue']])
        norm = Normalize(vmin=0, vmax=largest, clip=False)
        cell_records = []
        for yi, (year, row) in enumerate(zip(data['years'], data['counts'])):
            for ci, value in enumerate(row):
                if value is None:
                    top.scatter(ci, yi, s=310, marker='s', facecolors='white', edgecolors=neutral, linewidths=.8)
                    top.text(ci, yi, 'NA', ha='center', va='center', fontsize=floor, color=neutral)
                elif value == 0:
                    top.scatter(ci, yi, s=310, marker='o', facecolors='white', edgecolors=palette['blue'], linewidths=1)
                    top.text(ci, yi, '0', ha='center', va='center', fontsize=floor, color=palette['blue'])
                else:
                    top.scatter(ci, yi, s=310, marker='o', c=[value], cmap=cmap, norm=norm, edgecolors='none')
                    top.text(ci, yi, str(value), ha='center', va='center', fontsize=floor,
                             color='white' if value / largest > .55 else '#253348')
                cell_records.append({'year': year, 'category': data['categories'][ci], 'count': value,
                                     'display': 'NA' if value is None else str(value)})
        top.set(xlim=(-.55, len(data['categories'])-.45), ylim=(-.55, len(data['years'])-.45))
        top.set_xticks(range(len(data['categories'])), data['categories'])
        top.set_yticks(range(len(data['years'])), data['years'])
        top.tick_params(length=0, pad=9)
        for spine in top.spines.values(): spine.set_visible(False)
        fig.text(.08, .94, 'a  Counts by year and category', fontweight='bold', fontsize=floor)
        cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cb_ax, ticks=[0, largest])
        cb.ax.set_title('Items', fontsize=floor, pad=9)
        fig.text(.19, .505, 'Open circle: zero    Box marked NA: not available', fontsize=floor, color=neutral)
        fig.text(.08, .462, 'b  Composition of complete years', fontweight='bold', fontsize=floor)
        for index, (num, percent) in enumerate(zip(comp['numerators'], comp['percentages'])):
            bottom.barh(index, percent, height=.48, color=palette['blue'])
            bottom.text(percent + 1.4, index, f'{num}/{comp["denominator"]} ({percent:.1f}%)', va='center', ha='left', fontsize=floor)
        bottom.set_yticks(range(len(data['categories'])), data['categories'])
        bottom.set(xlim=(0, max(comp['percentages'])*1.5+5), ylim=(len(data['categories'])-.45, -.55), xlabel='Share of included items (%)')
        bottom.set_xticks([0, 20, 40, 60][:1+int(bottom.get_xlim()[1]//20)])
        bottom.tick_params(axis='y', length=0, pad=8)
        bottom.spines[['top', 'right', 'left']].set_visible(False)
        bottom.spines['bottom'].set_color(neutral)
        included = ', '.join(map(str, comp['included_years']))
        excluded = ', '.join(map(str, comp['excluded_incomplete_years'])) or 'none'
        fig.text(.08, .065, 'Included years: '+included+'; excluded: '+excluded, fontsize=floor, color=neutral)
        fig.text(.08, .015, footer, fontsize=floor, color=neutral)
        caption = ('Exact item counts are shown with constant-size markers and a sequential color scale; numbers '
                   'supply exact readout. Zero is an open circle labeled 0; missing cells are boxes labeled NA and '
                   'are never imputed as zero. The composition pools only complete years ('+included+'); incomplete '
                   'years ('+excluded+') are excluded in full, including their observed cells. Categories are declared '
                   'mutually exclusive and exhaustive within each included year. Every bar labels its numerator, '
                   'the common denominator ('+str(comp['denominator'])+'), and its percentage. Pooled shares are not '
                   'the mean of annual percentages and are not a trend or causal effect.')
        record = {'panels': {'a': {'cells': cell_records, 'area_encodes': 'constant; count encoded by color and exact labels'},
                             'b': comp}, 'normalization': {'variable': 'nonnegative count', 'vmin': 0, 'vmax': largest,
                              'sequential': True, 'clip': False}, 'composition': comp,
                  'geometry': {'comparable_panel_axes': False, 'reason': 'Matrix cells and pooled bars have different axes and responsibilities'}}
    fig.canvas.draw()
    record['caption_english'] = ('Synthetic demonstration. ' if synthetic else 'Supplied JSON visualization. ') + caption
    return fig, axes, record


def export(recipe, output, style_path, data_path=None, qa_scripts=None):
    output = Path(output).resolve()
    if output.exists(): raise ValueError('Use a new output directory; existing paths are never overwritten')
    style_path = Path(style_path)
    style = json.loads(style_path.read_text(encoding='utf-8'))
    data = json.loads(Path(data_path).read_text(encoding='utf-8-sig')) if data_path else demo_data(recipe)
    validate_data(recipe, data)
    fig, axes, record = build(recipe, style, data, synthetic=data_path is None)
    output.mkdir(parents=True, exist_ok=False)
    source = output/'source.json'
    if data_path: shutil.copyfile(data_path, source)
    else: source.write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8')
    if recipe == 'counts':
        with (output/'counts.csv').open('w', encoding='utf-8', newline='') as handle:
            writer = csv.writer(handle); writer.writerow(['year', 'category', 'count'])
            writer.writerows([y, category, 'NA' if value is None else value] for y, row in zip(data['years'], data['counts']) for category, value in zip(data['categories'], row))
    exports = []
    for suffix in ('.pdf', '.svg', '.png'):
        target = output/(recipe+suffix); fig.savefig(target, dpi=max(300, int(style['raster_dpi'])))
        exports.append({'path': target.name, 'sha256': sha(target)})
    width, height = fig.get_size_inches()*25.4
    rectangles = {str(i): list(ax.get_position().bounds) for i, ax in enumerate(axes)}
    qa = {}
    qa_scripts = Path(qa_scripts) if qa_scripts else Path(__file__).resolve().parent
    aligner = qa_scripts/'audit_panel_alignment.py'
    if aligner.is_file() and recipe == 'scenarios':
        sys.path.insert(0, str(qa_scripts))
        from audit_panel_alignment import require_matplotlib_panel_alignment
        aligned = require_matplotlib_panel_alignment(fig, axes=axes, panel_ids=list('abc'), row_groups=[],
                      column_groups=[list('abc')], json_out=output/'alignment.json', strict=True)
        qa['alignment'] = {'verdict': aligned['verdict'], 'scope': 'Three same-domain symbolic plot rectangles'}
    else:
        qa['alignment'] = {'verdict': 'NOT AUDITABLE' if aligner.is_file() else 'not_executed_helper_unavailable',
                           'scope': 'Count matrix and pooled composition are not comparable coordinate panels'}
    plt.close(fig)
    for helper, args in [('audit_pdf_text.py', ['--min-pt', str(max(12, style['minimum_final_glyph_pt']))]),
                         ('audit_figure_collisions.py', [])]:
        if not (qa_scripts/helper).is_file():
            qa[helper] = {'status': 'not_executed_helper_unavailable'}; continue
        process = subprocess.run([sys.executable, str(qa_scripts/helper), str(output/(recipe+'.pdf')), *args, '--json'],
                                 capture_output=True, text=True, encoding='utf-8', timeout=90)
        report = json.loads(process.stdout)
        if 'pdf' in report: report['pdf'] = recipe+'.pdf'
        (output/(helper+'.json')).write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        qa[helper] = {'exit_code': process.returncode, 'verdict': report.get('verdict'), 'summary': report.get('summary')}
        if process.returncode: raise ValueError(helper+' failed; inspect the new output directory')
    caption = output/'caption.md'; caption.write_text(record['caption_english']+'\n', encoding='utf-8')
    record.update({'recipe': recipe, 'synthetic_demo': data_path is None,
                   'source': {'path': source.name, 'sha256': sha(source)},
                   'data_origin': 'self_authored_synthetic_example' if data_path is None else 'external_json_unverified_provenance',
                   'source_data_unchanged': True, 'script_sha256': sha(__file__), 'style_sha256': sha(style_path),
                   'size_mm': [float(width), float(height)], 'plot_rectangles': rectangles,
                   'minimum_final_glyph_pt': max(12, style['minimum_final_glyph_pt']),
                   'dpi': max(300, int(style['raster_dpi'])), 'outputs': exports,
                   'caption_sha256': sha(caption), 'qa': qa,
                   'visual_review': 'pending_actual_inspection', 'independent_acceptance': 'not_claimed'})
    (output/'mapping.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe', choices=RECIPES, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--style', type=Path)
    parser.add_argument('--data', type=Path, help='Optional exact JSON schema; bytes are preserved')
    parser.add_argument('--qa-scripts', type=Path)
    args = parser.parse_args()
    style = args.style or Path(__file__).resolve().parent.parent/'assets/mcm-figure-style.json'
    try: record = export(args.recipe, args.output, style, args.data, args.qa_scripts)
    except (OSError, ValueError) as exc: parser.error(str(exc))
    print(json.dumps({'status': 'generated', 'recipe': args.recipe, 'synthetic_demo': record['synthetic_demo']}))


if __name__ == '__main__': main()
