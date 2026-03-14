from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys

from bugsi_daemon.config import ConfigManager


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BUGSI Device Client")
    parser.add_argument("--mock", action="store_true", help="Use mock hardware (or set BUGSI_MOCK_HARDWARE=true)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--config-dir", default=None,
        help="Path to config directory (default: bundled config/)",
    )
    parser.add_argument(
        "--credentials", default=None,
        help="Path to credentials.json (default: /mnt/usb/bugsi/credentials.json)",
    )
    parser.add_argument("--api-key", default=None, help="Device API key")
    parser.add_argument("--api-url", default=None, help="Backend API URL")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Add --mock and --verbose to each subparser too, so they work after the subcommand
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--mock", action="store_true", help=argparse.SUPPRESS)
    shared.add_argument("--verbose", "-v", action="store_true", help=argparse.SUPPRESS)
    shared.add_argument("--api-key", default=None, help=argparse.SUPPRESS)
    shared.add_argument("--api-url", default=None, help=argparse.SUPPRESS)

    subparsers.add_parser("run", help="Start the daemon", parents=[shared])
    subparsers.add_parser("telemetry", help="Collect and print one telemetry reading", parents=[shared])
    subparsers.add_parser("upload", help="Run one upload cycle immediately", parents=[shared])
    subparsers.add_parser("status", help="Show buffer stats, config version, power mode", parents=[shared])
    subparsers.add_parser("config", help="Show current configuration", parents=[shared])

    return parser


def load_config(args) -> ConfigManager:
    from pathlib import Path

    default_config_path = Path(__file__).parent.parent / "config" / "default.json"
    if args.config_dir:
        default_config_path = Path(args.config_dir) / "default.json"

    kwargs = {"default_config_path": default_config_path}
    if args.credentials:
        kwargs["credentials_path"] = args.credentials

    config = ConfigManager(**kwargs)
    config.load()

    # CLI args override credentials
    api_key = getattr(args, "api_key", None)
    api_url = getattr(args, "api_url", None)
    if api_key or api_url:
        config.set_credentials(api_key=api_key, api_url=api_url)

    return config


async def run_daemon(config: ConfigManager, mock: bool) -> None:
    from bugsi_daemon.cli import init_components
    from bugsi_daemon.core.scheduler import Scheduler

    components = await init_components(config, mock)
    scheduler = Scheduler(
        config=config,
        telemetry_collector=components["telemetry"],
        upload_cycle=components["upload"],
        power_manager=components["power_manager"],
        buffer=components["buffer"],
        backup=components["backup"],
        thumbnail_generator=components.get("thumbnail_generator"),
        web_server=components.get("web_server"),
    )

    loop = asyncio.get_event_loop()

    def handle_signal():
        logging.getLogger(__name__).info("Signal received, shutting down...")
        asyncio.ensure_future(scheduler.shutdown())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal)

    try:
        await scheduler.start()
    finally:
        await components["buffer"].close()
        components["client"].close()
        logging.getLogger(__name__).info("Daemon stopped")


async def _wait_for_credentials(config: ConfigManager) -> None:
    """Wait for credentials to become available (e.g. env var or credentials file created)."""
    logger = logging.getLogger(__name__)
    logger.warning(
        "API key/URL not configured. Waiting for credentials... "
        "Set BUGSI_API_KEY/BUGSI_API_URL env vars, use --api-key/--api-url, "
        "or create a credentials.json file."
    )
    while not config.is_configured:
        await asyncio.sleep(10)
        # Re-check env vars and credentials file
        config._load_credentials()
    logger.info("Credentials found, starting daemon")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(args.verbose)
    mock = args.mock or os.environ.get("BUGSI_MOCK_HARDWARE", "").lower() == "true"

    config = load_config(args)

    from bugsi_daemon import cli

    commands = {
        "telemetry": cli.cmd_telemetry,
        "upload": cli.cmd_upload,
        "status": cli.cmd_status,
        "config": cli.cmd_config,
    }

    if args.command == "run":
        if not config.is_configured:
            asyncio.run(_wait_for_credentials(config))
        asyncio.run(run_daemon(config, mock))
    elif args.command in commands:
        if not config.is_configured:
            print(
                "Error: API key/URL not configured. Use --api-key/--api-url, "
                "set BUGSI_API_KEY/BUGSI_API_URL env vars, or create a credentials.json file.",
                file=sys.stderr,
            )
            sys.exit(1)
        asyncio.run(commands[args.command](config, mock))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
