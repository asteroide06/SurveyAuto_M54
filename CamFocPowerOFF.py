import sys
from cam_foc_power_lib import set_cam_foc_power, setup_logger


def main() -> int:
    logger = setup_logger("CamFocPowerOFF")
    return set_cam_foc_power(0, logger)


if __name__ == "__main__":
    sys.exit(main())