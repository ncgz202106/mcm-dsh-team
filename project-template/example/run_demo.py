#!/usr/bin/env python3
"""Run a small end-to-end rehearsal. Never records human approval or submits a PDF."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from solve import solve
from verify import verify
from plot import plot


def load_cli(project):
    spec = importlib.util.spec_from_file_location("local_mcm_cli", Path(project) / "scripts" / "mcm.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(project, force=False):
    project = Path(project).resolve()
    cli = load_cli(project)
    result_path = project / "results/demo/results.json"
    existing_artifacts = cli.records(project, "artifacts")
    if existing_artifacts and not all(a.get("synthetic") and a.get("artifact_id", "").startswith("DEMO_") for a in existing_artifacts):
        raise ValueError("Demo refuses projects containing non-demo artifacts; use a fresh template copy")
    if result_path.exists() and not force:
        raise ValueError("Demo outputs exist. Inspect them, then explicitly use --force to regenerate the synthetic rehearsal")
    source = project / "example/synthetic_input.json"
    for relative in ("results/demo/results.json", "results/demo/verification.json", "paper/generated/results.tex", "paper/generated/demo_table.tex",
                     "figures/demo_tradeoff.pdf", "figures/demo_tradeoff.png", "figures/demo_tradeoff.svg"):
        cli.resolve_inside(project, relative, protect_raw=True)
    result = solve(source, result_path)
    report_path = project / "results/demo/verification.json"
    verification = verify(source, result_path, report_path)
    if verification["status"] != "passed":
        raise ValueError("Independent verification failed; no figures or paper values released")
    figures = plot(result_path, project / "figures/demo_tradeoff")
    solution = result["solution"]
    macros = {"DemoDemand": solution["demand"], "DemoX": solution["x"], "DemoY": solution["y"], "DemoCost": solution["cost"],
              "DemoBaselineCost": solution["baseline_cost"], "DemoSavingPct": solution["saving_pct"],
              "DemoMaxVerificationError": verification["max_verification_error"], "DemoGridGap": verification["max_grid_gap"]}
    generated = project / "paper/generated"
    generated.mkdir(parents=True, exist_ok=True)
    (generated / "results.tex").write_text("% Generated from verified SYNTHETIC results; do not edit numeric values manually.\n" +
        "\n".join("\\newcommand{\\"+name+"}{"+format(value,'.3g' if name=='DemoSavingPct' else '.6g')+"}" for name, value in macros.items()) + "\n", encoding="utf-8")
    (generated / "demo_table.tex").write_text(
        "% Generated synthetic result table.\n\\begin{tabular}{lrrr}\n\\toprule\nScenario & $x$ & $y$ & Cost \\\\\n\\midrule\n" +
        "\n".join(f"$T={r['demand']:g}$ & {r['x']:.3f} & {r['y']:.3f} & {r['cost']:.3f} \\\\" for r in result["sensitivity"]) +
        "\n\\bottomrule\n\\end{tabular}\n", encoding="utf-8")
    def artifact(identity, kind, path, inputs=(), author="demo-solver", **extra):
        record = {"artifact_id": identity, "kind": kind, "path": Path(path).relative_to(project).as_posix(),
                  "version": 1, "status": "verified", "approval_state": "verified", "owner_role": "mcm-programmer",
                  "task_id": "DEMO_TASK", "inputs": list(inputs), "sha256": cli.file_hash(path),
                  "verification_status": "passed", "verified_by": "demo-independent-verifier", "author_agent_id": author,
                  "reproduced": True, "citations_verified": True, "citations_required": False, "synthetic": True}
        record.update(extra)
        return record
    def ref(row):
        return {k: row[k] for k in ("artifact_id", "version", "sha256")}
    input_row = artifact("DEMO_INPUT", "data", source, author="demo-input-generator", reproduction_required=False)
    code_rows=[artifact(identity,'code',path,author=author,reproduction_required=False) for identity,path,author in [
        ('DEMO_SOLVER_CODE',HERE/'solve.py','demo-solver-author'),
        ('DEMO_VERIFIER_CODE',HERE/'verify.py','demo-verifier-author'),
        ('DEMO_PLOT_CODE',HERE/'plot.py','demo-plot-author'),
        ('DEMO_EXPORT_CODE',HERE/'run_demo.py','demo-export-author')]]
    code_by_id={r['artifact_id']:r for r in code_rows}
    result_row = artifact("DEMO_RESULT", "result", result_path, [ref(input_row),ref(code_by_id['DEMO_SOLVER_CODE']),ref(code_by_id['DEMO_VERIFIER_CODE'])],
                          verification_report={"path": "results/demo/verification.json", "sha256": cli.file_hash(report_path)})
    all_rows = [input_row, *code_rows, result_row]
    for file in figures:
        all_rows.append(artifact("DEMO_FIGURE_" + file.suffix[1:].upper(), "figure", file, [ref(result_row),ref(code_by_id['DEMO_PLOT_CODE'])], author="demo-plotter", owner_role="mcm-figure"))
    for identity, file in (("DEMO_MACROS", generated / "results.tex"), ("DEMO_TABLE", generated / "demo_table.tex")):
        all_rows.append(artifact(identity, "table", file, [ref(result_row),ref(code_by_id['DEMO_EXPORT_CODE'])], author="demo-exporter", owner_role="mcm-paper-lead"))
    with cli.registry_lock(project):
        cli.save_records(project, "artifacts", all_rows)
        tasks = cli.records(project, "tasks")
        tasks = [t for t in tasks if t.get("task_id") != "DEMO_TASK"]
        tasks.append({"task_id": "DEMO_TASK", "parent_task_id": None, "title": "Synthetic rehearsal", "objective": "Verify the local handoff chain",
                      "owner_role": "mcm-programmer", "owner_agent_id": "demo-solver", "status": "in_review", "priority": "normal", "stage": "rehearsal",
                      "inputs": ["DEMO_INPUT"], "outputs": [r["artifact_id"] for r in all_rows if r["artifact_id"] != "DEMO_INPUT"],
                      "depends_on": [], "acceptance_criteria": ["Independent verifier passes", "No real human gate is approved"], "synthetic": True})
        cli.save_records(project, "tasks", tasks)
    validation = cli.validate_project(project, strict=True, allow_synthetic=True)
    if not validation["ok"]:
        raise ValueError("; ".join(validation["errors"]))
    return {"ok": True, "synthetic": True, "solution": solution, "independent_verification": verification["status"],
            "artifacts_registered": len(all_rows), "figure_formats": [p.suffix for p in figures],
            "human_gates_approved": False, "official_submission_created": False,
            "validation": validation, "next": "Build/check the synthetic paper using scripts/paper.py; all contest gates remain pending"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=HERE.parent)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.project, args.force), indent=2, allow_nan=False))
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
