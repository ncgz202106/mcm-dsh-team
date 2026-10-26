"""Publication-sized, deterministic synthetic demonstration; no empirical confidence bands."""
import json
from pathlib import Path


def plot(result_path, output_base):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    data = json.loads(Path(result_path).read_text(encoding="utf-8-sig"))
    if data.get("synthetic") is not True:
        raise ValueError("This plotting example is restricted to synthetic data")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12, "axes.labelsize": 12,
                         "axes.titlesize": 12, "legend.fontsize": 10, "pdf.fonttype": 42,
                         "svg.fonttype": "none", "svg.hashsalt": "mcm-synthetic-v1", "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.3), layout="constrained", gridspec_kw={"width_ratios": [1.4, 1]})
    rows, solution = data["sensitivity"], data["solution"]
    axes[0].plot([r["demand"] for r in rows], [r["cost"] for r in rows], "o-", color="#0072B2", label="Optimal allocation", markersize=4)
    axes[0].plot([r["demand"] for r in rows], [r["baseline_cost"] for r in rows], "s--", color="#D55E00", label="Equal allocation", markersize=4)
    axes[0].set(xlabel="Demand (resource units)", ylabel="Cost (synthetic units)", title="A  Demand sensitivity")
    axes[0].xaxis.set_major_locator(MaxNLocator(integer=True, nbins=5))
    axes[0].legend(frameon=False, loc="upper left")
    axes[0].grid(axis="y", color="0.9", linewidth=0.6)
    axes[1].bar(["Resource X", "Resource Y"], [solution["x"], solution["y"]], color=["#0072B2", "#E69F00"], width=0.6)
    axes[1].set(ylabel="Allocated resource units", title=f"B  Allocation at T={solution['demand']:g}", ylim=(0, solution["demand"]))
    for i, value in enumerate([solution["x"], solution["y"]]):
        axes[1].text(i, value + .3, f"{value:g}", ha="center", va="bottom")
    fig.suptitle("SYNTHETIC REHEARSAL — not observed contest data", fontsize=11)
    output_base = Path(output_base)
    output_base.parent.mkdir(parents=True, exist_ok=True)
    outputs = []
    for suffix in ("pdf", "png", "svg"):
        output = output_base.with_suffix("." + suffix)
        metadata={"Creator":"MCM synthetic rehearsal"}
        if suffix=='pdf':metadata.update(CreationDate=None,ModDate=None)
        if suffix=='svg':metadata['Date']=None
        fig.savefig(output, dpi=300, metadata=metadata)
        outputs.append(output)
    plt.close(fig)
    return outputs
