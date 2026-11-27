import sys
from roof_lib import run_obs_control, setup_logger


def main() -> int:
    logger = setup_logger("StopRoof")
    logger.info("Sending emergency STOP command to roof controller...")
    if not run_obs_control("STOP", logger):
        return 1
    logger.info("STOP command sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())