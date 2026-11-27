import sys
from roof_lib import execute_roof_cycle, setup_logger

OPEN_WAIT_SECONDS = 25


def main() -> int:
    logger = setup_logger("OpenRoof")
    return execute_roof_cycle("OPEN", OPEN_WAIT_SECONDS, logger)


if __name__ == "__main__":
    sys.exit(main())