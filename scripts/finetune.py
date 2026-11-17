"""LoRA / full fine-tuning for Chronos-2 with strict train/val/test isolation.

Split per series:
  - train      = everything before the last 56 days
  - validation = 28 days before test ([-56:-28])
  - test       = last 28 days (NEVER touched unless --final is passed)

Run (validation mode):
  .venv\\Scripts\\python.exe scripts/finetune.py --steps 500 --lr 1e-5 --mode lora --tag lora-v1

Run (final test-set evaluation, once per tag):
  .venv\\Scripts\\python.exe scripts/finetune.py --final --checkpoint models/lora-v1 --tag lora-v1
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import numpy as np
import pandas as pd

from rdf import config
from rdf.data_loader import get_series, list_series, load_sales
from rdf.forecaster import load_pipeline

HORIZON = 28
REPORTS_DIR = ROOT / "reports"
MODELS_DIR = ROOT / "models"


def safe_wape(abs_err_sum: float, actual_sum: float) -> float:
    return float(abs_err_sum / actual_sum) if actual_sum > 0 else float("nan")


def evaluate_window(
    pipeline,
    series_map: dict[str, pd.DataFrame],
    start_offset: int,
    end_offset: int | None,
) -> tuple[dict[str, float], pd.DataFrame]:
    """Forecast 28 days starting at -start_offset up to -end_offset (None = end of series)."""
    ctx_frames: list[pd.DataFrame] = []
    actuals: dict[str, np.ndarray] = {}

    for sid, s in series_map.items():
        train_df = s.iloc[:-start_offset]
        target_slice = s.iloc[-start_offset:end_offset]
        actuals[sid] = target_slice["sales"].to_numpy(dtype=np.float64)
        ctx_frames.append(
            pd.DataFrame({
                "item_id": sid,
                "timestamp": train_df["date"].values,
                "target": train_df["sales"].values,
            })
        )

    out = pipeline.predict_df(
        pd.concat(ctx_frames, ignore_index=True),
        id_column="item_id",
        timestamp_column="timestamp",
        target="target",
        prediction_length=HORIZON,
        quantile_levels=config.QUANTILES,
        freq="D",
    )
    for col in ("predictions", "0.1", "0.5", "0.9"):
        out[col] = out[col].clip(lower=0)

    per_series = []
    all_act, all_mean, all_q50, all_q10, all_q90 = [], [], [], [], []
    for sid, grp in out.groupby("item_id", sort=True):
        grp = grp.sort_values("timestamp")
        act = actuals[sid]
        mean_p = grp["predictions"].to_numpy(dtype=np.float64)
        q50_p = grp["0.5"].to_numpy(dtype=np.float64)
        q10_p = grp["0.1"].to_numpy(dtype=np.float64)
        q90_p = grp["0.9"].to_numpy(dtype=np.float64)

        all_act.append(act)
        all_mean.append(mean_p)
        all_q50.append(q50_p)
        all_q10.append(q10_p)
        all_q90.append(q90_p)

        act_sum = float(np.nansum(act))
        per_series.append({
            "series_id": sid,
            "mean_mae": float(np.nanmean(np.abs(mean_p - act))),
            "mean_wape": safe_wape(float(np.nansum(np.abs(mean_p - act))), act_sum),
            "mean_bias": float(np.nanmean(mean_p - act)),
            "q50_mae": float(np.nanmean(np.abs(q50_p - act))),
            "q50_wape": safe_wape(float(np.nansum(np.abs(q50_p - act))), act_sum),
            "q50_bias": float(np.nanmean(q50_p - act)),
            "cov80": float(np.nanmean((act >= q10_p) & (act <= q90_p))),
        })

    a = np.concatenate(all_act)
    m = np.concatenate(all_mean)
    q = np.concatenate(all_q50)
    ql = np.concatenate(all_q10)
    qh = np.concatenate(all_q90)
    a_sum = float(np.nansum(a))

    overall = {
        "mean_mae": float(np.nanmean(np.abs(m - a))),
        "mean_wape": safe_wape(float(np.nansum(np.abs(m - a))), a_sum),
        "mean_bias": float(np.nanmean(m - a)),
        "q50_mae": float(np.nanmean(np.abs(q - a))),
        "q50_wape": safe_wape(float(np.nansum(np.abs(q - a))), a_sum),
        "q50_bias": float(np.nanmean(q - a)),
        "cov80": float(np.nanmean((a >= ql) & (a <= qh))),
    }
    return overall, pd.DataFrame(per_series)


def run_final(tag: str, checkpoint: Path) -> int:
    from chronos import Chronos2Pipeline

    final_csv = REPORTS_DIR / f"final_{tag}_metrics.csv"
    if final_csv.exists():
        print(f"Refusing to run --final twice for tag '{tag}': {final_csv} already exists.", file=sys.stderr)
        return 1
    if not checkpoint.exists():
        print(f"Checkpoint not found: {checkpoint}", file=sys.stderr)
        return 1

    t0 = time.perf_counter()
    sales = load_sales()
    series_map = {sid: get_series(sales, sid) for sid in list_series(sales)}

    zs_pipe, device = load_pipeline()
    ft_pipe = Chronos2Pipeline.from_pretrained(str(checkpoint), device_map=device)

    zs_overall, zs_series = evaluate_window(zs_pipe, series_map, HORIZON, None)
    ft_overall, ft_series = evaluate_window(ft_pipe, series_map, HORIZON, None)

    merged = zs_series.merge(ft_series, on="series_id", suffixes=("_zs", "_ft"))
    merged.to_csv(final_csv, index=False)

    improved_mae = int((merged["q50_mae_ft"] < merged["q50_mae_zs"]).sum())
    worsened_mae = int((merged["q50_mae_ft"] > merged["q50_mae_zs"]).sum())
    improved_wape = int((merged["q50_wape_ft"] < merged["q50_wape_zs"]).sum())
    worsened_wape = int((merged["q50_wape_ft"] > merged["q50_wape_zs"]).sum())

    print(f"\nFINAL TEST WINDOW EVALUATION (tag={tag}, device={device}, {time.perf_counter() - t0:.1f}s)")
    print(f"  Zero-Shot (mean): MAE={zs_overall['mean_mae']:.3f} | WAPE={zs_overall['mean_wape']:.1%} | Bias={zs_overall['mean_bias']:+.3f} | Cov80={zs_overall['cov80']:.1%}")
    print(f"  Fine-Tune (mean): MAE={ft_overall['mean_mae']:.3f} | WAPE={ft_overall['mean_wape']:.1%} | Bias={ft_overall['mean_bias']:+.3f} | Cov80={ft_overall['cov80']:.1%}")
    print(f"  Zero-Shot (q50):  MAE={zs_overall['q50_mae']:.3f} | WAPE={zs_overall['q50_wape']:.1%} | Bias={zs_overall['q50_bias']:+.3f}")
    print(f"  Fine-Tune (q50):  MAE={ft_overall['q50_mae']:.3f} | WAPE={ft_overall['q50_wape']:.1%} | Bias={ft_overall['q50_bias']:+.3f}")
    print(f"  Per-series (q50 MAE):  {improved_mae} improved, {worsened_mae} worsened (of {len(merged)})")
    print(f"  Per-series (q50 WAPE): {improved_wape} improved, {worsened_wape} worsened (of {len(merged)})")
    return 0


def run_train(args: argparse.Namespace) -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    tag = args.tag or f"{args.mode}-s{args.steps}-lr{args.lr:.0e}"
    ckpt_dir = MODELS_DIR / tag

    t_start = time.perf_counter()
    sales = load_sales()
    series_map = {sid: get_series(sales, sid) for sid in list_series(sales)}

    train_inputs = [{"target": s.iloc[:-56]["sales"].to_numpy(dtype=np.float32)} for s in series_map.values()]
    val_inputs = [{"target": s.iloc[:-28]["sales"].to_numpy(dtype=np.float32)} for s in series_map.values()]

    pipeline, device = load_pipeline()
    print(
        f"Fine-tuning on [{device}]: tag={tag}, mode={args.mode}, steps={args.steps}, "
        f"lr={args.lr}, batch_size={args.batch_size}, context_length={args.context_length}"
    )

    t_train = time.perf_counter()
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"chronos2-{tag}-"))
    try:
        finetuned = pipeline.fit(
            inputs=train_inputs,
            prediction_length=HORIZON,
            validation_inputs=val_inputs,
            finetune_mode=args.mode,
            learning_rate=args.lr,
            num_steps=args.steps,
            batch_size=args.batch_size,
            context_length=args.context_length,
            output_dir=tmp_dir,
        )
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        finetuned.save_pretrained(ckpt_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    train_sec = time.perf_counter() - t_train

    t_eval = time.perf_counter()
    val_overall, _ = evaluate_window(finetuned, series_map, 56, -28)
    eval_sec = time.perf_counter() - t_eval
    total_min = (time.perf_counter() - t_start) / 60.0

    row = pd.DataFrame([{
        "tag": tag,
        "steps": args.steps,
        "lr": args.lr,
        "mode": args.mode,
        "context_length": args.context_length,
        "val_mean_wape": val_overall["mean_wape"],
        "val_mean_mae": val_overall["mean_mae"],
        "val_mean_bias": val_overall["mean_bias"],
        "val_q50_wape": val_overall["q50_wape"],
        "val_q50_mae": val_overall["q50_mae"],
        "val_q50_bias": val_overall["q50_bias"],
        "val_cov80": val_overall["cov80"],
        "minutes": round(total_min, 2),
    }])
    runs_csv = REPORTS_DIR / "finetune_runs.csv"
    row.to_csv(runs_csv, mode="a", header=not runs_csv.exists(), index=False)

    print(f"\nValidation results (tag={tag}):")
    print(f"  Mean: MAE={val_overall['mean_mae']:.3f} | WAPE={val_overall['mean_wape']:.1%} | Bias={val_overall['mean_bias']:+.3f} | Cov80={val_overall['cov80']:.1%}")
    print(f"  Q50:  MAE={val_overall['q50_mae']:.3f} | WAPE={val_overall['q50_wape']:.1%} | Bias={val_overall['q50_bias']:+.3f}")
    print(f"Timing: train={train_sec:.1f}s | val_eval={eval_sec:.1f}s | total={total_min:.2f}m | saved={ckpt_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fine-tune Chronos-2 on train split only.")
    p.add_argument("--steps", type=int, default=500)
    p.add_argument("--lr", type=float, default=1e-5)
    p.add_argument("--mode", choices=["lora", "full"], default="lora")
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--context-length", type=int, default=None)
    p.add_argument("--tag", type=str, default="")
    p.add_argument("--final", action="store_true")
    p.add_argument("--checkpoint", type=str, default="")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.final:
        tag = args.tag or Path(args.checkpoint).name
        if not tag:
            print("Provide --tag or --checkpoint with --final.", file=sys.stderr)
            return 1
        ckpt = Path(args.checkpoint) if args.checkpoint else MODELS_DIR / tag
        return run_final(tag, ckpt)
    return run_train(args)


if __name__ == "__main__":
    raise SystemExit(main())
