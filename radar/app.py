from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from radar.alerts.dispatcher import AlertDispatcher
from radar.alerts.email import send_email
from radar.alerts.service import AlertService
from radar.alerts.webhook import send_webhook
from radar.api.routes.alerts import router as alerts_router
from radar.api.routes.config import router as config_router
from radar.api.routes.feed import router as feed_router
from radar.api.routes.health import router as health_router
from radar.api.routes.home import router as home_router
from radar.api.routes.jobs import router as jobs_router
from radar.api.routes.reports import router as reports_router
from radar.api.routes.ui import router as ui_router
from radar.core.config import Settings, load_settings
from radar.core.db import create_engine_and_session_factory, init_db
from radar.core.repositories import RadarRepository
from radar.core.scheduler import RadarScheduler
from radar.jobs.daily_digest import run_daily_digest_job
from radar.jobs.gitcode_repos import run_gitcode_repos_job
from radar.jobs.github_burst import run_github_burst_job
from radar.jobs.huggingface_models import run_huggingface_models_job
from radar.jobs.modelers_models import run_modelers_models_job
from radar.jobs.official_pages import run_official_pages_job
from radar.reports.summarization import (
    CloseableReportSummarizer,
    NullReportSummarizer,
    OpenAIReportSummarizer,
)
from radar.sources.github.client import GitHubClient
from radar.sources.gitcode.client import GitCodeClient
from radar.sources.huggingface.client import HuggingFaceClient
from radar.sources.github.client import expand_query_date_placeholders
from radar.sources.github.pipeline import readme_matches_keywords
from radar.sources.modelers.client import ModelersClient
from radar.sources.modelscope.client import ModelScopeClient
from radar.sources.official_pages.client import fetch_html


@dataclass
class RuntimeState:
    settings: Settings
    config_path: Path
    engine: Any
    repo: RadarRepository
    scheduler: RadarScheduler
    alert_service: AlertService
    github_client: GitHubClient
    huggingface_client: Any
    modelscope_client: Any
    modelers_client: Any
    gitcode_client: Any
    report_summarizer: CloseableReportSummarizer
    github_readme_ai_filter: Any = None


def _build_channels(settings: Settings) -> dict[str, Any]:
    channels: dict[str, Any] = {}
    if settings.channels.webhook.enabled and settings.channels.webhook.url is not None:
        channels["webhook"] = str(settings.channels.webhook.url)
    if settings.channels.email.enabled:
        channels["email"] = True
    return channels


def _build_email_sender(settings: Settings):
    if not settings.channels.email.enabled:
        return None

    email_settings = settings.channels.email
    from_address = email_settings.from_address or "radar@example.com"

    def _sender(payload: dict) -> None:
        send_email(
            payload,
            smtp_host=email_settings.smtp_host or "localhost",
            smtp_port=email_settings.smtp_port,
            username=email_settings.username,
            password=email_settings.password,
            from_address=from_address,
            to=email_settings.to,
        )

    return _sender


def _build_report_summarizer(settings: Settings) -> CloseableReportSummarizer:
    if settings.summarization.enabled:
        return OpenAIReportSummarizer(
            base_url=str(settings.summarization.base_url),
            api_key=settings.summarization.api_key or "",
            model=settings.summarization.model or "",
            timeout_seconds=settings.summarization.timeout_seconds,
            max_input_chars=settings.summarization.max_input_chars,
        )
    return NullReportSummarizer()


def _close_report_summarizer(summarizer: CloseableReportSummarizer | None) -> None:
    if summarizer is not None:
        summarizer.close()


def build_runtime(config_path: Path) -> RuntimeState:
    settings = load_settings(config_path)
    engine, session_factory = create_engine_and_session_factory(Path(settings.storage.path))
    init_db(engine)
    repo = RadarRepository(session_factory)
    dispatcher = AlertDispatcher(
        repository=repo,
        send_webhook=send_webhook if settings.channels.webhook.enabled else None,
        send_email=_build_email_sender(settings),
    )
    alert_service = AlertService(
        repository=repo,
        dispatcher=dispatcher,
        channels=_build_channels(settings),
    )
    github_client = GitHubClient(settings.sources.github.token)
    huggingface_client = HuggingFaceClient()
    modelscope_client = ModelScopeClient()
    modelers_client = ModelersClient()
    gitcode_client = GitCodeClient(settings.sources.gitcode.token or "")
    scheduler = RadarScheduler(timezone=settings.app.timezone)
    report_summarizer = _build_report_summarizer(settings)

    if settings.sources.official_pages.enabled:

        def _run_official_pages() -> int:
            created = 0
            for page in settings.sources.official_pages.pages:
                created += run_official_pages_job(
                    page_config=page,
                    fetch_html=fetch_html,
                    repository=repo,
                    alert_service=alert_service,
                )
            return created

        scheduler.register("official_pages", _run_official_pages, minutes=10)

    if settings.sources.github.enabled:

        def _run_github_burst() -> int:
            search_items: list[dict] = []
            for query in settings.sources.github.queries:
                search_items.extend(
                    github_client.search_repositories(
                        expand_query_date_placeholders(query)
                    )
                )
            github_filter = settings.sources.github.readme_filter
            if github_filter.enabled:
                filtered_items: list[dict] = []
                failures: list[tuple[str, Exception]] = []
                for item in search_items:
                    full_name = item["full_name"]
                    try:
                        readme_text = github_client.fetch_readme_text(full_name)
                    except Exception as exc:
                        failures.append((full_name, exc))
                        continue
                    if readme_matches_keywords(readme_text, github_filter.require_any):
                        filtered_items.append(item)
                search_items = filtered_items
                if failures:
                    failed_repositories = ", ".join(
                        f"{full_name} ({exc})" for full_name, exc in failures
                    )
                    raise RuntimeError(
                        "github_burst readme filtering failed for repositories: "
                        f"{failed_repositories}"
                    )
            return run_github_burst_job(
                search_items=search_items,
                threshold=settings.sources.github.burst_threshold,
                repository=repo,
                alert_service=alert_service,
            )

        scheduler.register("github_burst", _run_github_burst, minutes=15)

    if settings.sources.huggingface.enabled:

        def _run_huggingface_models() -> int:
            created = 0
            failures: list[tuple[str, Exception]] = []
            for organization in settings.sources.huggingface.organizations:
                try:
                    items = huggingface_client.list_models_for_organization(organization)
                    created += run_huggingface_models_job(
                        items,
                        repository=repo,
                        alert_service=alert_service,
                    )
                except Exception as exc:
                    failures.append((organization, exc))
                    continue
            if failures:
                failed_organizations = ", ".join(
                    f"{organization} ({exc})" for organization, exc in failures
                )
                raise RuntimeError(
                    "huggingface_models failed for organizations: "
                    f"{failed_organizations}"
                )
            return created

        scheduler.register("huggingface_models", _run_huggingface_models, minutes=30)

    if settings.sources.modelscope.enabled:

        def _run_modelscope_models() -> int:
            created = 0
            failures: list[tuple[str, Exception]] = []
            for organization in settings.sources.modelscope.organizations:
                try:
                    items = modelscope_client.list_models_for_organization(organization)
                    from radar.jobs.modelscope_models import run_modelscope_models_job

                    created += run_modelscope_models_job(
                        items,
                        alert_service=alert_service,
                    )
                except Exception as exc:
                    failures.append((organization, exc))
                    continue
            if failures:
                failed_organizations = ", ".join(
                    f"{organization} ({exc})" for organization, exc in failures
                )
                raise RuntimeError(
                    "modelscope_models failed for organizations: "
                    f"{failed_organizations}"
                )
            return created

        scheduler.register("modelscope_models", _run_modelscope_models, minutes=30)

    if settings.sources.modelers.enabled:

        def _run_modelers_models() -> int:
            created = 0
            failures: list[tuple[str, Exception]] = []
            for organization in settings.sources.modelers.organizations:
                try:
                    items = modelers_client.list_models_for_organization(organization)
                    created += run_modelers_models_job(
                        items,
                        alert_service=alert_service,
                    )
                except Exception as exc:
                    failures.append((organization, exc))
                    continue
            if failures:
                failed_organizations = ", ".join(
                    f"{organization} ({exc})" for organization, exc in failures
                )
                raise RuntimeError(
                    "modelers_models failed for organizations: "
                    f"{failed_organizations}"
                )
            return created

        scheduler.register("modelers_models", _run_modelers_models, minutes=30)

    if settings.sources.gitcode.enabled:

        def _run_gitcode_repos() -> int:
            created = 0
            failures: list[tuple[str, Exception]] = []
            for organization in settings.sources.gitcode.organizations:
                try:
                    items = gitcode_client.list_repositories_for_organization(organization)
                    created += run_gitcode_repos_job(
                        items,
                        alert_service=alert_service,
                    )
                except Exception as exc:
                    failures.append((organization, exc))
                    continue
            if failures:
                failed_organizations = ", ".join(
                    f"{organization} ({exc})" for organization, exc in failures
                )
                raise RuntimeError(
                    "gitcode_repos failed for organizations: "
                    f"{failed_organizations}"
                )
            return created

        scheduler.register("gitcode_repos", _run_gitcode_repos, minutes=30)

    daily_digest_channels = _build_channels(settings)

    def _dispatch_daily_digest(payload: dict) -> None:
        dispatcher.dispatch_raw(
            alert_payload=payload,
            channels=daily_digest_channels,
            delivery_key_prefix="daily_digest",
        )

    def _run_daily_digest() -> int:
        return run_daily_digest_job(repo, dispatch=_dispatch_daily_digest)

    scheduler.register("daily_digest", _run_daily_digest, hours=24)

    return RuntimeState(
        settings=settings,
        config_path=config_path,
        engine=engine,
        repo=repo,
        scheduler=scheduler,
        alert_service=alert_service,
        github_client=github_client,
        huggingface_client=huggingface_client,
        modelscope_client=modelscope_client,
        modelers_client=modelers_client,
        gitcode_client=gitcode_client,
        report_summarizer=report_summarizer,
    )


def apply_runtime(app: FastAPI, runtime: RuntimeState) -> None:
    old_scheduler = getattr(app.state, "scheduler", None)
    if old_scheduler is not None:
        old_scheduler.stop()

    old_engine = getattr(app.state, "engine", None)
    if old_engine is not None:
        old_engine.dispose()

    _close_report_summarizer(getattr(app.state, "report_summarizer", None))

    app.state.settings = runtime.settings
    app.state.config_path = runtime.config_path
    app.state.engine = runtime.engine
    app.state.repo = runtime.repo
    app.state.scheduler = runtime.scheduler
    app.state.alert_service = runtime.alert_service
    app.state.github_client = runtime.github_client
    app.state.huggingface_client = runtime.huggingface_client
    app.state.modelscope_client = runtime.modelscope_client
    app.state.modelers_client = runtime.modelers_client
    app.state.gitcode_client = runtime.gitcode_client
    app.state.report_summarizer = runtime.report_summarizer
    app.state.github_readme_ai_filter = runtime.github_readme_ai_filter
    runtime.scheduler.start()


def shutdown_runtime(app: FastAPI) -> None:
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is not None:
        scheduler.stop()
    engine = getattr(app.state, "engine", None)
    if engine is not None:
        engine.dispose()
    _close_report_summarizer(getattr(app.state, "report_summarizer", None))

def create_app(lifespan: Any = None) -> FastAPI:
    app = FastAPI(title="AI Infra Radar", lifespan=lifespan)
    app.include_router(home_router)
    app.include_router(health_router)
    app.include_router(alerts_router)
    app.include_router(jobs_router)
    app.include_router(config_router)
    app.include_router(reports_router)
    app.include_router(feed_router)
    app.include_router(ui_router)
    app.mount(
        "/static/results",
        StaticFiles(directory=Path(__file__).resolve().parent / "ui" / "results"),
        name="results-static",
    )
    app.mount(
        "/static/ops",
        StaticFiles(directory=Path(__file__).resolve().parent / "ui"),
        name="ops-static",
    )
    # Initialise default state so routes never hit AttributeError
    app.state.engine = None
    app.state.repo = None
    app.state.scheduler = None
    app.state.settings = None
    app.state.config_path = None
    app.state.alert_service = None
    app.state.github_client = None
    app.state.huggingface_client = None
    app.state.modelscope_client = None
    app.state.modelers_client = None
    app.state.gitcode_client = None
    app.state.report_summarizer = NullReportSummarizer()
    app.state.github_readme_ai_filter = None
    return app
