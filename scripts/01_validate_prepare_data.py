"""Data Validation and Preparation Entrypoint for Raphael (Phase 1).

Validates raw CSVs against schema and verified facts from Section 3 of prompt.md.
Saves canonical processed Parquet files to data/processed/ and generates
artifacts/data_validation_report.json.
"""
import argparse
import json
import random
import sys
from datetime import datetime
from pathlib import Path
import yaml

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.loader import load_raw_csvs, parse_and_clean_data, save_processed_parquets
from src.data.validator import (
    validate_schema_and_integrity,
    analyze_demand_properties,
    analyze_lead_time_properties,
    analyze_inventory_properties,
)
from src.utils.logger import setup_logger
from src.utils.progress import get_progress_bar, timed_block


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate and prepare Raphael datasets (Phase 1)."
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/raphael.yaml",
        help="Path to YAML configuration file (default: configs/raphael.yaml)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite of processed files",
    )
    return parser.parse_args()


def load_yaml_config(config_path: str) -> dict:
    """Load configuration dictionary from YAML file."""
    p = Path(config_path)
    if not p.exists():
        raise FileNotFoundError(f"Configuration file not found: {p.resolve()}")
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def set_seed(seed: int) -> None:
    """Set random seed for reproducibility."""
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass


def verify_against_section_3(
    schema_res: dict,
    demand_res: dict,
    lt_res: dict,
    inv_res: dict,
    expected_as_of: str,
) -> dict:
    """Compare observed statistics against every fact enumerated in Section 3 of prompt.md."""
    checks = []

    # 1. Pairs count & breakdown
    checks.append({
        "fact": "75 (material, area) pairs = 25 materials x 3 areas",
        "expected": "75 pairs, 25 materials, 3 areas",
        "observed": f"{schema_res['pair_count']} pairs, {schema_res['materials_count']} materials, {len(schema_res['areas'])} areas",
        "match": (schema_res["pair_count"] == 75 and schema_res["materials_count"] == 25 and len(schema_res["areas"]) == 3),
    })

    # 2. Rows per pair & date range in demand
    checks.append({
        "fact": "Demand: 1,913 daily rows per pair, 2011-01-29 to 2016-04-24, no gaps, no missing, no negatives",
        "expected": "1913 rows/pair, 2011-01-29 to 2016-04-24, no gaps, no neg",
        "observed": f"{demand_res['rows_per_pair_min']}-{demand_res['rows_per_pair_max']} rows/pair, {demand_res['min_date']} to {demand_res['max_date']}, gaps={demand_res['has_date_gaps']}",
        "match": (
            demand_res["all_exact_1913"]
            and demand_res["min_date"] == "2011-01-29"
            and demand_res["max_date"] == "2016-04-24"
            and not demand_res["has_date_gaps"]
        ),
    })

    # 3. Intermittency & zeros
    checks.append({
        "fact": "Demand is intermittent: about 26% zeros; 29 pairs > 30% zeros; 6 pairs > 50%; mean ~0.6-36 units/day",
        "expected": "~26% zeros, 29 pairs > 30%, 6 pairs > 50%, mean 0.6-36",
        "observed": f"{demand_res['overall_zero_share']*100:.1f}% zeros, {demand_res['pairs_over_30_pct_zeros']} pairs > 30%, {demand_res['pairs_over_50_pct_zeros']} pairs > 50%, mean range {demand_res['pair_mean_range']}",
        "match": (
            abs(demand_res["overall_zero_share"] - 0.26) <= 0.02
            and demand_res["pairs_over_30_pct_zeros"] == 29
            and demand_res["pairs_over_50_pct_zeros"] == 6
        ),
    })

    # 4. Promotion share and lift
    checks.append({
        "fact": "is_promotion has ~32.9% share for every pair and weak avg lift (~1.06, range ~0.93-1.43)",
        "expected": "~32.9% share, lift ~1.06 (range ~0.93-1.43)",
        "observed": f"{demand_res['promo_share_range'][0]*100:.1f}%-{demand_res['promo_share_range'][1]*100:.1f}% share, lift mean {demand_res['promo_lift_mean']} (range {demand_res['promo_lift_range']})",
        "match": (
            abs(demand_res["promo_share_range"][0] - 0.329) <= 0.01
            and abs(demand_res["promo_lift_mean"] - 1.06) <= 0.05
        ),
    })

    # 5. Lead time stats
    checks.append({
        "fact": "Lead time: 274 orders per pair, 2011-01-29 to 2016-04-23, mean ~5.2 days, corr with quantity ~0.89",
        "expected": "274 orders/pair, 2011-01-29 to 2016-04-23, mean ~5.2, corr ~0.89",
        "observed": f"{lt_res['orders_per_pair_min']}-{lt_res['orders_per_pair_max']} orders/pair, {lt_res['min_date']} to {lt_res['max_date']}, mean {lt_res['mean_lead_time']}, within-pair corr {lt_res['mean_within_pair_corr_quantity']}",
        "match": (
            lt_res["all_exact_274"]
            and lt_res["min_date"] == "2011-01-29"
            and lt_res["max_date"] == "2016-04-23"
            and abs(lt_res["mean_lead_time"] - 5.2) <= 0.2
            and abs(lt_res["mean_within_pair_corr_quantity"] - 0.89) <= 0.05
        ),
    })

    # 6. Lead time Nov-Dec and Area differences
    checks.append({
        "fact": "Lead time higher in Nov-Dec (+1.3 days), area means: CA ~4.2, TX ~5.2, WI ~6.3 days",
        "expected": "Nov-Dec delta +1.3 days, CA ~4.2, TX ~5.2, WI ~6.3",
        "observed": f"Nov-Dec delta +{lt_res['nov_dec_delta']} days, Area means: {lt_res['area_means']}",
        "match": (
            abs(lt_res["nov_dec_delta"] - 1.3) <= 0.3
            and abs(lt_res["area_means"].get("California - CA_1", 0) - 4.2) <= 0.3
            and abs(lt_res["area_means"].get("Texas - TX_1", 0) - 5.2) <= 0.3
            and abs(lt_res["area_means"].get("Wisconsin - WI_1", 0) - 6.3) <= 0.3
        ),
    })

    # 7. Inventory snapshot date
    checks.append({
        "fact": "Inventory snapshot stamped 2016-04-24, equals last demand date (as_of_date)",
        "expected": expected_as_of,
        "observed": str(inv_res["unique_last_updated"]),
        "match": inv_res["all_match_as_of"],
    })

    all_matched = all(c["match"] for c in checks)
    return {"all_matched": all_matched, "checks": checks}


def main():
    args = parse_args()
    logger = setup_logger("01_validate_prepare_data", log_dir="logs")
    set_seed(args.seed)

    logger.info("=" * 70)
    logger.info(" Raphael Phase 1: Data Validation & Preparation")
    logger.info("=" * 70)

    config = load_yaml_config(args.config)
    expected_as_of = config.get("dates", {}).get("as_of_date", "2016-04-24")
    raw_paths = config.get("paths", {}).get("raw_data", {})

    with timed_block("Data Loading and Schema Validation", logger=logger):
        # 1. Load CSVs
        logger.info("Loading 4 raw CSV files from data/raw/...")
        raw_map = {
            "demand": raw_paths.get("demand", "data/raw/demand_history.csv"),
            "lead_time": raw_paths.get("lead_time", "data/raw/lead_time_history.csv"),
            "inventory": raw_paths.get("inventory", "data/raw/current_inventory.csv"),
            "calendar_events": raw_paths.get("calendar_events", "data/raw/calendar_events_reference.csv"),
        }
        df_dem_raw, df_lt_raw, df_inv_raw, df_cal_raw = load_raw_csvs(raw_map)
        logger.info(f"Loaded: Demand ({len(df_dem_raw):,} rows), Lead Time ({len(df_lt_raw):,} rows), Inventory ({len(df_inv_raw):,} rows), Calendar ({len(df_cal_raw):,} rows)")

        # 2. Parse and Clean types
        logger.info("Cleaning dtypes and parsing dates...")
        df_demand, df_lead_time, df_inventory, df_calendar = parse_and_clean_data(
            df_dem_raw, df_lt_raw, df_inv_raw, df_cal_raw
        )

        # 3. Schema & Integrity Validation
        logger.info("Validating schema constraints, missing values, and pair alignments...")
        schema_res = validate_schema_and_integrity(
            df_demand, df_lead_time, df_inventory, df_calendar, config
        )
        if not schema_res["valid"]:
            logger.error("Schema validation failed:")
            for err in schema_res["errors"]:
                logger.error(f"  - {err}")
            sys.exit(1)
        logger.info("  [OK] Schema, dtypes, null-checks, and pair alignments passed!")

    with timed_block("Statistical Property Verification (Section 3)", logger=logger):
        # Progress bar over the validation analysis steps
        steps = [
            ("Analyzing demand properties and intermittency (ADI/CV^2)", lambda: analyze_demand_properties(df_demand, expected_as_of)),
            ("Analyzing lead-time properties and correlations", lambda: analyze_lead_time_properties(df_lead_time)),
            ("Analyzing inventory and computing Raphael stock cover", lambda: analyze_inventory_properties(df_inventory, df_demand, expected_as_of)),
        ]
        results = {}
        pbar = get_progress_bar(total=len(steps), desc="Verifying data statistics", unit="task")
        for desc, func in steps:
            pbar.set_description(desc)
            if "demand" in desc:
                results["demand"] = func()
            elif "lead-time" in desc:
                results["lead_time"] = func()
            else:
                results["inventory"] = func()
            pbar.update(1)
        pbar.close()

        # Detailed Section 3 comparison
        sec3_verification = verify_against_section_3(
            schema_res,
            results["demand"],
            results["lead_time"],
            results["inventory"],
            expected_as_of,
        )

    # Log Section 3 Fact Checks
    logger.info("\n" + "=" * 70)
    logger.info(" SECTION 3 FACTS RE-VERIFICATION REPORT")
    logger.info("=" * 70)
    for check in sec3_verification["checks"]:
        status = "[MATCH]" if check["match"] else "[MISMATCH / DIFFERENCE]"
        logger.info(f"{status} {check['fact']}")
        logger.info(f"   Expected: {check['expected']}")
        logger.info(f"   Observed: {check['observed']}")

    # Save to Parquet
    processed_dir = config.get("paths", {}).get("processed_data", {}).get("dir", "data/processed")
    logger.info(f"\nSaving validated datasets as Parquet to {processed_dir}...")
    saved_parquet_paths = save_processed_parquets(
        df_demand, df_lead_time, df_inventory, df_calendar, output_dir=processed_dir
    )
    for name, path in saved_parquet_paths.items():
        logger.info(f"  Saved {name:<12} -> {path}")

    # Build final report artifact
    report = {
        "timestamp": datetime.now().isoformat(),
        "seed": args.seed,
        "as_of_date": expected_as_of,
        "schema_summary": {
            "pair_count": schema_res["pair_count"],
            "materials_count": schema_res["materials_count"],
            "areas": schema_res["areas"],
        },
        "section_3_verification": sec3_verification,
        "demand_summary": {
            "total_rows": results["demand"]["total_rows"],
            "rows_per_pair": results["demand"]["rows_per_pair_min"],
            "date_range": [results["demand"]["min_date"], results["demand"]["max_date"]],
            "overall_zero_share": results["demand"]["overall_zero_share"],
            "pairs_over_30_pct_zeros": results["demand"]["pairs_over_30_pct_zeros"],
            "pairs_over_50_pct_zeros": results["demand"]["pairs_over_50_pct_zeros"],
            "pair_mean_range": results["demand"]["pair_mean_range"],
            "promo_share_range": results["demand"]["promo_share_range"],
            "promo_lift_mean": results["demand"]["promo_lift_mean"],
            "promo_lift_range": results["demand"]["promo_lift_range"],
            "category_counts": results["demand"]["category_counts"],
        },
        "lead_time_summary": {
            "total_orders": results["lead_time"]["total_orders"],
            "orders_per_pair": results["lead_time"]["orders_per_pair_min"],
            "date_range": [results["lead_time"]["min_date"], results["lead_time"]["max_date"]],
            "mean_lead_time": results["lead_time"]["mean_lead_time"],
            "mean_within_pair_corr_quantity": results["lead_time"]["mean_within_pair_corr_quantity"],
            "overall_corr_quantity": results["lead_time"]["overall_corr_quantity"],
            "nov_dec_delta": results["lead_time"]["nov_dec_delta"],
            "area_means": results["lead_time"]["area_means"],
        },
        "inventory_summary": {
            "last_updated": results["inventory"]["unique_last_updated"],
            "all_match_as_of": results["inventory"]["all_match_as_of"],
            "stock_stats": results["inventory"]["stock_stats"],
            "stock_cover_stats_days": results["inventory"]["stock_cover_stats"],
            "stock_cover_buckets": results["inventory"]["stock_cover_buckets"],
            "note": "stock_status_simulated was preserved for reference only and NEVER used in any calculations.",
        },
        "intermittency_per_pair": results["demand"]["intermittency_details"],
        "saved_parquets": saved_parquet_paths,
    }

    artifacts_dir = PROJECT_ROOT / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    report_file = artifacts_dir / "data_validation_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info(f"\nFull validation report saved to: {report_file}")
    if sec3_verification["all_matched"]:
        logger.info("\n>>> ALL SECTION 3 FACTS PERFECTLY VERIFIED. Phase 1 complete. <<<")
    else:
        logger.warning("\n>>> Data validation completed with differences noted above. <<<")


if __name__ == "__main__":
    main()
