"""Progress bar and execution timing helpers."""
import time
from contextlib import contextmanager
from typing import Iterable, Optional, TypeVar
from tqdm import tqdm

T = TypeVar("T")


def get_progress_bar(
    iterable: Optional[Iterable[T]] = None,
    total: Optional[int] = None,
    desc: str = "Processing",
    unit: str = "it",
    leave: bool = True,
    **kwargs,
) -> tqdm:
    """Standardized tqdm progress bar configured for consistent CLI output.

    Args:
        iterable: Optional iterable to wrap.
        total: Expected total iterations if iterable is a generator or not provided.
        desc: Descriptive label displayed beside the progress bar.
        unit: Unit of measurement (e.g., 'pair', 'sku', 'fold').
        leave: Whether to leave the progress bar on screen after completion.
        **kwargs: Additional parameters passed to tqdm.

    Returns:
        Configured tqdm instance.
    """
    return tqdm(
        iterable=iterable,
        total=total,
        desc=desc,
        unit=unit,
        leave=leave,
        ncols=100,
        bar_format="{l_bar}{bar:25}{r_bar}{bar:-10b}",
        **kwargs,
    )


@contextmanager
def timed_block(name: str, logger=None):
    """Context manager measuring and reporting elapsed execution time.

    Args:
        name: Name of the executed block or task.
        logger: Optional logger instance. If None, prints to stdout.
    """
    msg_start = f"--> Starting: {name}"
    if logger:
        logger.info(msg_start)
    else:
        print(msg_start)

    start_time = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start_time
        mins, secs = divmod(elapsed, 60)
        time_str = f"{int(mins)}m {secs:.2f}s" if mins > 0 else f"{secs:.2f}s"
        msg_end = f"<-- Finished: {name} (Elapsed: {time_str})"
        if logger:
            logger.info(msg_end)
        else:
            print(msg_end)
