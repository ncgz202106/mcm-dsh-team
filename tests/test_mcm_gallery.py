"""Numerical semantics of the synthetic layout examples, not an aesthetics score."""
from pathlib import Path
import importlib.util
import json
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('gallery', ROOT/'skill-overlays/nature-figure/scripts/mcm-gallery.py')
gallery = importlib.util.module_from_spec(spec); spec.loader.exec_module(gallery)
STYLE = json.loads((ROOT/'bundle/src/figure-style.json').read_text())


class GalleryTests(unittest.TestCase):
    def setUp(self): gallery.apply_style(STYLE)
    def tearDown(self): gallery.plt.close('all')

    def test_frontier_includes_ties_and_excludes_dominated(self):
        np.testing.assert_array_equal(gallery.nondominated([1, 2, 2, 3, 4], [1, 3, 3, 2, 4]),
                                      [True, True, True, False, True])
        with self.assertRaises(ValueError): gallery.nondominated([1, 2], [1, float('nan')])

    def test_paired_units_and_ecdf_are_not_sampled_or_sorted_apart(self):
        fig, data, _, _ = gallery.build('paired', STYLE)
        np.testing.assert_allclose(data['treatment']-data['baseline'], data['difference'])
        self.assertEqual(len(set(data['id'])), 120)
        np.testing.assert_array_equal(np.sort(data['difference']), data['ecdf_x'])
        self.assertEqual(data['ecdf_probability'][-1], 1)
        self.assertLess(data['difference'].min(), 0)
        np.testing.assert_allclose(data['quantiles'], np.quantile(data['difference'], [.1, .25, .5, .75, .9]))
        points = fig.axes[0].collections[1].get_offsets()
        np.testing.assert_allclose(points[:, 1], data['difference'])

    def test_sensitivity_keeps_middle_reversal_and_three_tested_choices(self):
        _, data, _, _ = gallery.build('sensitivity', STYLE)
        self.assertGreater(data['strategy_a'][1], max(data['strategy_a'][0], data['strategy_a'][2]))
        np.testing.assert_array_equal(data['selected'], [1, 0, 1])

    def test_shared_spatial_scale_and_all_cells(self):
        fig, data, _, _ = gallery.build('spatial', STYLE)
        self.assertEqual(data['grid_values'].shape, (4, 8, 8))
        for ax, values in zip(fig.axes[:4], data['grid_values']):
            im = ax.images[0]
            self.assertEqual((im.norm.vmin, im.norm.vmax), (0, 1))
            np.testing.assert_array_equal(im.get_array(), values)
            self.assertEqual(im.get_interpolation(), 'nearest')

    def test_prediction_interval_and_every_residual(self):
        fig, data, _, _ = gallery.build('prediction', STYLE)
        np.testing.assert_allclose(data['upper']-data['mean'], 1.96*1.2)
        residual = fig.axes[1].collections[0].get_offsets()
        np.testing.assert_allclose(residual[:, 1], data['observed']-data['mean'])
        self.assertEqual(len(residual), 36)
        self.assertEqual(data['split'], 24)

    def test_axis_guard_rejects_hidden_interval_and_missing_values(self):
        gallery.visible([-.2, .5], (1, -1))
        for values in ([-1.1, .2], [0, float('nan')], []):
            with self.assertRaises(ValueError): gallery.visible(values, (-1, 1))

    def test_strategy_axes_and_baselines_are_identical(self):
        fig, data, _, _ = gallery.build('strategies', STYLE)
        for ax, values in zip(fig.axes, data['curves']):
            self.assertEqual(ax.get_ylim(), (20, 57))
            np.testing.assert_array_equal(ax.lines[0].get_ydata(), data['reference'])
            np.testing.assert_array_equal(ax.lines[1].get_ydata(), values)
        self.assertLess(data['curves'][-1, -1], data['reference'][-1])


if __name__ == '__main__': unittest.main()
