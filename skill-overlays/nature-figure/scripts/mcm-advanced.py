#!/usr/bin/env python3
"""Conditional 3D recipes with explicit units and linked 2D references.

Requires existing numpy/matplotlib only. No interpolation is called measured
data. CSV schemas are deliberately fixed: surface x_m,y_m,response_kPa;
trajectory time_s,x_m,y_m,z_m. Without --data, clearly marked deterministic
synthetic examples are generated. Existing output directories are refused.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from matplotlib.collections import LineCollection
from mpl_toolkits.mplot3d.art3d import Line3DCollection

SCHEMAS = {'surface': ('x_m', 'y_m', 'response_kPa'),
           'trajectory': ('time_s', 'x_m', 'y_m', 'z_m')}
CAMERA = {'elevation_degrees': 28, 'azimuth_degrees': -128,
          'projection': 'orthographic'}
MINIMUM_DPI = 300


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def demo_data(recipe):
    """Original deterministic arrays; no random or copied observations."""
    if recipe == 'surface':
        x, y = np.meshgrid(np.linspace(0, 4, 9), np.linspace(0, 3, 7))
        z = 20 + 2*x + 1.5*y + 5*np.exp(-((x-2.2)**2 + (y-1.4)**2)/.9)
        return np.column_stack((x.ravel(), y.ravel(), z.ravel()))
    if recipe == 'trajectory':
        t = np.linspace(0, 60, 61)
        theta = t*np.pi/20
        return np.column_stack((t, 14*np.cos(theta), 14*np.sin(theta), 2+.4*t))
    raise ValueError('Unknown recipe')


def read_csv(path, recipe):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != SCHEMAS[recipe]:
            raise ValueError('Expected exact CSV header: '+','.join(SCHEMAS[recipe]))
        try:
            rows = []
            for row in reader:
                if None in row:
                    raise ValueError('Unexpected extra CSV cells')
                rows.append([float(row[k]) for k in SCHEMAS[recipe]])
        except (TypeError, ValueError, KeyError) as exc:
            raise ValueError('Every CSV cell must be a finite number') from exc
    data = np.asarray(rows, dtype=float)
    validate_data(recipe, data)
    return data


def validate_data(recipe, data):
    data = np.asarray(data)
    if data.ndim != 2 or data.shape[1] != len(SCHEMAS[recipe]) or len(data) < 3:
        raise ValueError('Expected at least three complete rows with fixed unit columns')
    if not np.isfinite(data).all():
        raise ValueError('Missing or nonfinite values must be resolved upstream')
    if recipe == 'surface':
        x, y = np.unique(data[:, 0]), np.unique(data[:, 1])
        if len(x) < 3 or len(y) < 3:
            raise ValueError('Surface needs at least a 3 by 3 tested grid')
        if len(np.unique(data[:, :2], axis=0)) != len(data):
            raise ValueError('Duplicate grid coordinates: aggregate with a stated upstream rule')
        if len(x)*len(y) != len(data):
            raise ValueError('Incomplete grid: missing cells are not filled or extrapolated')
        if np.ptp(data[:, 2]) <= 0:
            raise ValueError('Constant response adds no surface evidence; use a 2D display')
    elif recipe == 'trajectory':
        if np.any(np.diff(data[:, 0]) <= 0):
            raise ValueError('Time must be strictly increasing in input row order')
        if np.any(np.ptp(data[:, 1:], axis=0) <= 0):
            raise ValueError('A constant spatial coordinate needs a 2D trajectory, not 3D')
        centered = data[:, 1:] - np.mean(data[:, 1:], axis=0)
        if np.linalg.matrix_rank(centered) < 3:
            raise ValueError('Planar or linear positions do not require this 3D recipe')
    else:
        raise ValueError('Unknown recipe')


def surface_grid(data):
    """Reorder, never interpolate or average, the complete unique input grid."""
    validate_data('surface', data)
    order = np.lexsort((data[:, 0], data[:, 1]))
    x, y = np.unique(data[:, 0]), np.unique(data[:, 1])
    xx, yy = np.meshgrid(x, y)
    return xx, yy, data[order, 2].reshape(len(y), len(x))


def apply_style(style):
    minimum = max(12., float(style['minimum_final_glyph_pt']))
    plt.rcParams.update({'font.family': 'sans-serif',
                         'font.sans-serif': [style['font_family']],
                         'font.size': minimum, 'axes.labelsize': max(minimum, style['axis_font_pt']),
                         'axes.titlesize': max(minimum, style['title_font_pt']),
                         'xtick.labelsize': minimum, 'ytick.labelsize': minimum,
                         'legend.fontsize': minimum, 'pdf.fonttype': 42, 'svg.fonttype': 'none',
                         'axes.linewidth': .7, 'figure.facecolor': 'white',
                         'savefig.facecolor': 'white', 'legend.frameon': False,
                         'axes.formatter.useoffset': False})
    return minimum


def limits(values, fraction=.07):
    lo, hi = float(np.min(values)), float(np.max(values))
    pad = max((hi-lo)*fraction, 1.e-6)
    return [lo-pad, hi+pad]


def decorate_3d(ax):
    ax.view_init(elev=CAMERA['elevation_degrees'], azim=CAMERA['azimuth_degrees'])
    ax.set_proj_type('ortho')
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.set_major_locator(plt.MaxNLocator(3))
        axis.pane.set_facecolor((1, 1, 1, 0))
        axis.labelpad = 16
    ax.tick_params(pad=1)
    ax.grid(False)


def label_panel(fig, letter, title, x, y):
    fig.text(x, y, letter, weight='bold', va='bottom')
    fig.text(x+.045, y, title, fontsize=14, va='bottom')


def build(recipe, style, data, synthetic=True):
    validate_data(recipe, data)
    apply_style(style)
    fig = plt.figure(figsize=(float(style['final_width_mm'])/25.4, 9.0))
    primary = fig.add_axes([.08, .52, .73, .40], projection='3d')
    decorate_3d(primary)
    cb_ax = fig.add_axes([.87, .60, .025, .23])
    neutral = style['palette']['neutral']
    label_panel(fig, 'a', 'Response surface' if recipe == 'surface' else 'Spatial path', .12, .94)
    if recipe == 'surface':
        xx, yy, zz = surface_grid(data)
        norm = Normalize(vmin=float(zz.min()), vmax=float(zz.max()), clip=False)
        primary.plot_surface(xx, yy, zz, cmap='cividis', norm=norm, alpha=1,
                             rcount=zz.shape[0], ccount=zz.shape[1],
                             linewidth=.25, edgecolor='#FFFFFF', shade=False)
        primary.scatter(data[:, 0], data[:, 1], data[:, 2], s=11, color='#202124',
                        depthshade=False, zorder=5)
        primary.set(xlabel='x (m)', ylabel='y (m)', zlabel='Response (kPa)')
        primary.set_xlim(limits(data[:, 0])); primary.set_ylim(limits(data[:, 1]))
        primary.set_zlim(limits(data[:, 2]))
        primary.set_box_aspect((1, .75, .65))
        reference = fig.add_axes([.14, .12, .62, .31])
        levels = np.linspace(norm.vmin, norm.vmax, 9)
        reference.contourf(xx, yy, zz, levels=levels, cmap='cividis', norm=norm)
        reference.contour(xx, yy, zz, levels=levels, colors='#FFFFFF', linewidths=.65)
        reference.scatter(data[:, 0], data[:, 1], s=12, color='#202124', zorder=4)
        reference.set(xlabel='x (m)', ylabel='y (m)', xlim=limits(data[:, 0]), ylim=limits(data[:, 1]))
        reference.set_aspect('equal', adjustable='box')
        reference.xaxis.set_major_locator(plt.MaxNLocator(4))
        reference.yaxis.set_major_locator(plt.MaxNLocator(4))
        label_panel(fig, 'b', 'Plan view of the same grid', .12, .46)
        cb_label = 'kPa'
        mapping = {'a': {'role': 'Show joint response to two tested inputs',
                          'x': 'x_m', 'y': 'y_m', 'z': 'response_kPa',
                          'color': 'response_kPa', 'points': 'All supplied grid samples'},
                   'b': {'role': 'Read input combinations without 3D occlusion',
                          'x': 'x_m', 'y': 'y_m', 'color': 'response_kPa',
                          'points': 'All supplied grid samples'}}
        geometry = {'box_aspect': [1, .75, .65], 'metric_aspect': False,
                    'aspect_note': 'Response and position have different units; height is not a spatial distance.',
                    'grid_shape': list(zz.shape), 'contour_levels': levels.tolist(),
                    'interpolation': 'Surface faces and contour boundaries join tested grid values; no new observations.',
                    'alignment_note': '3D projected area and metric plan view have intentionally different shapes.'}
        caption = ('Response on a complete tested x-y grid, with response in kPa. '
                   'Black dots identify all '+str(len(data))+' supplied samples in both panels. '
                   'Surface faces and contour boundaries interpolate between these grid values; '
                   'intermediate colors are not additional measurements. Both panels share one '
                   'unclipped color normalization. The height axis is response, not distance; '
                   'the plan view preserves equal x-y distance. No extrapolation or uncertainty is inferred.')
        axes = [primary, reference]
    else:
        t, xyz = data[:, 0], data[:, 1:]
        norm = Normalize(vmin=float(t.min()), vmax=float(t.max()), clip=False)
        segments = np.stack((xyz[:-1], xyz[1:]), axis=1)
        line = Line3DCollection(segments, cmap='cividis', norm=norm, linewidth=2)
        line.set_array((t[:-1]+t[1:])/2); primary.add_collection3d(line)
        primary.scatter(*xyz.T, c=t, cmap='cividis', norm=norm, s=13, depthshade=False)
        common = limits(xyz)
        primary.set(xlabel='x (m)', ylabel='y (m)', zlabel='z (m)',
                    xlim=common, ylim=common, zlim=common)
        primary.set_box_aspect((1, 1, 1))
        # Stagger adjacent floor-axis tick labels at the common front corner.
        ticks = primary.xaxis.get_major_locator().tick_values(*common)
        ticks = ticks[(ticks >= common[0]) & (ticks <= common[1])]
        primary.set_xticks(ticks[1:] if len(ticks) > 1 else ticks)
        references = [fig.add_axes([.13, .12, .31, .31]),
                      fig.add_axes([.61, .12, .31, .31])]
        for ax, second in zip(references, (1, 2)):
            coords = xyz[:, [0, second]]
            projected = np.stack((coords[:-1], coords[1:]), axis=1)
            collection = LineCollection(projected, cmap='cividis', norm=norm, linewidth=1.8)
            collection.set_array((t[:-1]+t[1:])/2); ax.add_collection(collection)
            ax.scatter(*coords.T, c=t, cmap='cividis', norm=norm, s=11, zorder=3)
            ax.scatter(*coords[0], marker='s', s=55, facecolor='white', edgecolor='#202124', zorder=5)
            ax.scatter(*coords[-1], marker='^', s=60, facecolor='white', edgecolor='#202124', zorder=5)
            ax.set(xlim=common, ylim=common, xlabel='x (m)', ylabel=('y' if second == 1 else 'z')+' (m)')
            ax.set_aspect('equal', adjustable='box')
            ax.set_xticks(np.linspace(*common, 3)); ax.set_yticks(np.linspace(*common, 3))
            ax.xaxis.set_major_formatter(plt.FormatStrFormatter('%.3g'))
            ax.yaxis.set_major_formatter(plt.FormatStrFormatter('%.3g'))
        primary.scatter(*xyz[0], marker='s', s=55, facecolor='white', edgecolor='#202124', depthshade=False)
        primary.scatter(*xyz[-1], marker='^', s=60, facecolor='white', edgecolor='#202124', depthshade=False)
        label_panel(fig, 'b', 'XY projection', .13, .43)
        label_panel(fig, 'c', 'XZ projection', .61, .43)
        fig.text(.13, .055, 'Square: start    Triangle: end', fontsize=12, color=neutral)
        cb_label = 'Time (s)'
        mapping = {'a': {'role': 'Show genuine nonplanar spatial geometry', 'x': 'x_m', 'y': 'y_m',
                          'z': 'z_m', 'color': 'time_s', 'points': 'All supplied positions'},
                   'b': {'role': 'Resolve horizontal location without occlusion', 'x': 'x_m', 'y': 'y_m',
                          'color': 'time_s', 'points': 'All supplied positions'},
                   'c': {'role': 'Resolve height at the same times', 'x': 'x_m', 'y': 'z_m',
                          'color': 'time_s', 'points': 'All supplied positions'}}
        geometry = {'box_aspect': [1, 1, 1], 'metric_aspect': True,
                    'common_spatial_limits_m': common, 'all_samples_retained': True,
                    'interpolation': 'Straight segments connect consecutive input rows; no intermediate positions are measured.',
                    'alignment_note': 'XY and XZ references have identical square plot areas and physical limits; 3D is a hero panel.'}
        caption = ('Nonplanar spatial trajectory in meters; color encodes time in seconds, not height. '
                   'All '+str(len(data))+' supplied positions are marked, with straight segments connecting '
                   'successive time-ordered rows. The square and triangle mark the first and last '
                   'position. XY and XZ views retain every sample and share the same time normalization '
                   'and spatial limits. Equal metric aspect is used in all spatial dimensions. '
                   'Connecting segments do not establish measured intermediate positions, speed, '
                   'or collision clearance; these require upstream analysis.')
        axes = [primary, *references]
    colorbar = fig.colorbar(ScalarMappable(norm=norm, cmap='cividis'), cax=cb_ax,
                            ticks=np.linspace(norm.vmin, norm.vmax, 3))
    cb_ax.set_title(cb_label, fontsize=12, pad=12)
    colorbar.ax.yaxis.set_major_formatter(plt.FormatStrFormatter('%.3g'))
    footer = 'Synthetic demonstration' if synthetic else 'Supplied CSV; provenance not validated'
    fig.text(.13, .017, footer, fontsize=12, color=neutral)
    fig.canvas.draw()
    return fig, axes, {'panels': mapping, 'geometry': geometry,
                       'normalization': {'variable': 'response_kPa' if recipe == 'surface' else 'time_s',
                                         'vmin': norm.vmin, 'vmax': norm.vmax,
                                         'cmap': 'cividis', 'clip': False},
                       'caption_english': ('Synthetic demonstration. ' if synthetic else 'Supplied CSV visualization. ')+caption}


def run_qa(fig, axes, out, recipe, qa_scripts):
    qa = {}
    helper = qa_scripts/'audit_panel_alignment.py'
    if helper.is_file():
        sys.path.insert(0, str(qa_scripts))
        from audit_panel_alignment import require_matplotlib_panel_alignment, PanelAlignmentError
        groups = [['b', 'c']] if recipe == 'trajectory' else []
        try:
            result = require_matplotlib_panel_alignment(
                fig, axes=axes, panel_ids=list('abc')[:len(axes)], row_groups=groups,
                column_groups=[], exemptions=[{'panels': ['a'], 'checks': ['all'],
                    'reason': 'A projected 3D hero is not geometrically comparable to orthographic 2D references.'}],
                json_out=out/'alignment.json', strict=True)
            qa['alignment'] = {'verdict': result['verdict'], 'scope': '2D comparable references only; 3D explicitly exempt'}
        except PanelAlignmentError:
            report = json.loads((out/'alignment.json').read_text(encoding='utf-8'))
            if recipe != 'surface' or report.get('errors') != [
                    'No comparable row, column or shared-boundary groups were declared or inferred']:
                raise
            qa['alignment'] = {'verdict': 'NOT AUDITABLE',
                'scope': 'No comparable panel group: projected 3D and metric plan view are intentionally unequal; no alignment pass claimed.'}
    else:
        qa['alignment'] = {'status': 'not_executed_helper_unavailable'}
    return qa


def export(recipe, output, style_path, data_path=None, qa_scripts=None):
    """Validate first; reserve a new directory atomically; never overwrite."""
    out = Path(output).resolve()
    if out.exists():
        raise ValueError('Use a new output directory; existing paths are never overwritten')
    style_path = Path(style_path)
    style = json.loads(style_path.read_text(encoding='utf-8'))
    data = read_csv(data_path, recipe) if data_path else demo_data(recipe)
    validate_data(recipe, data)
    fig, axes, record = build(recipe, style, data, synthetic=data_path is None)
    out.mkdir(parents=True, exist_ok=False)
    source = out/'source.csv'
    if data_path:
        shutil.copyfile(data_path, source)
    else:
        with source.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.writer(handle); writer.writerow(SCHEMAS[recipe]); writer.writerows(data)
    qa_scripts = Path(qa_scripts) if qa_scripts else Path(__file__).resolve().parent
    qa = run_qa(fig, axes, out, recipe, qa_scripts)
    exports = []
    for extension in ('.pdf', '.svg', '.png'):
        path = out/(recipe+extension)
        fig.savefig(path, dpi=max(MINIMUM_DPI, int(style['raster_dpi'])))
        exports.append({'path': path.name, 'sha256': digest(path)})
    width_mm, height_mm = fig.get_size_inches()*25.4
    rectangles = {chr(97+i): (ax.get_position().bounds*np.array([width_mm, height_mm, width_mm, height_mm])).tolist()
                  for i, ax in enumerate(axes)}
    plt.close(fig)
    for helper, arguments in [('audit_pdf_text.py', ['--min-pt', str(max(12, style['minimum_final_glyph_pt']))]),
                              ('audit_figure_collisions.py', [])]:
        if not (qa_scripts/helper).is_file():
            qa[helper] = {'status': 'not_executed_helper_unavailable'}; continue
        process = subprocess.run([sys.executable, str(qa_scripts/helper), str(out/(recipe+'.pdf')),
                                  *arguments, '--json'], capture_output=True, text=True,
                                 encoding='utf-8', timeout=90)
        report = None
        try:
            report = json.loads(process.stdout)
            if 'pdf' in report:
                report['pdf'] = recipe+'.pdf'
            qa_text = json.dumps(report, indent=2)
        except json.JSONDecodeError:
            qa_text = process.stdout
        (out/(helper+'.json')).write_text(qa_text+'\n', encoding='utf-8')
        qa[helper] = {'exit_code': process.returncode}
        if isinstance(report, dict):
            for key in ('verdict', 'summary', 'minimum_found_pt', 'below_minimum_count'):
                if key in report:
                    qa[helper][key] = report[key]
        if process.returncode:
            raise ValueError(helper+' failed; inspect the new output directory')
    caption = out/'caption.md'; caption.write_text(record['caption_english']+'\n', encoding='utf-8')
    record.update({'recipe': recipe, 'synthetic_demo': data_path is None,
                   'data_origin': 'deterministic_synthetic_demo' if data_path is None else 'external_csv_unverified_provenance',
                   'schema': list(SCHEMAS[recipe]), 'row_count': len(data), 'excluded_rows': 0,
                   'source': {'path': source.name, 'sha256': digest(source)},
                   'script_sha256': digest(__file__), 'style_sha256': digest(style_path),
                   'size_mm': [float(width_mm), float(height_mm)],
                   'minimum_final_glyph_pt': max(12, style['minimum_final_glyph_pt']),
                   'dpi': max(MINIMUM_DPI, int(style['raster_dpi'])), 'camera': CAMERA,
                   'plot_rectangles_mm': rectangles, 'outputs': exports,
                   'caption_sha256': digest(caption), 'qa': qa,
                   'visual_review': 'pending_actual_inspection', 'independent_acceptance': 'not_claimed',
                   'reuse': 'Keep fixed CSV units or adapt the schema, labels, caption and domain checks together. Freeze the upstream source; validate provenance separately.'})
    (out/'mapping.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe', required=True, choices=tuple(SCHEMAS))
    parser.add_argument('--output', required=True, type=Path, help='A new directory; overwrite is refused')
    parser.add_argument('--style', type=Path, help='Project figure-style.json; default is the overlay asset')
    parser.add_argument('--data', type=Path, help='Optional fixed-schema CSV in declared SI units')
    parser.add_argument('--qa-scripts', type=Path, help='Optional installed nature-figure/scripts directory')
    args = parser.parse_args()
    style = args.style or Path(__file__).resolve().parent.parent/'assets/mcm-figure-style.json'
    try:
        result = export(args.recipe, args.output, style, args.data, args.qa_scripts)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({'status': 'generated', 'recipe': args.recipe,
                      'synthetic_demo': result['synthetic_demo'], 'row_count': result['row_count']}))


if __name__ == '__main__':
    main()
