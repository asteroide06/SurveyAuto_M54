import logging
import os
import sys
import urllib.error
import urllib.request

IPX800_HOST = "192.168.0.250:81"
RELAY_SET2_URL = "http://192.168.0.250:81/preset.htm?set2={state}"


def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
        logger.addHandler(handler)
    return logger


def set_cam_foc_power(state: int, logger: logging.Logger) -> int:
    """Active (1) ou coupe (0) l'alimentation caméra/focuser via le relais set2 de l'IPX800."""
    user = os.environ.get("M54_IPX800_USER")
    password = os.environ.get("M54_IPX800_PASS")
    if not user or not password:
        logger.error("Variables d'environnement M54_IPX800_USER ou M54_IPX800_PASS manquantes.")
        return 1

    url = RELAY_SET2_URL.format(state=state)
    action = "ON" if state == 1 else "OFF"

    try:
        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, f"http://{IPX800_HOST}/", user, password)
        opener = urllib.request.build_opener(urllib.request.HTTPBasicAuthHandler(password_mgr))

        req = urllib.request.Request(url, method="POST")
        with opener.open(req, timeout=5) as resp:
            logger.info("Cam/Foc power %s (HTTP %s)", action, resp.status)
            return 0 if 200 <= resp.status < 300 else 1
    except urllib.error.URLError as exc:
        logger.error("Failed to set Cam/Foc power %s: %s", action, exc)
        return 1