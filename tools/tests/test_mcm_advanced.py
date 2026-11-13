"""Data integrity, unit mapping and physical exports for conditional 3D recipes."""
import csv
import importlib.util
import json
from pathlib import Path
import re
import struct
import tempfile
import unittest

import numpy as np
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT/'skill-overlays/nature-figure/scripts/mcm-advanced.py'
STYLE = ROOT/'bundle/src/figure-style.json'
spec = importlib.util.spec_from_file_location('mcm_advanced', SCRIPT)
advanced = importlib.util.module_from_spec(spec)
spec.loader.exec_module(advanced)


class AdvancedRecipes(unittest.TestCase):
    def test_complete_grid_reordered_without_interpolation_or_averaging(self):
        source = advanced.demo_data('surface')[::-1]
        x, y, z = advanced.surface_grid(source)
        for row in source:
            selected = (x == row[0]) & (y == row[1])
            self.assertEqual(z[selected].item(), row[2])
        self.assertEqual(z.size, len(source))

    def test_missing_duplicate_nonfinite_or_constant_surface_refused(self):
        data = advanced.demo_data('surface')
        invalid = [data[:-1], np.vstack([data, data[0]]), data.copy(), data.copy()]
        invalid[2][0, 2] = np.nan
        invalid[3][:, 2] = 5
        for sample in invalid:
            with self.subTest(shape=sample.shape), self.assertRaises(ValueError):
                advanced.validate_data('surface', sample)

    def test_time_order_and_true_third_spatial_dimension_are_required(self):
        data = advanced.demo_data('trajectory')
        invalid = [data[::-1], data.copy(), data.copy(), data.copy()]
        invalid[1][1, 0] = invalid[1][0, 0]
        invalid[2][:, 3] = invalid[2][:, 1]+invalid[2][:, 2]
        invalid[3][:, 3] = 0
        for sample in invalid:
            with self.subTest(first_time=sample[0, 0]), self.assertRaises(ValueError):
                advanced.validate_data('trajectory', sample)

    def test_fixed_unit_schema_rejects_ambiguous_or_wrong_units(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'input.csv'
            for header in ('x,y,z', 'x_km,y_m,response_kPa', 'x_m,y_m,response_kPa,extra'):
                source.write_text(header+'\n1,2,3\n', encoding='utf-8')
                with self.subTest(header=header), self.assertRaisesRegex(ValueError, 'exact CSV header'):
                    advanced.read_csv(source, 'surface')

    def test_extra_csv_cells_cannot_be_silently_dropped(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'input.csv'
            source.write_text('x_m,y_m,response_kPa\n1,2,3,4\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                advanced.read_csv(source, 'surface')

    def test_mapping_matches_units_normalization_camera_and_metric_geometry(self):
        style = json.loads(STYLE.read_text(encoding='utf-8'))
        for recipe in advanced.SCHEMAS:
            data = advanced.demo_data(recipe)
            fig, axes, record = advanced.build(recipe, style, data)
            try:
                column = 2 if recipe == 'surface' else 0
                self.assertEqual(record['normalization']['vmin'], data[:, column].min())
                self.assertEqual(record['normalization']['vmax'], data[:, column].max())
                self.assertFalse(record['normalization']['clip'])
                self.assertAlmostEqual(fig.get_figwidth()*25.4, 165.1)
                self.assertEqual(axes[0].get_zlabel(), 'Response (kPa)' if recipe == 'surface' else 'z (m)')
                self.assertEqual(len(record['panels']), 2 if recipe == 'surface' else 3)
                self.assertEqual(record['geometry']['metric_aspect'], recipe == 'trajectory')
                self.assertEqual(axes[0].elev, advanced.CAMERA['elevation_degrees'])
                if recipe == 'trajectory':
                    np.testing.assert_allclose(axes[1].get_position().bounds[2:],
                                               axes[2].get_position().bounds[2:])
                    np.testing.assert_allclose(axes[0].get_box_aspect(),
                                               np.repeat(axes[0].get_box_aspect()[0], 3))
                    self.assertEqual(axes[1].get_xlim(), axes[2].get_ylim())
            finally:
                plt.close(fig)

    def test_external_csv_bytes_and_units_are_preserved_and_not_called_measured(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'supplied.csv'
            with source.open('w', encoding='utf-8', newline='') as handle:
                writer = csv.writer(handle); writer.writerow(advanced.SCHEMAS['trajectory'])
                writer.writerows(advanced.demo_data('trajectory'))
            before = source.read_bytes()
            record = advanced.export('trajectory', root/'new', STYLE, source)
            self.assertEqual((root/'new/source.csv').read_bytes(), before)
            self.assertEqual(source.read_bytes(), before)
            self.assertFalse(record['synthetic_demo'])
            self.assertEqual(record['data_origin'], 'external_csv_unverified_provenance')
            self.assertEqual(record['excluded_rows'], 0)
            self.assertEqual(record['source']['sha256'], advanced.digest(source))
            self.assertIn('Supplied CSV', record['caption_english'])

    def test_physical_export_width_resolution_and_existing_directory_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'new'
            record = advanced.export('surface', output, STYLE)
            self.assertTrue(record['synthetic_demo'])
            self.assertIn('not additional measurements', record['caption_english'])
            png = (output/'surface.png').read_bytes()
            self.assertEqual(struct.unpack('>II', png[16:24]), (1950, 2700))
            p = png.index(b'pHYs')
            xdpi, ydpi, unit = struct.unpack('>IIB', png[p+4:p+13])
            self.assertEqual(unit, 1)
            self.assertGreaterEqual(xdpi*.0254, 299.99)
            self.assertEqual(xdpi, ydpi)
            media = re.search(rb'/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)',
                              (output/'surface.pdf').read_bytes())
            self.assertIsNotNone(media)
            width_pt = float(media[3])-float(media[1])
            self.assertAlmostEqual(width_pt/72*25.4, 165.1, places=5)
            self.assertIn('width="468pt"', (output/'surface.svg').read_text(encoding='utf-8'))
            mapping = json.loads((output/'mapping.json').read_text(encoding='utf-8'))
            self.assertEqual(mapping['minimum_final_glyph_pt'], 12)
            hashes_before = {p.name: advanced.digest(p) for p in output.iterdir()}
            with self.assertRaisesRegex(ValueError, 'new output directory'):
                advanced.export('surface', output, STYLE)
            self.assertEqual(hashes_before, {p.name: advanced.digest(p) for p in output.iterdir()})


if __name__ == '__main__':
    unittest.main()
