"""Environment and Dependency Verification Script for Raphael.

Verifies:
- Python version and core runtime parameters
- System resources (CPU cores, RAM, free disk space)
- GPU / CUDA availability (informational)
- Core package versions
- US holiday calendar availability via `holidays`
- Prophet model instantiation and toy fit (crucial for Windows cmdstanpy toolchains)
"""
import argparse
import importlib
import json
import os
import platform
import random
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to sys.path so src modules can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.logger import setup_logger
from src.utils.progress import timed_block


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments with YAML config and seed support."""
    parser = argparse.ArgumentParser(
        description="Verify system environment, dependencies, and Prophet setup for Raphael."
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
        help="Random seed for reproducibility (default: 42)",
    )
    return parser.parse_args()


def set_seed(seed: int) -> None:
    """Set global seeds for reproducibility."""
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass


def check_hardware(logger) -> dict:
    """Check and log host system resources (CPU, RAM, Disk)."""
    hw_info = {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "python": sys.version.split()[0],
        "architecture": platform.machine(),
    }
    logger.info(f"OS: {hw_info['os']} [{hw_info['architecture']}]")
    logger.info(f"Python: {hw_info['python']} ({sys.executable})")

    # CPU
    cpu_count_logical = os.cpu_count() or 1
    hw_info["cpu_logical"] = cpu_count_logical
    try:
        import psutil
        cpu_count_physical = psutil.cpu_count(logical=False)
        ram = psutil.virtual_memory()
        hw_info["cpu_physical"] = cpu_count_physical
        hw_info["ram_total_gb"] = round(ram.total / (1024**3), 2)
        hw_info["ram_available_gb"] = round(ram.available / (1024**3), 2)
        logger.info(f"CPU Cores: {cpu_count_physical} physical, {cpu_count_logical} logical")
        logger.info(f"RAM: {hw_info['ram_total_gb']} GB total ({hw_info['ram_available_gb']} GB available)")
    except ImportError:
        logger.info(f"CPU Cores: {cpu_count_logical} logical (psutil not installed for RAM stats)")

    # Disk
    total, used, free = shutil.disk_usage(PROJECT_ROOT)
    hw_info["disk_free_gb"] = round(free / (1024**3), 2)
    logger.info(f"Disk Free Space: {hw_info['disk_free_gb']} GB on {PROJECT_ROOT.anchor}")

    # CUDA / GPU (Informational)
    gpu_found = False
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram_gb = round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 2)
            hw_info["gpu"] = f"{gpu_name} ({vram_gb} GB VRAM)"
            logger.info(f"GPU Detected: {hw_info['gpu']} (CUDA available)")
            gpu_found = True
        else:
            hw_info["gpu"] = "None (torch detected, CUDA not active)"
    except ImportError:
        hw_info["gpu"] = "PyTorch not installed in this environment"

    if not gpu_found:
        logger.info("GPU status: CPU fallback active (Prophet and Random Forest run on CPU by design).")

    return hw_info


def check_packages(logger) -> dict:
    """Check required packages and report versions."""
    required = [
        "pandas",
        "pyarrow",
        "numpy",
        "scipy",
        "sklearn",
        "prophet",
        "holidays",
        "joblib",
        "yaml",
        "tqdm",
        "fastapi",
        "uvicorn",
        "pydantic",
    ]
    pkg_versions = {}
    missing = []

    for pkg in required:
        try:
            mod = importlib.import_module(pkg)
            version = getattr(mod, "__version__", "installed")
            pkg_versions[pkg] = str(version)
            logger.info(f"  [OK] {pkg:<15} : {version}")
        except ImportError:
            missing.append(pkg)
            logger.error(f"  [FAIL] {pkg:<15} : NOT INSTALLED")

    if missing:
        logger.error(f"Missing required packages: {missing}")
        logger.error("Run: pip install -r requirements.txt")
        return {"status": "fail", "missing": missing, "installed": pkg_versions}

    return {"status": "pass", "installed": pkg_versions}


def check_holidays(logger) -> bool:
    """Verify US holiday calendar availability via holidays package."""
    try:
        import holidays
        us_holidays = holidays.country_holidays("US", years=[2015, 2016])
        sample_count = len(us_holidays)
        test_date = datetime(2016, 1, 1).date()
        is_new_year = test_date in us_holidays
        logger.info(f"US Holidays Check: {sample_count} holidays detected for 2015-2016. (2016-01-01 -> '{us_holidays.get(test_date)}')")
        if not is_new_year:
            logger.warning("US holidays did not find expected New Year's Day. Check holidays package configuration.")
            return False
        return True
    except Exception as e:
        logger.error(f"US Holidays Check Failed: {e}")
        return False


def check_prophet_toy_fit(logger) -> bool:
    """Perform a toy Prophet fit to ensure CmdStan/Stan toolchain works on Windows."""
    logger.info("Testing Prophet initialization and toy fit...")
    try:
        import pandas as pd
        import numpy as np
        from prophet import Prophet

        # Suppress verbose cmdstanpy logs during check
        import logging as py_logging
        py_logging.getLogger("cmdstanpy").setLevel(py_logging.WARNING)

        # Generate a small 30-day toy series
        dates = [datetime(2016, 1, 1) + timedelta(days=i) for i in range(30)]
        values = [10.0 + 2.0 * np.sin(i / 3.0) + (i % 7) for i in range(30)]
        df_toy = pd.DataFrame({"ds": dates, "y": values})

        model = Prophet(
            yearly_seasonality=False,
            weekly_seasonality=True,
            daily_seasonality=False,
        )
        model.fit(df_toy)

        future = model.make_future_dataframe(periods=1)
        forecast = model.predict(future)

        if len(forecast) == 31 and "yhat" in forecast.columns:
            logger.info("  [OK] Prophet toy fit completed successfully! Stan toolchain is operational.")
            return True
        else:
            logger.error("  [FAIL] Prophet forecast dataframe incomplete.")
            return False

    except Exception as e:
        logger.error(f"  [FAIL] Prophet toy fit failed: {e}")
        logger.error("\n" + "=" * 70)
        logger.error("PROPHET ON WINDOWS TROUBLESHOOTING:")
        logger.error("Prophet requires a functioning C++ compiler and CmdStan backend.")
        logger.error("Recommended resolution steps:")
        logger.error("  1. In your activated Python venv, run:")
        logger.error("     python -m cmdstanpy.install_cmdstan")
        logger.error("  2. If C++ toolchain is missing, install RTools or Visual Studio C++ Build Tools,")
        logger.error("     or install via conda: conda install -c conda-forge prophet")
        logger.error("  3. Verify cmdstanpy toolchain with: python -c \"import cmdstanpy; print(cmdstanpy.cmdstan_path())\"")
        logger.error("=" * 70 + "\n")
        return False


def main():
    args = parse_args()
    logger = setup_logger("00_check_env", log_dir="logs")
    set_seed(args.seed)

    logger.info("=" * 60)
    logger.info(" Raphael Phase 0: Environment & Toolchain Verification")
    logger.info("=" * 60)

    all_passed = True
    report = {
        "timestamp": datetime.now().isoformat(),
        "seed": args.seed,
        "config_path": args.config,
    }

    with timed_block("Environment Verification", logger=logger):
        # 1. Hardware & OS
        logger.info("\n--- 1. Hardware & System Resources ---")
        report["hardware"] = check_hardware(logger)

        # 2. Package Versions
        logger.info("\n--- 2. Python Packages ---")
        pkg_res = check_packages(logger)
        report["packages"] = pkg_res
        if pkg_res.get("status") != "pass":
            all_passed = False

        # 3. US Holidays
        logger.info("\n--- 3. US Calendar / Holidays ---")
        holidays_ok = check_holidays(logger)
        report["holidays_us"] = holidays_ok
        if not holidays_ok:
            all_passed = False

        # 4. Prophet Toy Fit
        logger.info("\n--- 4. Prophet Model Fit Test ---")
        prophet_ok = check_prophet_toy_fit(logger)
        report["prophet_toy_fit"] = prophet_ok
        if not prophet_ok:
            all_passed = False

    # Save summary artifact
    artifacts_dir = PROJECT_ROOT / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    report_path = artifacts_dir / "env_check_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info(f"\nEnvironment report saved to: {report_path}")

    if all_passed:
        logger.info("\n>>> ALL ENVIRONMENT CHECKS PASSED. Ready for Phase 1. <<<")
        sys.exit(0)
    else:
        logger.error("\n>>> ONE OR MORE CHECKS FAILED. Please resolve issues noted above. <<<")
        sys.exit(1)


if __name__ == "__main__":
    main()
