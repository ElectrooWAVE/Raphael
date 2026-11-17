"""Single LoRA fine-tune (lr=1e-5, steps=500) using best context_length + covariates.

Trains on train portion only ([:-56]), validates on [:-28], and compares against
the same setup without fine-tuning on the 5 rolling validation origins.
Never touches the final 28-day test window.

Run:  .venv\\Scripts\\python.exe scripts/finetune_best.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for p in (SRC, SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import numpy as np
import pandas as pd
from chronos.chronos2.preprocess import from_data_frame

from eval_covariates_best import (
    FUTURE_COV_COLS,
    HORIZON,
    load_best_config,
    load_series_with_covariates,
    run_validation_origins,
    safe_wape,
)
from rdf.forecaster import load_pipeline

MODELS_DIR = ROOT / "models"


def build_fit_dataframe(series_map: dict[str, pd.DataFrame], end_offset: int) -> pd.DataFrame:
    frames = []
    for sid, s in series_map.items():
        sub = s.iloc[:-end_offset]
        frames.append(
            pd.DataFrame({
                "item_id": sid,
                "timestamp": sub["date"].values,
                "target": sub["sales"].values,
                "is_promotion": sub["is_promotion"].values,
                **{col: sub[col].values for col in FUTURE_COV_COLS},
            })
        )
    return pd.concat(frames, ignore_index=True)


def main() -> int:
    ctx_len, cross_learning, cfg_name = load_best_config()
    print(f"Using best config: {cfg_name} (context_length={ctx_len}, cross_learning={cross_learning})")

    series_map = load_series_with_covariates()
    train_df = build_fit_dataframe(series_map, 56)
    val_df = build_fit_dataframe(series_map, 28)

    train_inputs = from_data_frame(
        train_df,
        target_columns=["target"],
        prediction_length=HORIZON,
        known_covariates_names=FUTURE_COV_COLS,
    )
    val_inputs = from_data_frame(
        val_df,
        target_columns=["target"],
        prediction_length=HORIZON,
        known_covariates_names=FUTURE_COV_COLS,
    )

    pipeline, device = load_pipeline()
    print(f"Running LoRA fine-tune on [{device}]: lr=1e-5, steps=500, batch_size=32, context_length={ctx_len}")

    t0 = time.perf_counter()
    tmp_dir = Path(tempfile.mkdtemp(prefix="chronos2-best-"))
    ckpt_dir = MODELS_DIR / "lora-cov-best"
    try:
        finetuned = pipeline.fit(
            inputs=train_inputs,
            prediction_length=HORIZON,
            validation_inputs=val_inputs,
            finetune_mode="lora",
            learning_rate=1e-5,
            num_steps=500,
            batch_size=32,
            context_length=ctx_len,
            output_dir=tmp_dir,
        )
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        finetuned.save_pretrained(ckpt_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    print(f"Training finished in {(time.perf_counter() - t0) / 60:.2f}m (saved to {ckpt_dir})")

    base_res = run_validation_origins(pipeline, series_map, ctx_len, cross_learning, use_covariates=True)
    ft_res = run_validation_origins(finetuned, series_map, ctx_len, cross_learning, use_covariates=True)

    act = base_res["actual"].to_numpy()
    act_sum = float(act.sum())
    base_med_wape = safe_wape(float(np.abs(base_res["median"].to_numpy() - act).sum()), act_sum)
    ft_med_wape = safe_wape(float(np.abs(ft_res["median"].to_numpy() - act).sum()), act_sum)
    base_exp_wape = safe_wape(float(np.abs(base_res["expected"].to_numpy() - act).sum()), act_sum)
    ft_exp_wape = safe_wape(float(np.abs(ft_res["expected"].to_numpy() - act).sum()), act_sum)

    rel_med = (base_med_wape - ft_med_wape) / base_med_wape if base_med_wape > 0 else 0.0
    rel_exp = (base_exp_wape - ft_exp_wape) / base_exp_wape if base_exp_wape > 0 else 0.0

    b_ser = base_res.groupby("series_id", sort=True).apply(
        lambda g: safe_wape(float(np.abs(g["median"] - g["actual"]).sum()), float(g["actual"].sum())),
        include_groups=False,
    )
    f_ser = ft_res.groupby("series_id", sort=True).apply(
        lambda g: safe_wape(float(np.abs(g["median"] - g["actual"]).sum()), float(g["actual"].sum())),
        include_groups=False,
    )
    improved = int((f_ser < b_ser).sum())
    worsened = int((f_ser > b_ser).sum())

    print("\nVALIDATION COMPARISON (same config + covariates, zero-shot vs LoRA fine-tune):")
    print(f"  Median WAPE:   {base_med_wape:.2%} -> {ft_med_wape:.2%} (diff={ft_med_wape - base_med_wape:+.2%}, rel_impr={rel_med:+.2%})")
    print(f"  Expected WAPE: {base_exp_wape:.2%} -> {ft_exp_wape:.2%} (diff={ft_exp_wape - base_exp_wape:+.2%}, rel_impr={rel_exp:+.2%})")
    print(f"  Per-series (median WAPE): {improved} improved, {worsened} worsened (of {len(b_ser)})")

    if max(rel_med, rel_exp) < 0.02:
        print("\nfine-tuning does not help")
    else:
        print("\nFine-tuning improved validation WAPE by >= 2% relative.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
