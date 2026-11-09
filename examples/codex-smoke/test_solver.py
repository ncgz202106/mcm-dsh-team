"""Author tests for the synthetic RK4 solver, independent of scenario generation."""

import json
import math
from pathlib import Path
import unittest

from solver import analytic, solve


CONTRACT = json.loads(Path(__file__).with_name("model-contract.json").read_text(encoding="utf-8"))
PARAMETERS = CONTRACT["parameters"]


def max_error(dt):
    rows = solve(**PARAMETERS, dt=dt)
    return max(
        abs(value - analytic(t, PARAMETERS["r"], PARAMETERS["K"], PARAMETERS["d"], PARAMETERS["B0"]))
        for t, value in rows
    )


class SolverTests(unittest.TestCase):
    def test_initial_condition(self):
        self.assertEqual(analytic(0, 0.35, 100, 0.08, 12), 12)
        self.assertEqual(solve(**PARAMETERS)[0], (0.0, PARAMETERS["B0"]))

    def test_default_accuracy_and_finite_nonnegative_trajectory(self):
        rows = solve(**PARAMETERS)
        self.assertEqual(len(rows), 301)
        self.assertEqual(rows[-1][0], PARAMETERS["horizon"])
        self.assertTrue(all(math.isfinite(b) and b >= 0 for _, b in rows))
        self.assertLess(max_error(0.1), 0.001)

    def test_fourth_order_refinement(self):
        errors = [max_error(dt) for dt in (0.2, 0.1, 0.05)]
        self.assertGreater(errors[0], errors[1])
        self.assertGreater(errors[1], errors[2])
        for coarse, fine in zip(errors, errors[1:]):
            self.assertGreater(coarse / fine, 14)
            self.assertLess(coarse / fine, 18)

    def test_equal_growth_and_mortality(self):
        for t in (0, 1, 30):
            expected = 12 / (1 + 0.35 / 100 * 12 * t)
            self.assertAlmostEqual(analytic(t, 0.35, 100, 0.35, 12), expected, places=13)
        rows = solve(0.35, 100, 0.35, 12, 30, 0.1)
        self.assertLess(max(abs(b - 12 / (1 + 0.0035 * 12 * t)) for t, b in rows), 1e-8)

    def test_limit_near_equal_rates(self):
        reference = analytic(30, 0.35, 100, 0.35, 12)
        for offset in (-1e-12, 1e-12):
            self.assertAlmostEqual(analytic(30, 0.35, 100, 0.35 + offset, 12), reference, places=9)

    def test_zero_biomass(self):
        for mortality in (0, 0.35, 0.7):
            self.assertEqual(analytic(30, 0.35, 100, mortality, 0), 0)
            self.assertTrue(all(b == 0 for _, b in solve(0.35, 100, mortality, 0, 30)))

    def test_zero_growth_is_exponential_decay(self):
        rows = solve(0, 100, 0.08, 12, 30)
        self.assertAlmostEqual(analytic(30, 0, 100, 0.08, 12), 12 * math.exp(-2.4), places=13)
        self.assertLess(max(abs(b - 12 * math.exp(-0.08 * t)) for t, b in rows), 1e-8)

    def test_both_rates_zero(self):
        self.assertEqual(analytic(30, 0, 100, 0, 12), 12)
        self.assertTrue(all(b == 12 for _, b in solve(0, 100, 0, 12, 30)))

    def test_mortality_above_growth(self):
        rows = solve(0.35, 100, 0.5, 12, 30)
        self.assertTrue(all(right[1] < left[1] for left, right in zip(rows, rows[1:])))
        self.assertLess(max(abs(b - analytic(t, 0.35, 100, 0.5, 12)) for t, b in rows), 1e-7)

    def test_positive_equilibrium(self):
        equilibrium = 100 * (1 - 0.08 / 0.35)
        rows = solve(0.35, 100, 0.08, equilibrium, 30)
        self.assertLess(max(abs(b - equilibrium) for _, b in rows), 1e-12)
        self.assertAlmostEqual(analytic(30, 0.35, 100, 0.08, equilibrium), equilibrium, places=12)

    def test_above_carrying_capacity(self):
        rows = solve(0.35, 100, 0.08, 150, 30, 0.05)
        self.assertTrue(all(right[1] <= left[1] for left, right in zip(rows, rows[1:])))
        self.assertLess(max(abs(b - analytic(t, 0.35, 100, 0.08, 150)) for t, b in rows), 1e-5)

    def test_zero_horizon(self):
        self.assertEqual(solve(0.35, 100, 0.08, 12, 0), [(0.0, 12.0)])

    def test_short_final_step_and_horizon_smaller_than_dt(self):
        for horizon, expected_size in ((0.25, 4), (0.03, 2)):
            rows = solve(0.35, 100, 0.08, 12, horizon)
            self.assertEqual(len(rows), expected_size)
            self.assertEqual(rows[-1][0], horizon)
            self.assertTrue(all(right[0] > left[0] for left, right in zip(rows, rows[1:])))
            self.assertLess(abs(rows[-1][1] - analytic(horizon, 0.35, 100, 0.08, 12)), 1e-7)

    def test_long_time_analytic_does_not_overflow(self):
        self.assertAlmostEqual(analytic(1e6, 0.35, 100, 0.08, 12), 100 * (1 - 0.08 / 0.35), places=12)

    def test_horizon_survives_floating_point_grid_rounding(self):
        rows = solve(0.35, 100, 0.08, 12, 0.9, 0.3)
        self.assertEqual(rows[-1][0], 0.9)
        self.assertEqual(len(rows), 4)

    def test_invalid_inputs(self):
        for field in ("r", "K", "d", "B0", "horizon", "dt"):
            for invalid in (-1, math.nan, math.inf):
                with self.subTest(field=field, invalid=invalid):
                    kwargs = dict(PARAMETERS, dt=0.1)
                    kwargs[field] = invalid
                    with self.assertRaises(ValueError):
                        solve(**kwargs)
        for field in ("K", "dt"):
            kwargs = dict(PARAMETERS, dt=0.1)
            kwargs[field] = 0
            with self.assertRaises(ValueError):
                solve(**kwargs)
        for invalid in (-1, math.nan, math.inf):
            with self.assertRaises(ValueError):
                analytic(invalid, 0.35, 100, 0.08, 12)

    def test_unsafe_step_fails_without_clipping(self):
        with self.assertRaises(ArithmeticError):
            solve(0, 100, 10, 12, 1, 1)

    def test_excessive_grid_is_rejected(self):
        with self.assertRaises(ValueError):
            solve(0.35, 100, 0.08, 12, 30, 1e-12)


if __name__ == "__main__":
    unittest.main()
