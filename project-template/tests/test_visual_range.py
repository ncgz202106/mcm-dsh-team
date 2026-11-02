"""Failures that PDF text/geometry inspection cannot detect."""
from pathlib import Path
import importlib.util
import unittest

spec=importlib.util.spec_from_file_location('visual_range',Path(__file__).resolve().parents[1]/'scripts/visual_range.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
guard=module.require_visible_data


class VisibleEvidence(unittest.TestCase):
    def test_negative_result_cannot_be_hidden_by_pretty_axis(self):
        with self.assertRaisesRegex(ValueError,'outside final axis'):
            guard([-.12,.03],[-.05,.10])

    def test_interval_tail_is_checked_even_if_point_is_visible(self):
        with self.assertRaisesRegex(ValueError,'outside final axis'):
            guard([.03],[0,.1],lower=[-.01],upper=[.06])

    def test_inverted_axis_and_valid_interval(self):
        result=guard([-.12,.03],[.1,-.2],lower=[-.14,.01],upper=[-.10,.07])
        self.assertTrue(result['passed']);self.assertEqual(result['defined_points'],2)
        self.assertEqual(result['visual_review'],'still_required')

    def test_missing_result_is_never_silently_zero_imputed(self):
        with self.assertRaisesRegex(ValueError,'undefined'):
            guard([None,.03],[-.2,.1])
        result=guard([None,.03],[-.2,.1],lower=[None,.01],upper=[None,.06],allow_undefined=True)
        self.assertEqual(result['undefined_points'],1)

    def test_inconsistent_missing_interval_and_unmatched_arrays(self):
        with self.assertRaises(ValueError):guard([None,.03],[-.2,.1],lower=[0,.01],upper=[0,.06],allow_undefined=True)
        with self.assertRaisesRegex(ValueError,'lengths'):guard([.03,.04],[-.2,.1],lower=[.01],upper=[.06])

    def test_reversed_interval_and_bad_axis_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'reversed'):guard([.03],[0,.1],lower=[.05],upper=[.01])
        for limits in ([0,0],[None,1],[0,float('inf')]):
            with self.assertRaises(ValueError):guard([.03],limits)

    def test_empty_all_missing_infinite_and_boolean_series(self):
        for vals in ([],[None],[float('inf')],[True]):
            with self.assertRaises(ValueError):guard(vals,[-1,1],allow_undefined=True)

    def test_float_roundoff_tolerance_does_not_hide_a_real_overrun(self):
        self.assertTrue(guard([0],[0,1],lower=[-1e-16],upper=[.01])['passed'])
        with self.assertRaises(ValueError):guard([0],[0,1],lower=[-.001],upper=[.01])


if __name__=='__main__':unittest.main()
