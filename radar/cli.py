from pathlib import Path

import typer

from radar.core.config import load_settings

cli = typer.Typer(no_args_is_help=True)


@cli.callback()
def _main() -> None:
    pass


@cli.command("validate-config")
def validate_config(path: Path) -> None:
    load_settings(path)
    typer.echo("config ok")


@cli.command("run-job")
def run_job(
    job_name: str,
    config: Path = typer.Option(..., "--config", help="Path to radar.yaml"),
) -> None:
    """Trigger a named job immediately using the configured sources."""
    _KNOWN_JOBS = {"official_pages", "github_burst"}
    if job_name not in _KNOWN_JOBS:
        typer.echo(f"error: unknown job {job_name!r}. known jobs: {sorted(_KNOWN_JOBS)}", err=True)
        raise typer.Exit(1)

    settings = load_settings(config)

    from radar.core.db import create_engine_and_session_factory, init_db
    from radar.core.repositories import RadarRepository

    engine, sf = create_engine_and_session_factory(settings.storage.path)
    init_db(engine)
    repo = RadarRepository(sf)

    if job_name == "official_pages":
        if not settings.sources.official_pages.enabled:
            typer.echo("official_pages source is not enabled in config", err=True)
            raise typer.Exit(1)
        import httpx

        from radar.jobs.official_pages import run_official_pages_job

        total = 0
        for page in settings.sources.official_pages.pages:
            total += run_official_pages_job(page, lambda url: httpx.get(url, timeout=30).text, repo, None)
        typer.echo(f"official_pages: {total} alert(s) created")

    elif job_name == "github_burst":
        if not settings.sources.github.enabled:
            typer.echo("github source is not enabled in config", err=True)
            raise typer.Exit(1)
        typer.echo("github_burst: full client wiring pending Task 8")


@cli.command("backfill-source")
def backfill_source(
    source: str,
    config: Path = typer.Option(..., "--config", help="Path to radar.yaml"),
) -> None:
    """Re-run all jobs for a given source (alias for run-job)."""
    _SOURCE_TO_JOB = {"official_pages": "official_pages", "github": "github_burst"}
    if source not in _SOURCE_TO_JOB:
        typer.echo(f"error: unknown source {source!r}. known sources: {sorted(_SOURCE_TO_JOB)}", err=True)
        raise typer.Exit(1)
    # Delegate to run_job logic via programmatic invocation
    run_job(job_name=_SOURCE_TO_JOB[source], config=config)


@cli.command("send-test-notification")
def send_test_notification(
    channel: str,
    config: Path = typer.Option(..., "--config", help="Path to radar.yaml"),
) -> None:
    """Send a test notification via a named channel."""
    settings = load_settings(config)
    if channel == "webhook":
        ch = settings.channels.webhook
        if not ch.enabled:
            typer.echo("webhook channel is not enabled", err=True)
            raise typer.Exit(1)
        import httpx

        payload = {"text": "AI Infra Radar: test notification"}
        httpx.post(str(ch.url), json=payload, timeout=10)
        typer.echo(f"test notification sent to {ch.url}")
    elif channel == "email":
        typer.echo("email test notification not yet implemented")
    else:
        typer.echo(f"error: unknown channel {channel!r}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    cli()
