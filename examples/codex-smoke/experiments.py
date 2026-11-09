"""Reproducible synthetic experiments; figures consume hash-verified frozen CSVs.

Run once: python -B examples/codex-smoke/experiments.py
Existing output directories are rejected. No randomness or external API is used.
The installed nature-figure QA scripts are optional reproducibility dependencies;
pass --qa-scripts to enable their alignment, glyph-size and collision gates.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from solver import analytic, solve


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DEFAULT_STYLE = REPO / "bundle/src/figure-style.json"
TRAJECTORY_FIELDS = ["synthetic", "run_id", "run_kind", "r", "K", "d", "B0", "horizon", "dt", "t", "biomass", "analytic_biomass", "signed_error", "absolute_error"]
SCENARIO_FIELDS = ["synthetic", "scenario_id", "r", "K", "d", "B0", "horizon", "dt", "final_biomass", "analytic_final_biomass", "max_absolute_error", "delta_from_baseline", "row_count"]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def write_csv(path, fields, rows):
    with Path(path).open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def check_inputs():
    contract = json.loads((HERE / "model-contract.json").read_text(encoding="utf-8"))
    handoff = json.loads((HERE / "solver-handoff.json").read_text(encoding="utf-8"))
    for filename, key in [("model-contract.json", "contract_sha256"), ("solver.py", "solver_sha256")]:
        if sha256(HERE / filename) != handoff[key]:
            raise ValueError(f"P1 handoff hash mismatch: {filename}")
    if contract["synthetic"] is not True or handoff["synthetic"] is not True:
        raise ValueError("This runner accepts only the frozen synthetic rehearsal")
    return contract


def run_rows(run_id, kind, parameters, dt):
    trajectory = solve(**parameters, dt=dt)
    result = []
    for t, biomass in trajectory:
        exact = analytic(t, **{k: parameters[k] for k in ("r", "K", "d", "B0")})
        result.append(dict(synthetic="true", run_id=run_id, run_kind=kind,
                           **parameters, dt=dt, t=t, biomass=biomass,
                           analytic_biomass=exact, signed_error=biomass-exact,
                           absolute_error=abs(biomass-exact)))
    return result


def create_data(output, style=DEFAULT_STYLE):
    """Execute the contract, freeze numeric tables, then hash the exact bytes."""
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing frozen output: {output}")
    contract = check_inputs()
    style = Path(style)
    json.loads(style.read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=False)
    params = contract["parameters"]
    baseline = run_rows("baseline", "baseline", params, 0.1)
    trajectories = list(baseline)
    refinements = []
    for dt in (0.2, 0.1, 0.05):
        rows = baseline if dt == 0.1 else run_rows(f"baseline_dt_{dt:g}", "convergence", params, dt)
        if dt != 0.1:
            trajectories.extend(rows)
        refinements.append(dict(synthetic="true", dt=dt, row_count=len(rows),
                                max_absolute_error=max(row["absolute_error"] for row in rows),
                                final_biomass=rows[-1]["biomass"], final_time=rows[-1]["t"]))
    scenarios, scenario_trajectories = [], []
    for r in contract["experiments"]["growth"]:
        for d in contract["experiments"]["mortality"]:
            scenario_id = f"r{r:.2f}_d{d:.2f}"
            p = dict(params, r=r, d=d)
            rows = run_rows(scenario_id, "scenario", p, 0.1)
            trajectories.extend(rows)
            scenario_trajectories.append(rows)
            scenarios.append(dict(synthetic="true", scenario_id=scenario_id, **p, dt=0.1,
                                  final_biomass=rows[-1]["biomass"],
                                  analytic_final_biomass=rows[-1]["analytic_biomass"],
                                  max_absolute_error=max(row["absolute_error"] for row in rows),
                                  delta_from_baseline=rows[-1]["biomass"]-baseline[-1]["biomass"],
                                  row_count=len(rows)))
    if any([row["t"] for row in rows] != [row["t"] for row in baseline] for rows in scenario_trajectories):
        raise AssertionError("Scenario time grids must match exactly")
    envelope = []
    for index, base in enumerate(baseline):
        at_time = [rows[index] for rows in scenario_trajectories]
        low = min(at_time, key=lambda row: row["biomass"])
        high = max(at_time, key=lambda row: row["biomass"])
        envelope.append(dict(synthetic="true", t=base["t"], baseline_biomass=base["biomass"],
                             minimum_biomass=low["biomass"], maximum_biomass=high["biomass"],
                             minimum_scenario=low["run_id"], maximum_scenario=high["run_id"],
                             scenario_count=9, interval_type="parameter_envelope_not_confidence_interval"))

    equal = run_rows("equal_rates", "boundary_check", dict(params, d=params["r"]), 0.1)
    zero = run_rows("zero_biomass", "boundary_check", dict(params, B0=0.0), 0.1)
    errors = [row["max_absolute_error"] for row in refinements]
    ratios = [errors[index]/errors[index+1] for index in range(2)]
    checks = {
        "initial_condition": all(rows[0]["biomass"] == rows[0]["B0"] for rows in [baseline, *scenario_trajectories, equal, zero]),
        "finite_nonnegative": all(math.isfinite(row["biomass"]) and row["biomass"] >= 0 for row in trajectories + equal + zero),
        "exact_horizon": all(rows[-1]["t"] == params["horizon"] for rows in [baseline, *scenario_trajectories, equal, zero]),
        "equal_rates_limit": max(row["absolute_error"] for row in equal) < 0.001,
        "zero_initial_remains_zero": all(row["biomass"] == 0 for row in zero),
        "default_error_below_threshold": errors[1] < 0.001,
        "all_scenario_errors_below_threshold": all(row["max_absolute_error"] < 0.001 for row in scenarios),
        "dt_refinement": errors[0] > errors[1] > errors[2],
        "fourth_order_ratio": all(14 < ratio < 18 for ratio in ratios),
        "nine_fixed_scenarios": len(scenarios) == 9,
    }
    validation = dict(format_version=1, synthetic=True, checks=checks, passed=all(checks.values()),
                      acceptance_absolute_error=0.001, convergence=refinements,
                      step_halving_error_ratios=ratios,
                      boundary_checks={"equal_rates_max_absolute_error": max(row["absolute_error"] for row in equal),
                                       "zero_initial_rows": len(zero)},
                      scenario_count=9, trajectory_row_count=len(trajectories),
                      independent_review="pending; these are author-run computational checks")
    if not validation["passed"]:
        raise AssertionError(json.dumps(validation, indent=2))
    write_csv(output / "trajectories.csv", TRAJECTORY_FIELDS, trajectories)
    write_csv(output / "scenarios.csv", SCENARIO_FIELDS, scenarios)
    write_csv(output / "convergence.csv", list(refinements[0]), refinements)
    write_csv(output / "envelope.csv", list(envelope[0]), envelope)
    write_json(output / "validation.json", validation)
    # The manuscript macros are also sourced from the frozen CSV bytes.
    frozen_base = [row for row in read_csv(output / "trajectories.csv") if row["run_id"] == "baseline"]
    frozen_scenarios = read_csv(output / "scenarios.csv")
    frozen_errors = [float(row["max_absolute_error"]) for row in read_csv(output / "convergence.csv")]
    mantissa, exponent = f"{max(float(row['absolute_error']) for row in frozen_base):.2e}".split("e")
    macros = {"BaselineBiomass": f"{float(frozen_base[-1]['biomass']):.6f}",
              "SolverError": rf"{mantissa}\times 10^{{{int(exponent)}}}",
              "FirstErrorRatio": f"{frozen_errors[0] / frozen_errors[1]:.2f}",
              "SecondErrorRatio": f"{frozen_errors[1] / frozen_errors[2]:.2f}",
              "MinimumBiomass": f"{min(float(row['final_biomass']) for row in frozen_scenarios):.6f}",
              "MaximumBiomass": f"{max(float(row['final_biomass']) for row in frozen_scenarios):.6f}"}
    with (output / "numbers.tex").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("% synthetic=true; biomass extrema are final-time values across nine fixed scenarios.\n")
        for name, value in macros.items():
            stream.write("\\newcommand{\\" + name + "}{" + value + "}\n")
    sources = {name: sha256(HERE / name) for name in ["model-contract.json", "solver.py", "solver-handoff.json", "experiments.py"]}
    files = {path.name: {"sha256": sha256(path), "bytes": path.stat().st_size} for path in sorted(output.iterdir())}
    manifest = dict(format_version=1, synthetic=True, created_at_utc=datetime.now(timezone.utc).isoformat(),
                    inputs=sources, figure_style={"path": "bundle/src/figure-style.json", "sha256": sha256(style)},
                    data_files=files, parameters=params, scenario_grid=contract["experiments"],
                    runtime={"python": platform.python_version(), "platform": platform.system()},
                    deterministic=True, randomness="none", missing_values=0, exclusions=0,
                    unit_definitions={"time": contract["time_unit"], "biomass": contract["biomass_unit"]},
                    macro_definitions={"BaselineBiomass": "baseline B(30), dt=0.1",
                                       "SolverError": "maximum absolute baseline error over t=0..30, dt=0.1",
                                       "FirstErrorRatio": "maximum error at dt=0.2 divided by maximum error at dt=0.1",
                                       "SecondErrorRatio": "maximum error at dt=0.1 divided by maximum error at dt=0.05",
                                       "MinimumBiomass": "minimum final-time biomass across nine scenarios",
                                       "MaximumBiomass": "maximum final-time biomass across nine scenarios"},
                    scope="Synthetic workflow rehearsal only; no ecological calibration or scientific approval")
    write_json(output / "data-manifest.json", manifest)
    return manifest


def load_frozen(output):
    """Verify all frozen bytes before any figure reads a result table."""
    output = Path(output)
    manifest = json.loads((output / "data-manifest.json").read_text(encoding="utf-8"))
    if manifest["synthetic"] is not True:
        raise ValueError("Expected explicitly synthetic frozen data")
    for name, item in manifest["data_files"].items():
        if sha256(output / name) != item["sha256"]:
            raise ValueError(f"Frozen data hash mismatch: {name}")
    return manifest, {name: read_csv(output / name) for name in ("trajectories.csv", "scenarios.csv", "convergence.csv", "envelope.csv")}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def render_figures(output, style=DEFAULT_STYLE, qa_scripts=None, figure_dir=None):
    """Plot only frozen tables. This function never calls solve() or analytic()."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
    from matplotlib.ticker import FixedLocator

    output = Path(output)
    manifest, tables = load_frozen(output)
    style = Path(style)
    if sha256(style) != manifest["figure_style"]["sha256"]:
        raise ValueError("Figure style no longer matches the frozen input")
    cfg = json.loads(style.read_text(encoding="utf-8"))
    dest = Path(figure_dir) if figure_dir else output / "figures"
    if dest.exists():
        raise FileExistsError(f"Refusing to overwrite existing figures: {dest}")
    dest.mkdir(parents=True, exist_ok=False)
    qa_scripts = Path(qa_scripts) if qa_scripts else None
    alignment = load_module("rehearsal_alignment", qa_scripts / "audit_panel_alignment.py") if qa_scripts else None
    visibility = load_module("rehearsal_visual_range", REPO / "project-template/scripts/visual_range.py")
    p = cfg["palette"]
    plt.rcParams.update({"font.family": cfg["font_family"], "font.size": cfg["body_font_pt"],
                         "axes.labelsize": cfg["axis_font_pt"], "xtick.labelsize": cfg["tick_font_pt"],
                         "ytick.labelsize": cfg["tick_font_pt"], "legend.fontsize": 12,
                         "svg.fonttype": "none", "pdf.fonttype": 42,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": p["neutral"], "axes.labelcolor": "#202630",
                         "xtick.color": "#202630", "ytick.color": "#202630",
                         "axes.linewidth": 0.8, "lines.linewidth": 2.1,
                         "legend.frameon": False, "savefig.facecolor": "white"})
    width = cfg["final_width_mm"] / 25.4
    baseline = [row for row in tables["trajectories.csv"] if row["run_id"] == "baseline"]
    runs = {}
    for row in tables["trajectories.csv"]:
        runs.setdefault(row["run_id"], []).append(row)
    def vector(rows, name):
        return [float(row[name]) for row in rows]
    def axis_style(ax):
        ax.set_axisbelow(True)
        ax.grid(axis="y", color=p["neutral"], alpha=0.17, linewidth=0.7)
        ax.tick_params(length=3.5)
    def visible(ax, rows, column, **kwargs):
        return visibility.require_visible_data(vector(rows, column), ax.get_ylim(), context=column, **kwargs)
    def x_visible(ax, rows, column="t"):
        return visibility.require_visible_data(vector(rows, column), ax.get_xlim(), context=column)
    records = {}
    def save(fig, name, caption, mapping, ranges, contract, exclude_axes=()):
        fig.canvas.draw()
        if alignment:
            align = alignment.require_matplotlib_panel_alignment(fig, json_out=dest / f"{name}.alignment.json",
                tolerance_pt=1.5, gutter_tolerance_pt=1.5, strict=True, exclude_axes=exclude_axes)
            alignment_status = align.get("verdict", align.get("status", "see report"))
        else:
            alignment_status = "not executed: installed QA scripts not supplied"
            write_json(dest / f"{name}.alignment.json", {"synthetic": True, "status": alignment_status})
        for extension in ("pdf", "svg", "png"):
            # Preserve the declared physical canvas; no tight cropping or rescaling.
            fig.savefig(dest / f"{name}.{extension}", dpi=cfg["raster_dpi"])
        qa = {"alignment": alignment_status}
        if qa_scripts:
            for key, command in {
                "text": [sys.executable, "-B", str(qa_scripts / "audit_pdf_text.py"), str(dest / f"{name}.pdf"), "--min-pt", "12", "--json"],
                "collision": [sys.executable, "-B", str(qa_scripts / "audit_figure_collisions.py"), str(dest / f"{name}.pdf"), "--json-out", str(dest / f"{name}.collision-audit.json")],
            }.items():
                result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
                qa[key] = {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
                if key == "text":
                    write_json(dest / f"{name}.text-audit.json", json.loads(result.stdout))
                if result.returncode:
                    raise RuntimeError(f"{name} {key} QA failed: {result.stdout} {result.stderr}")
        with (dest / f"{name}.caption.txt").open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(caption + "\n")
        figure_record = dict(synthetic=True, figure=name, caption=caption, contract=contract,
                             data_mapping=mapping, data_file_hashes={key: manifest["data_files"][key]["sha256"] for key in mapping},
                             width_mm=cfg["final_width_mm"], height_mm=float(fig.get_figheight()*25.4),
                             minimum_final_font_pt=12, png_dpi=cfg["raster_dpi"],
                             input_style_sha256=sha256(style),
                             no_interpolation=True, no_filtering="All rows in each declared panel population retained",
                             range_checks=ranges, automated_qa=qa, author_visual_review="pending actual PNG inspection",
                             independent_review="pending separate reviewer",
                             exports={ext: {"sha256": sha256(dest / f"{name}.{ext}")} for ext in ("pdf", "svg", "png")})
        write_json(dest / f"{name}.mapping.json", figure_record)
        records[name] = figure_record
        plt.close(fig)

    # Prediction recipe: response and numerical error have distinct roles.
    fig, axes = plt.subplots(2, 1, figsize=(width, 5.4), sharex=True, gridspec_kw={"height_ratios": [1.25, 1]})
    fig.subplots_adjust(left=0.17, right=0.97, top=0.83, bottom=0.13, hspace=0.49)
    ax, error_ax = axes
    time = vector(baseline, "t")
    ax.plot(time, vector(baseline, "biomass"), color=p["blue"], label="RK4, dt = 0.1")
    ax.plot(time, vector(baseline, "analytic_biomass"), color=p["neutral"], linestyle="--", linewidth=1.6, label="Analytic reference")
    ax.set_ylim(0, 86)
    ax.set_ylabel("Biomass (synthetic units)")
    ax.set_yticks([0, 20, 40, 60, 80])
    ax.text(0, 1.08, "a  Baseline response", transform=ax.transAxes, fontsize=14, fontweight="bold", va="bottom")
    fig.legend(*ax.get_legend_handles_labels(), loc="upper center", bbox_to_anchor=(0.54, 0.985), ncol=2, columnspacing=1.2)
    errors = vector(baseline, "signed_error")
    error_ax.plot(time, [value / 1e-8 for value in errors], color=p["blue"])
    error_ax.axhline(0, color=p["neutral"], linewidth=1, linestyle="--")
    error_ax.set_ylim(-3.4, 0.4)
    error_ax.set_yticks([-3, -2, -1, 0])
    error_ax.set_ylabel("RK4 − analytic\n(10⁻⁸ synthetic units)")
    error_ax.set_xlabel("Time (arbitrary units)")
    error_ax.text(0, 1.08, "b  Numerical error", transform=error_ax.transAxes, fontsize=14, fontweight="bold", va="bottom")
    for axis in axes:
        axis_style(axis)
        axis.set_xlim(-0.4, 30.4)
        axis.xaxis.set_major_locator(FixedLocator([0, 5, 10, 15, 20, 25, 30]))
    ranges = [visible(ax, baseline, "biomass"), visible(ax, baseline, "analytic_biomass"), x_visible(ax, baseline),
              visibility.require_visible_data([value/1e-8 for value in errors], error_ax.get_ylim(), context="signed_error / 1e-8"), x_visible(error_ax, baseline)]
    save(fig, "trajectory", "Synthetic baseline trajectory and numerical accuracy. (a) All 301 RK4 values (dt = 0.1) and their analytic references over 0–30 arbitrary time units are shown. The curves overlap at the displayed biomass scale. (b) Signed RK4 minus analytic error at the same points, scaled by 10⁻⁸ for readability. Parameters: r = 0.35, K = 100, d = 0.08, B0 = 12. These deterministic synthetic results have no observational or ecological calibration.",
         {"trajectories.csv": {"population": "run_id == baseline; all 301 rows", "a": ["t", "biomass", "analytic_biomass"], "b": ["t", "signed_error"], "transform": "b y = signed_error / 1e-8; no other transformations"}}, ranges,
         {"question": "Does RK4 reproduce the analytic synthetic baseline?", "claim": "Baseline response is resolved and default-grid numerical error is small.", "archetype": "quantitative grid", "recipe": "prediction", "panel_roles": {"a": "response", "b": "accuracy beyond apparent curve overlap"}})

    # Sensitivity recipe: retain all nine tested combinations; no interpolation.
    scenarios = tables["scenarios.csv"]
    growth = manifest["scenario_grid"]["growth"]
    mortality = manifest["scenario_grid"]["mortality"]
    grid = [[next(float(row["final_biomass"]) for row in scenarios if float(row["r"]) == r and float(row["d"]) == d) for d in mortality] for r in growth]
    fig = plt.figure(figsize=(width, 5.6))
    ax = fig.add_axes([0.16, 0.30, 0.69, 0.60])
    cax = fig.add_axes([0.19, 0.12, 0.63, 0.035])
    cmap = LinearSegmentedColormap.from_list("project_blue", ["#FFFFFF", p["blue"]])
    mesh = ax.imshow(grid, cmap=cmap, interpolation="none", origin="lower", vmin=50, vmax=95, aspect="auto")
    for i, row in enumerate(grid):
        for j, value in enumerate(row):
            ax.text(j, i, f"{value:.2f}", ha="center", va="center", fontsize=14,
                    color="white" if value >= 83 else "#202630", fontweight="bold")
    ax.add_patch(Rectangle((0.5, 0.5), 1, 1, fill=False, edgecolor=p["orange"], linewidth=2.3))
    ax.set_xticks(range(3), [f"{v:.2f}" for v in mortality])
    ax.set_yticks(range(3), [f"{v:.2f}" for v in growth])
    ax.set_xlabel("Loss d (per time unit)")
    ax.set_ylabel("Growth r (per time unit)")
    ax.tick_params(length=0, pad=7)
    ax.set_title("Final biomass at time 30", fontsize=14, pad=14, loc="left", fontweight="bold")
    for spine in ax.spines.values():
        spine.set_visible(False)
    colorbar = fig.colorbar(mesh, cax=cax, orientation="horizontal", ticks=[50, 65, 80, 95])
    colorbar.set_label("Biomass (synthetic units)", labelpad=6)
    ranges = [{"color_scale": [50, 95], "data_extent": [min(map(min, grid)), max(map(max, grid))], "all_nine_cells_visible": True,
               "no_interpolation": True, "passed": all(50 <= value <= 95 for row in grid for value in row)}]
    save(fig, "sensitivity", "Synthetic final-time response across all nine tested parameter combinations. Each cell displays B(30) from RK4 with dt = 0.1, K = 100 and B0 = 12; mortality varies by column and growth by row. The orange outline marks the baseline (r = 0.35, d = 0.08). Values are shown to two decimals and the shared sequential color scale spans 50–95 synthetic biomass units. Cells are discrete tested scenarios; no interpolation, confidence interval or global sensitivity claim is implied.",
         {"scenarios.csv": {"population": "all 9 rows", "rows": "r", "columns": "d", "cell_color_and_label": "final_biomass", "label_format": ".2f", "baseline_outline": "r=0.35, d=0.08"}}, ranges,
         {"question": "How does final biomass vary over the tested grid?", "claim": "All nine parameter outcomes remain directly comparable.", "archetype": "quantitative grid", "recipe": "sensitivity"}, exclude_axes=[cax])

    env = tables["envelope.csv"]
    fig, ax = plt.subplots(figsize=(width, 4.6))
    fig.subplots_adjust(left=0.16, right=0.97, bottom=0.17, top=0.78)
    ax.fill_between(vector(env, "t"), vector(env, "minimum_biomass"), vector(env, "maximum_biomass"), color=p["blue"], alpha=0.15, linewidth=0, label="Parameter envelope")
    for index, rows in enumerate([runs[row["scenario_id"]] for row in scenarios]):
        ax.plot(vector(rows, "t"), vector(rows, "biomass"), color=p["neutral"], alpha=0.38, linewidth=0.8, linestyle="--", label="Nine scenarios" if index == 0 else None)
    ax.plot(vector(env, "t"), vector(env, "minimum_biomass"), color=p["blue"], linewidth=1.2, linestyle=":")
    ax.plot(vector(env, "t"), vector(env, "maximum_biomass"), color=p["blue"], linewidth=1.2, linestyle=":")
    ax.plot(vector(env, "t"), vector(env, "baseline_biomass"), color=p["blue"], label="Baseline", linewidth=2.4)
    ax.set_xlim(-0.4, 30.4)
    ax.set_ylim(0, 100)
    ax.set_xticks([0, 5, 10, 15, 20, 25, 30])
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.set_xlabel("Time (arbitrary units)")
    ax.set_ylabel("Biomass (synthetic units)")
    axis_style(ax)
    fig.legend(*ax.get_legend_handles_labels(), loc="upper left", bbox_to_anchor=(0.16, 0.99), labelspacing=0.35)
    ranges = [visible(ax, env, "baseline_biomass", lower=vector(env, "minimum_biomass"), upper=vector(env, "maximum_biomass")), x_visible(ax, env)]
    for row in scenarios:
        ranges.append(visible(ax, runs[row["scenario_id"]], "biomass"))
    save(fig, "envelope", "Synthetic parameter envelope over all nine fixed scenarios. The shaded band is the pointwise minimum and maximum of the nine RK4 trajectories on the common 301-point grid (dt = 0.1). Dashed gray lines show every scenario, dotted blue boundaries delimit the band, and the solid blue line is the baseline. Growth values are 0.28, 0.35 and 0.42; mortality values are 0.04, 0.08 and 0.12; K = 100 and B0 = 12 throughout. The envelope represents these discrete parameter choices only. It is not a confidence interval, prediction interval, or estimate of real-world uncertainty.",
         {"envelope.csv": {"population": "all 301 rows", "x": "t", "line": "baseline_biomass", "band": ["minimum_biomass", "maximum_biomass"]},
          "trajectories.csv": {"population": "all 2709 scenario rows; run_kind == scenario", "lines": ["t", "biomass"], "group": "run_id"}}, ranges,
         {"question": "How broad is the response across the fixed parameter set?", "claim": "The tested parameter range changes the trajectory; the band is not probabilistic uncertainty.", "archetype": "quantitative grid", "recipe": "sensitivity", "interval": "min/max of exactly nine scenarios, frozen before plotting"})

    fig, ax = plt.subplots(figsize=(width, 2.75))
    fig.subplots_adjust(left=0.03, right=0.97, top=0.98, bottom=0.03)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    def box(x, y, w, h, title, body, color):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.014",
                                   linewidth=1.2, edgecolor=color, facecolor="white", clip_on=False))
        ax.text(x+w/2, y+h*0.76, title, fontsize=13, fontweight="bold", ha="center", va="center", color=color)
        ax.text(x+w/2, y+h*0.31, body, fontsize=12, ha="center", va="center", linespacing=1.1)
    def arrow(start, end):
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=15, color=p["neutral"], linewidth=1.2, shrinkA=0, shrinkB=2))
    box(0.01, 0.60, 0.28, 0.34, "Synthetic inputs", "B0 = 12, K = 100\nT = 30, 9 rate pairs", p["neutral"])
    box(0.36, 0.60, 0.28, 0.34, "Growth and loss", "dB/dt = (r − d)B\n− (r/K)B²", p["blue"])
    box(0.71, 0.60, 0.28, 0.34, "RK4 trajectories", "Nine scenarios\nBaseline refinements", p["blue"])
    box(0.71, 0.08, 0.28, 0.34, "Analytic checks", "Grid errors\nBoundary cases", p["teal"])
    box(0.36, 0.08, 0.28, 0.34, "Frozen tables", "CSV values\nSHA-256 file hashes", p["neutral"])
    box(0.01, 0.08, 0.28, 0.34, "Plots and paper", "Figure exports\nManuscript numbers", p["blue"])
    for start, end in [((0.302, 0.77), (0.348, 0.77)), ((0.652, 0.77), (0.698, 0.77)),
                       ((0.85, 0.588), (0.85, 0.432)), ((0.698, 0.25), (0.652, 0.25)),
                       ((0.348, 0.25), (0.302, 0.25))]:
        arrow(start, end)
    save(fig, "workflow", "Synthetic experiment and evidence flow. The model contract defines density-limited growth and constant per-capita loss. RK4 trajectories are evaluated against an analytic reference, including the zero-biomass and equal-rate cases. The nine scenarios use dt = 0.1. The baseline refinement uses dt = 0.2, 0.1 and 0.05. Hashed CSVs supply the numeric inputs for the figures and manuscript.",
         {"scenarios.csv": {"population": "all 9 rows", "schematic_inputs": ["B0", "K", "r", "d", "horizon", "dt"]}, "convergence.csv": {"population": "all 3 rows", "step_sizes": "dt"}}, [],
         {"question": "How do model inputs become traceable evidence?", "claim": "The workflow separates computation, frozen tables and presentation.", "archetype": "schematic-led composite", "schematic_not_quantitative_evidence": True})
    write_json(dest / "figure-manifest.json", {"synthetic": True, "figures": {name: {"mapping_sha256": sha256(dest / f"{name}.mapping.json"), "exports": record["exports"]} for name, record in records.items()},
                                               "data_manifest_sha256": sha256(output / "data-manifest.json"), "plotting_source_sha256": sha256(__file__),
                                               "matplotlib_version": matplotlib.__version__, "independent_review": "pending"})
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "output")
    parser.add_argument("--style", type=Path, default=DEFAULT_STYLE)
    parser.add_argument("--qa-scripts", type=Path)
    parser.add_argument("--data-only", action="store_true")
    parser.add_argument("--figures-only", action="store_true", help="Read existing frozen data; never rerun the solver")
    parser.add_argument("--figure-dir", type=Path, help="New directory for figure-only revisions; never overwrites")
    args = parser.parse_args()
    if args.data_only and args.figures_only:
        parser.error("--data-only and --figures-only are mutually exclusive")
    if not args.figures_only:
        create_data(args.output, args.style)
    if not args.data_only:
        render_figures(args.output, args.style, args.qa_scripts, args.figure_dir)
    print(json.dumps({"synthetic": True, "output": str(args.output), "status": "complete", "independent_review": "pending"}))


if __name__ == "__main__":
    main()
