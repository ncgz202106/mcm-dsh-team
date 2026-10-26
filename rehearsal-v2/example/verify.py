"""Independent verifier: no import from solve.py, finite differences and grid search."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def verify(input_path, result_path, report_path=None):
    input_path, result_path = Path(input_path), Path(result_path)
    source = json.loads(input_path.read_text(encoding="utf-8-sig"))
    result = json.loads(result_path.read_text(encoding="utf-8-sig"))
    a, b = source["cost_x"], source["cost_y"]
    errors, residuals, grid_gaps = [], [], []
    cases = [result["solution"], *result["sensitivity"]]
    expected_demands = [source["demand"], *source["demand_scenarios"]]
    if len(cases) != len(expected_demands):
        errors.append("Sensitivity case count differs from the input")
    if result.get("input_sha256") != hashlib.sha256(input_path.read_bytes()).hexdigest():
        errors.append("Input digest mismatch")
    if result.get("solver_source_sha256") != hashlib.sha256(Path(__file__).with_name('solve.py').read_bytes()).hexdigest():
        errors.append("Solver source changed since the recorded run")
    for index, (row, demand) in enumerate(zip(cases, expected_demands)):
        numbers = [row[k] for k in ("demand", "x", "y", "cost", "baseline_cost", "saving_pct")]
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in numbers):
            errors.append(f"case {index}: non-finite/non-numeric output")
            continue
        x, y = row["x"], row["y"]
        cost = lambda point: a * point * point + b * (demand - point) ** 2
        feasibility = max(abs(x + y - demand), max(0.0, -x), max(0.0, -y), abs(row["demand"] - demand))
        recomputed = a * x * x + b * y * y
        baseline = (a + b) * demand * demand / 4
        saving = 100 * (baseline - recomputed) / baseline
        value_error = max(abs(row["cost"] - recomputed), abs(row["baseline_cost"] - baseline), abs(row["saving_pct"] - saving))
        step = max(1e-5, demand * 1e-5)
        numerical_gradient = (cost(x + step) - cost(x - step)) / (2 * step)
        # 12,001 candidate points independently recover the optimum for this tiny model.
        grid_best = min(cost(demand * k / 12000) for k in range(12001))
        gap = abs(recomputed - grid_best)
        grid_gaps.append(gap)
        residuals.append(max(feasibility, value_error, abs(numerical_gradient)))
        if feasibility > 1e-8 or value_error > 1e-8 or abs(numerical_gradient) > 1e-6 or gap > 1e-5:
            errors.append(f"case {index}: feasibility/value/optimality failure")
    report = {"format_version": 1, "synthetic": True, "status": "passed" if not errors else "failed",
              "verifier_agent_id": "demo-independent-verifier", "author_agent_id": result.get("author_agent_id"),
              "result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
              "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
              "verifier_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "methods": ["constraint recomputation", "objective and baseline recomputation", "central finite difference", "independent grid search"],
              "reproduction_passed": not errors, "max_verification_error": max(residuals, default=0),
              "max_grid_gap": max(grid_gaps, default=0), "errors": errors,
              "limitations": "Independent numerical verification of a synthetic convex example; not a real contest review."}
    if report_path:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("result", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = verify(args.input, args.result, args.report)
    print(json.dumps(report))
    raise SystemExit(0 if report["status"] == "passed" else 2)
