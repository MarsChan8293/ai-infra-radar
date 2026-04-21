from __future__ import annotations

from pathlib import Path

import typer

from radar.app import build_runtime
from radar.core.config import load_settings
from radar.pages.export import export_pages_site

cli = typer.Typer(no_args_is_help=True)
_SOURCE_TO_JOB = {
    "official_pages": "official_pages",
    "github": "github_burst",
    "huggingface": "huggingface_models",
    "modelscope": "modelscope_models",
    "modelers": "modelers_models",
    "gitcode": "gitcode_repos",
}


def _close_github_readme_ai_filter(runtime: object) -> None:
    readme_ai_filter = getattr(runtime, "github_readme_ai_filter", None)
    if readme_ai_filter is not None:
        readme_ai_filter.close()


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
    runtime = build_runtime(config)
    try:
        known_jobs = runtime.scheduler.known_jobs()
        if job_name not in known_jobs:
            typer.echo(
                f"error: unknown job {job_name!r}. known jobs: {sorted(known_jobs)}",
                err=True,
            )
            raise typer.Exit(1)
        runtime.scheduler.run(job_name)
        typer.echo(f"{job_name}: executed")
    finally:
        summarizer = getattr(runtime, "report_summarizer", None)
        if summarizer is not None:
            summarizer.close()
        _close_github_readme_ai_filter(runtime)
        runtime.engine.dispose()


@cli.command("backfill-source")
def backfill_source(
    source: str,
    config: Path = typer.Option(..., "--config", help="Path to radar.yaml"),
) -> None:
    """Re-run all jobs for a given source (alias for run-job)."""
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

        payload = {
            "event_type": "daily_digest_item",
            "digest_type": "daily_digest",
            "digest_count": 1,
            "item_index": 1,
            "alert_id": 0,
            "alert_type": "test_notification",
            "source": "radar",
            "score": 1.0,
            "title": "AI Infra Radar test notification",
        }
        response = httpx.post(str(ch.url), json=payload, timeout=10)
        response.raise_for_status()
        typer.echo(f"test notification sent to {ch.url}")
    elif channel == "email":
        typer.echo("email test notification not yet implemented")
    else:
        typer.echo(f"error: unknown channel {channel!r}", err=True)
        raise typer.Exit(1)


@cli.command("export-pages")
def export_pages(
    config: Path = typer.Option(..., "--config", help="Path to radar.yaml"),
    output: Path = typer.Option(..., "--output", help="Directory to write Pages site"),
) -> None:
    runtime = build_runtime(config)
    try:
        export_pages_site(
            runtime.repo,
            output,
            report_summarizer=runtime.report_summarizer,
        )
        typer.echo(f"pages exported to {output}")
    finally:
        runtime.report_summarizer.close()
        _close_github_readme_ai_filter(runtime)
        runtime.engine.dispose()


if __name__ == "__main__":
    cli()
