from __future__ import annotations

from copilot_echo.config import load_config
from copilot_echo.logging_conf import configure_logging
from copilot_echo.orchestrator import Orchestrator
from copilot_echo.tray import TrayApp


def main() -> None:
    config = load_config()
    configure_logging(config.app.log_level)

    orchestrator = Orchestrator(config)
    tray = TrayApp(config, orchestrator)
    tray.run()


if __name__ == "__main__":
    main()
