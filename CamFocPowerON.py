import sys
from cam_foc_power_lib import set_cam_foc_power, setup_logger


def main() -> int:
    logger = setup_logger("CamFocPowerON")
    return set_cam_foc_power(1, logger)


if __name__ == "__main__":
    sys.exit(main())