from gui.calibrators.verifiers.bq78350 import verify_bq78350
from gui.calibrators.verifiers.bq40z50 import verify_bq40z50

def run_post_verify(runner) -> bool:
    """Dispatches post-verification to the appropriate IC verifier module."""
    try:
        run_mode = runner.targets.get("run_mode", "voltage")
        show_voltage = run_mode in ("voltage", "all")
        show_temp = run_mode in ("temp", "temperature", "all")

        ic_upper = runner.ic_name.upper()
        if "BQ78350" in ic_upper:
            return verify_bq78350(runner, show_voltage, show_temp)
        else:
            return verify_bq40z50(runner, show_voltage, show_temp)
    except Exception as e:
        runner._log(f"CRASH in post_verify: {e}")
        return False
