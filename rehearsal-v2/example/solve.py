"""Closed-form solver for an explicitly synthetic convex allocation example."""
import argparse
import hashlib
import json
from pathlib import Path


def solve_case(demand, a, b):
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in (demand, a, b)):
        raise ValueError("Demand and coefficients must be positive finite numbers")
    import math
    if not all(math.isfinite(v) for v in (demand, a, b)):
        raise ValueError("Demand and coefficients must be finite")
    x, y = b * demand / (a + b), a * demand / (a + b)
    cost = a * x * x + b * y * y
    baseline = (a + b) * (demand / 2) ** 2
    return {"demand": demand, "x": x, "y": y, "cost": cost,
            "baseline_cost": baseline, "saving_pct": 100 * (baseline - cost) / baseline,
            "constraint_residual": abs(x + y - demand)}


def solve(input_path, output_path):
    input_path, output_path = Path(input_path), Path(output_path)
    data = json.loads(input_path.read_text(encoding="utf-8-sig"))
    if data.get("synthetic") is not True:
        raise ValueError("Example solver accepts only explicitly synthetic input")
    a, b = data["cost_x"], data["cost_y"]
    result = {"format_version": 1, "synthetic": True, "author_agent_id": "demo-solver",
              "model_id": "synthetic-convex-allocation-v1", "model": "min a*x^2+b*y^2, x+y=T, x,y>=0",
              "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
              "solver_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "parameters": {"a": a, "b": b}, "units": data["units"],
              "solution": solve_case(data["demand"], a, b),
              "sensitivity": [solve_case(t, a, b) for t in data["demand_scenarios"]]}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    solve(args.input, args.output)
