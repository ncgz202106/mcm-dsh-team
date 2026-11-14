"""Data and rendering invariants for source-state and count/composition examples."""
import copy
import csv
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'skill-overlays/nature-figure/scripts/mcm-evidence-panels.py'
STYLE = ROOT/'bundle/src/figure-style.json'
SPEC = importlib.util.spec_from_file_location('mcm_evidence', SOURCE)
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)


class EvidencePanels(unittest.TestCase):
    def setUp(self):
        self.style = json.loads(STYLE.read_text(encoding='utf-8'))

    def test_pooled_composition_excludes_whole_incomplete_year_and_preserves_denominator(self):
        data = evidence.demo_data('counts')
        comp = evidence.composition(data)
        self.assertEqual(comp['excluded_incomplete_years'], [2021])
        self.assertEqual(comp['included_years'], [2022, 2023, 2024])
        self.assertEqual(comp['numerators'], [13, 10, 9, 5])
        self.assertEqual(comp['denominator'], 37)
        self.assertAlmostEqual(sum(comp['percentages']), 100)
        np.testing.assert_allclose(comp['percentages'], np.array([13, 10, 9, 5])*100/37)
        # A year with 0 in every known cell is still incomplete, not a zero-total cohort.
        data['counts'][0] = [0, 0, 0, None]
        self.assertEqual(evidence.composition(data), comp)

    def test_zero_and_missing_have_distinct_explicit_readout_and_color_domain(self):
        fig, _, record = evidence.build('counts', self.style, evidence.demo_data('counts'))
        try:
            cells = record['panels']['a']['cells']
            zero = next(c for c in cells if c['year'] == 2021 and c['category'] == 'Balance')
            missing = next(c for c in cells if c['year'] == 2021 and c['category'] == 'Forecast')
            self.assertEqual(zero, {'year': 2021, 'category': 'Balance', 'count': 0, 'display': '0'})
            self.assertIsNone(missing['count']); self.assertEqual(missing['display'], 'NA')
            self.assertTrue(record['normalization']['sequential'])
            self.assertEqual(record['normalization']['vmin'], 0)
            self.assertFalse(record['normalization']['clip'])
        finally: plt.close(fig)

    def test_counts_reject_negative_fractional_boolean_and_nan_without_coercion(self):
        for invalid in [-1, .5, True, float('nan'), '0']:
            data = evidence.demo_data('counts'); data['counts'][0][0] = invalid
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, 'nonnegative integers'):
                evidence.validate_data('counts', data)

    def test_declared_partition_and_full_count_matrix_are_required(self):
        invalid = []
        for _ in range(4): invalid.append(evidence.demo_data('counts'))
        invalid[0]['category_partition'] = 'overlapping tags'
        invalid[1]['counts'][0].pop()
        invalid[2]['counts'] = [[None]*4 for _ in range(4)]
        invalid[3]['counts'] = [[0]*4 for _ in range(4)]
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValueError): evidence.validate_data('counts', data)

    def test_years_not_sorted_or_unique_are_rejected_instead_of_reordered(self):
        for years in [[2024, 2022, 2023, 2021], [2021, 2022, 2022, 2024], [True, 2022, 2023, 2024]]:
            data = evidence.demo_data('counts'); data['years'] = years
            with self.assertRaisesRegex(ValueError, 'unique, increasing integers'):
                evidence.validate_data('counts', data)

    def test_symbol_ids_coordinates_categories_preserved_in_all_three_panels(self):
        data = evidence.demo_data('scenarios'); frozen = copy.deepcopy(data)
        fig, axes, record = evidence.build('scenarios', self.style, data)
        try:
            self.assertEqual(data, frozen)
            expected = {r['id']: (r['x'], r['y'], r['domain'], r['category']) for r in data['points']}
            for panel in record['panels'].values():
                self.assertEqual({r['id']: (r['x'], r['y'], r['domain'], r['category']) for r in panel['symbols']}, expected)
            for ax in axes[1:]:
                self.assertEqual(ax.get_xlim(), axes[0].get_xlim()); self.assertEqual(ax.get_ylim(), axes[0].get_ylim())
                np.testing.assert_allclose(ax.get_position().bounds[::2], axes[0].get_position().bounds[::2])
            self.assertFalse(record['geometry']['metric'])
            self.assertEqual(record['encoding']['shape'], {'Category 1': 'o', 'Category 2': '^'})
        finally: plt.close(fig)

    def test_target_evaluation_ids_never_enter_fitting_panels(self):
        fig, _, record = evidence.build('scenarios', self.style, evidence.demo_data('scenarios'))
        try:
            active = lambda panel: {r['id'] for r in record['panels'][panel]['symbols'] if r['state'] == 'available_this_step'}
            self.assertTrue(active('c'))
            self.assertFalse(active('a') & active('c'))
            self.assertFalse(active('b') & active('c'))
            self.assertTrue(active('a') < active('b'))
        finally: plt.close(fig)

    def test_scenarios_require_nonmetric_declaration_finite_positions_and_disjoint_ids(self):
        invalid = [evidence.demo_data('scenarios') for _ in range(5)]
        invalid[0]['position_semantics'] = 'feature_distance'
        invalid[1]['points'][0]['x'] = float('inf')
        invalid[2]['points'][1]['id'] = invalid[2]['points'][0]['id']
        invalid[3]['points'][-1]['partition'] = 'both'
        invalid[4]['points'][-1]['x'] = 3
        for data in invalid:
            with self.subTest(), self.assertRaises(ValueError): evidence.validate_data('scenarios', data)

    def test_all_final_text_has_required_size_and_fits_canvas(self):
        for recipe in evidence.RECIPES:
            fig, axes, _ = evidence.build(recipe, self.style, evidence.demo_data(recipe))
            try:
                self.assertAlmostEqual(fig.get_figwidth()*25.4, 165.1)
                fig.canvas.draw(); renderer = fig.canvas.get_renderer()
                for text in fig.findobj(plt.Text):
                    if not text.get_visible() or not text.get_text(): continue
                    self.assertGreaterEqual(text.get_fontsize(), 12)
                    box = text.get_window_extent(renderer)
                    self.assertGreaterEqual(box.xmin, -.5); self.assertGreaterEqual(box.ymin, -.5)
                    self.assertLessEqual(box.xmax, fig.bbox.width+.5); self.assertLessEqual(box.ymax, fig.bbox.height+.5)
            finally: plt.close(fig)

    def test_external_source_bytes_retained_and_not_called_synthetic_or_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'data.json'
            source.write_bytes(json.dumps(evidence.demo_data('counts'), indent=4).replace('\n', '\r\n').encode('utf-8'))
            record = evidence.export('counts', Path(directory)/'out', STYLE, source)
            self.assertEqual(source.read_bytes(), (Path(directory)/'out/source.json').read_bytes())
            self.assertEqual(record['source']['sha256'], evidence.sha(source))
            self.assertFalse(record['synthetic_demo'])
            self.assertEqual(record['data_origin'], 'external_json_unverified_provenance')
            self.assertEqual(record['visual_review'], 'pending_actual_inspection')
            self.assertEqual(record['independent_acceptance'], 'not_claimed')
            self.assertNotIn('Synthetic demonstration.', record['caption_english'])

    def test_exports_hashes_editable_text_physical_dimensions_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)/'out'
            record = evidence.export('counts', out, STYLE)
            self.assertEqual(record['size_mm'][0], 165.1)
            self.assertEqual(record['dpi'], 300)
            png = (out/'counts.png').read_bytes()
            self.assertEqual(struct.unpack('>II', png[16:24]), (1950, 2130))
            self.assertIn('<text', (out/'counts.svg').read_text(encoding='utf-8'))
            for item in record['outputs']: self.assertEqual(item['sha256'], evidence.sha(out/item['path']))
            with (out/'counts.csv').open(newline='') as handle: rows = list(csv.DictReader(handle))
            self.assertEqual(next(r['count'] for r in rows if r['year']=='2021' and r['category']=='Forecast'), 'NA')
            self.assertEqual(next(r['count'] for r in rows if r['year']=='2021' and r['category']=='Balance'), '0')
            before = evidence.sha(out/'counts.pdf')
            with self.assertRaisesRegex(ValueError, 'never overwritten'): evidence.export('counts', out, STYLE)
            self.assertEqual(before, evidence.sha(out/'counts.pdf'))


if __name__ == '__main__': unittest.main()
