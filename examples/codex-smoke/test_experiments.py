"""Author tests for synthetic exports, integrity gates and scenario completeness."""

import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import experiments as exp


class ExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp.name) / "frozen"
        exp.create_data(cls.output)
        cls.manifest, cls.tables = exp.load_frozen(cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_complete_fixed_grid_and_finite_results(self):
        rows = self.tables["scenarios.csv"]
        self.assertEqual(len(rows), 9)
        self.assertEqual({(float(row["r"]), float(row["d"])) for row in rows},
                         {(r, d) for r in [0.28, 0.35, 0.42] for d in [0.04, 0.08, 0.12]})
        for row in rows:
            self.assertEqual(row["synthetic"], "true")
            self.assertEqual(int(row["row_count"]), 301)
            self.assertTrue(math.isfinite(float(row["final_biomass"])))
            self.assertGreaterEqual(float(row["final_biomass"]), 0)
            self.assertLess(float(row["max_absolute_error"]), 0.001)

    def test_trajectory_populations_and_baseline_duplicate_agree(self):
        trajectories = self.tables["trajectories.csv"]
        self.assertEqual(len(trajectories), 3762)
        base = [row for row in trajectories if row["run_id"] == "baseline"]
        scenario = [row for row in trajectories if row["run_id"] == "r0.35_d0.08"]
        self.assertEqual([(r["t"], r["biomass"]) for r in base], [(r["t"], r["biomass"]) for r in scenario])
        self.assertEqual(float(base[0]["biomass"]), 12)
        self.assertEqual(float(base[-1]["t"]), 30)

    def test_parameter_envelope_has_all_nine_scenarios(self):
        by_time = {}
        for row in self.tables["trajectories.csv"]:
            if row["run_kind"] == "scenario":
                by_time.setdefault(row["t"], []).append(float(row["biomass"]))
        for row in self.tables["envelope.csv"]:
            values = by_time[row["t"]]
            self.assertEqual(len(values), 9)
            self.assertEqual(float(row["minimum_biomass"]), min(values))
            self.assertEqual(float(row["maximum_biomass"]), max(values))
            self.assertIn(float(row["baseline_biomass"]), values)
            self.assertEqual(row["interval_type"], "parameter_envelope_not_confidence_interval")

    def test_refinement_and_boundary_checks(self):
        validation = json.loads((self.output / "validation.json").read_text())
        self.assertTrue(validation["passed"])
        self.assertTrue(all(validation["checks"].values()))
        self.assertEqual([row["row_count"] for row in validation["convergence"]], [151, 301, 601])
        for ratio in validation["step_halving_error_ratios"]:
            self.assertTrue(14 < ratio < 18)

    def test_macros_are_frozen_table_values(self):
        content = (self.output / "numbers.tex").read_text()
        base = [row for row in self.tables["trajectories.csv"] if row["run_id"] == "baseline"]
        self.assertIn("\\newcommand{\\BaselineBiomass}{" + f"{float(base[-1]['biomass']):.6f}" + "}", content)
        for name in ("SolverError", "MinimumBiomass", "MaximumBiomass"):
            self.assertIn("\\newcommand{\\" + name + "}", content)

    def test_existing_output_refused_without_changing_bytes(self):
        before = exp.sha256(self.output / "data-manifest.json")
        with self.assertRaises(FileExistsError):
            exp.create_data(self.output)
        self.assertEqual(before, exp.sha256(self.output / "data-manifest.json"))

    def test_hash_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            candidate = Path(temp) / "data"
            exp.create_data(candidate)
            with (candidate / "scenarios.csv").open("a") as stream:
                stream.write("tampered\n")
            with self.assertRaisesRegex(ValueError, "Frozen data hash mismatch"):
                exp.load_frozen(candidate)

    def test_all_input_hashes_match_current_frozen_contract(self):
        for filename, digest in self.manifest["inputs"].items():
            self.assertEqual(exp.sha256(exp.HERE / filename), digest)
        self.assertEqual(exp.sha256(exp.DEFAULT_STYLE), self.manifest["figure_style"]["sha256"])

    def test_figures_consume_tables_without_calling_solver(self):
        with tempfile.TemporaryDirectory() as temp:
            figures = Path(temp) / "figures"
            with patch.object(exp, "solve", side_effect=AssertionError("Unexpected solve during plotting")), \
                 patch.object(exp, "analytic", side_effect=AssertionError("Unexpected analytic evaluation during plotting")):
                records = exp.render_figures(self.output, figure_dir=figures)
            self.assertEqual(set(records), {"trajectory", "sensitivity", "envelope", "workflow"})
            for name in records:
                for extension in ("pdf", "svg", "png"):
                    self.assertTrue((figures / f"{name}.{extension}").is_file())
            with self.assertRaises(FileExistsError):
                exp.render_figures(self.output, figure_dir=figures)


if __name__ == "__main__":
    unittest.main()
