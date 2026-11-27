import sys
from roof_lib import execute_roof_cycle, setup_logger

CLOSE_WAIT_SECONDS = 28


def main() -> int:
    logger = setup_logger("CloseRoof")
    return execute_roof_cycle("CLOSE", CLOSE_WAIT_SECONDS, logger)


if __name__ == "__main__":
    sys.exit(main())