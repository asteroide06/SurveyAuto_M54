import logging
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

WIFI_WAIT_SECONDS = 10
OBS_CONTROL_DIR = r"C:\ImagesNuit\Tools\ObsControl"
OBS_CONTROL_EXE = r"C:\ImagesNuit\Tools\ObsControl\ObsControl.exe"
IPX800_HOST = "192.168.0.250:81"
IPX800_URL_TEMPLATE = "http://192.168.0.250:81/preset.htm?set6={state}"


def get_ipx800_credentials() -> tuple[str, str]:
    """Récupère les identifiants IPX800 depuis les variables d'environnement utilisateur."""
    user = os.environ.get("M54_IPX800_USER")
    password = os.environ.get("M54_IPX800_PASS")
    if not user or not password:
        raise RuntimeError(
            "Variables d'environnement M54_IPX800_USER ou M54_IPX800_PASS manquantes."
        )
    return user, password


def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
        logger.addHandler(handler)
    return logger


def set_roof_power(state: int, logger: logging.Logger) -> bool:
    """Active (1) ou coupe (0) l'alimentation du toit via le relais IPX800."""
    url = IPX800_URL_TEMPLATE.format(state=state)
    action = "ON" if state == 1 else "OFF"
    try:
        ipx_user, ipx_pass = get_ipx800_credentials()
        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, f"http://{IPX800_HOST}/", ipx_user, ipx_pass)
        auth_handler = urllib.request.HTTPBasicAuthHandler(password_mgr)
        opener = urllib.request.build_opener(auth_handler)

        req = urllib.request.Request(url, method="POST")
        with opener.open(req, timeout=5) as resp:
            logger.info("Roof power %s (HTTP %s)", action, resp.status)
            return 200 <= resp.status < 300
    except RuntimeError as exc:
        logger.error("%s", exc)
        return False
    except urllib.error.URLError as exc:
        logger.error("Failed to set roof power %s: %s", action, exc)
        return False


def run_obs_control(command: str, logger: logging.Logger) -> bool:
    """Lance ObsControl.exe avec l'argument OPEN ou CLOSE."""
    try:
        logger.info("Running ObsControl.exe %s...", command)
        result = subprocess.run(
            [OBS_CONTROL_EXE, command],
            cwd=OBS_CONTROL_DIR,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            logger.warning("ObsControl.exe exited with code %s", result.returncode)
        return True
    except FileNotFoundError:
        logger.error("ObsControl.exe not found at %s", OBS_CONTROL_EXE)
        return False
    except subprocess.TimeoutExpired:
        logger.warning("ObsControl.exe %s did not exit within 15s (continuing move wait)", command)
        return True
    except Exception as exc:
        logger.error("Error running ObsControl.exe %s: %s", command, exc)
        return False


def execute_roof_cycle(command: str, move_wait_seconds: int, logger: logging.Logger) -> int:
    """Exécute la séquence complète : ON -> attente Wi-Fi -> commande -> attente course -> OFF."""
    if not set_roof_power(1, logger):
        return 1

    logger.info("Waiting %d seconds for ESP8266 Wi-Fi connection...", WIFI_WAIT_SECONDS)
    time.sleep(WIFI_WAIT_SECONDS)

    if not run_obs_control(command, logger):
        set_roof_power(0, logger)
        return 1

    logger.info("Waiting %d seconds for roof movement (%s)...", move_wait_seconds, command)
    time.sleep(move_wait_seconds)

    if not set_roof_power(0, logger):
        return 1

    logger.info("Roof %s sequence completed.", command)
    return 0