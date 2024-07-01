import gevent.subprocess
import sys


def start_server():
    """
    Boots the Ditto Server for API calls.
    """
    print("\n[Starting server...]")
    gevent.subprocess.call(["python", "modules/server/start_server.py"])


if __name__ == "__main__":
    start_server()
