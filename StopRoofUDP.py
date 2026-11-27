import socket
import sys
from roof_lib import run_obs_control, setup_logger

ESP8266_IP = "192.168.0.104"
ESP8266_UDP_PORT = 4210
STOP_PAYLOAD = b"STOP"


def send_udp_stop(ip: str, port: int, payload: bytes, logger) -> bool:
    """Envoie directement la trame UDP STOP à l'ESP8266."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(2.0)
            sent_bytes = sock.sendto(payload, (ip, port))
            logger.info(
                "Direct UDP fallback: sent %d byte(s) (%r) to %s:%d",
                sent_bytes,
                payload.decode("ascii", errors="replace"),
                ip,
                port,
            )
            return sent_bytes == len(payload)
    except OSError as exc:
        logger.error("Direct UDP STOP failed to %s:%d: %s", ip, port, exc)
        return False


def main() -> int:
    logger = setup_logger("StopRoof")
    logger.info("Sending emergency STOP command...")

    if run_obs_control("STOP", logger):
        return 0

    logger.warning("ObsControl.exe failed or timed out; falling back to direct UDP STOP...")
    if send_udp_stop(ESP8266_IP, ESP8266_UDP_PORT, STOP_PAYLOAD, logger):
        return 0

    logger.error("Both ObsControl.exe and direct UDP STOP failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())