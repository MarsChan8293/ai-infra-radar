from pathlib import Path

import typer

from radar.core.config import load_settings

cli = typer.Typer(no_args_is_help=True)


@cli.command("validate-config")
def validate_config(path: Path) -> None:
    load_settings(path)
    typer.echo("config ok")


@cli.command("run-job")
def run_job(job_name: str) -> None:
    typer.echo(f"queued {job_name}")


@cli.command("backfill-source")
def backfill_source(source: str, start: str, end: str) -> None:
    typer.echo(f"backfill {source} {start} {end}")


@cli.command("send-test-notification")
def send_test_notification(channel: str) -> None:
    typer.echo(f"test notification {channel}")


if __name__ == "__main__":
    cli()
