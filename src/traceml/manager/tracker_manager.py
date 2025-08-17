import threading
import sys
from typing import List, Tuple, Any, Dict


class TrackerManager:
    """
    Manages periodic sampling and logging of system metrics (CPU, memory, tensors, etc.)
    using a background thread. Each component defines a sampler and a list of associated loggers.

    This class ensures consistent sampling even if some components fail intermittently.
    """

    # components: List[Tuple[SamplerType, List[LoggerType]]]
    def __init__(
        self, components: List[Tuple[Any, List[Any]]], interval_sec: float = 1.0
    ):
        """
        Args:
            components (list of tuples): List of (sampler, list of loggers) pairs.
                                         Each sampler's output is sent to all loggers in its list.
            interval_sec (int): Time interval in seconds between samples.
        """
        self.components = components
        self.interval_sec = interval_sec
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        """
        Background thread loop that continuously samples and logs live snapshots.
        """
        while not self._stop_event.is_set():
            for sampler, loggers in self.components:
                try:
                    snapshot = sampler.sample()
                except Exception as e:
                    print(
                        f"[TraceML] Error in sampler '{sampler.__class__.__name__}'.sample(): {e}",
                        file=sys.stderr,
                    )
                    snapshot = {
                        "error": str(e),
                        "sampler_name": sampler.__class__.__name__,
                    }

                # 2. Log snapshot to all associated loggers
                for logger in loggers:
                    try:
                        logger.log(snapshot)
                    except Exception as e:
                        print(
                            f"[TraceML] Error in logger '{logger.__class__.__name__}'.log() for sampler '{sampler.__class__.__name__}': {e}",
                            file=sys.stderr,
                        )

            # 3. Wait for the next interval
            self._stop_event.wait(self.interval_sec)

    def start(self) -> None:
        """
        Starts the background tracking thread.
        """
        try:
            print("[TraceML] TrackerManager started.", file=sys.stderr)
            self._thread.start()
        except Exception as e:
            print(f"[TraceML] Failed to start TrackerManager: {e}", file=sys.stderr)

    def stop(self) -> None:
        """
        Signals the background thread to stop and waits for it to terminate.
        """
        try:
            print("[TraceML] Stopping TrackerManager...", file=sys.stderr)
            self._stop_event.set()
            self._thread.join(timeout=self.interval_sec * 2)

            if self._thread.is_alive():
                print(
                    f"[TraceML] WARNING: Tracker thread did not terminate within timeout.",
                    file=sys.stderr,
                )

            print("[TraceML] TrackerManager stopped.", file=sys.stderr)

            # Logger shutdown is now handled more broadly by the main execution context
            # calling StdoutDisplayManager.stop_display() and individual log_summaries.
            # However, if any logger has specific internal cleanup (e.g., closing files),
            # it might still have a 'shutdown' method.
            for _, loggers in self.components:
                for logger in loggers:
                    shutdown_fn = getattr(logger, "shutdown", None)
                    if callable(shutdown_fn):
                        try:
                            shutdown_fn()
                        except Exception as e:
                            print(
                                f"[TraceML] Logger '{logger.__class__.__name__}' shutdown error: {e}",
                                file=sys.stderr,
                            )

        except Exception as e:
            print(f"[TraceML] Failed to stop TrackerManager: {e}", file=sys.stderr)

    def log_summaries(self) -> None:
        """
        Logs final summaries from each sampler after tracking stops.
        Useful for reporting peak usage or historical stats.
        """
        print("\n[TraceML] Generating summaries...", file=sys.stderr)
        for sampler, loggers in self.components:
            summary: Dict[str, Any] = {}
            try:
                summary = sampler.get_summary()
            except Exception as e:
                print(
                    f"[TraceML] Error getting summary from sampler '{sampler.__class__.__name__}': {e}",
                    file=sys.stderr,
                )
                summary = {"error": str(e), "sampler_name": sampler.__class__.__name__}

            for logger in loggers:
                try:
                    logger.log_summary(summary)
                except Exception as e:
                    print(
                        f"[TraceML] Error in logger '{logger.__class__.__name__}'.log_summary() for sampler '{sampler.__class__.__name__}': {e}",
                        file=sys.stderr,
                    )
        print("[TraceML] Summaries generated.", file=sys.stderr)
