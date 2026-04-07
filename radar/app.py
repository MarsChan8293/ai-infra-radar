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
from radar.api.routes.health import router as health_router
from radar.api.routes.jobs import router as jobs_router
from radar.api.routes.ui import router as ui_router
from radar.core.config import Settings, load_settings
from radar.core.db import create_engine_and_session_factory, init_db
from radar.core.repositories import RadarRepository
from radar.core.scheduler import RadarScheduler
from radar.jobs.daily_digest import run_daily_digest_job
from radar.jobs.github_burst import run_github_burst_job
from radar.jobs.huggingface_models import run_huggingface_models_job
from radar.jobs.modelers_models import run_modelers_models_job
from radar.jobs.official_pages import run_official_pages_job
from radar.sources.github.client import GitHubClient
from radar.sources.huggingface.client import HuggingFaceClient
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
    scheduler = RadarScheduler(timezone=settings.app.timezone)

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
                search_items.extend(github_client.search_repositories(query))
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
                except Exception as exc:
                    failures.append((organization, exc))
                    continue
                created += run_huggingface_models_job(
                    items,
                    repository=repo,
                    alert_service=alert_service,
                )
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
                except Exception as exc:
                    failures.append((organization, exc))
                    continue
                from radar.jobs.modelscope_models import run_modelscope_models_job

                created += run_modelscope_models_job(
                    items,
                    alert_service=alert_service,
                )
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
                except Exception as exc:
                    failures.append((organization, exc))
                    continue
                created += run_modelers_models_job(
                    items,
                    alert_service=alert_service,
                )
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
    )


def apply_runtime(app: FastAPI, runtime: RuntimeState) -> None:
    old_scheduler = getattr(app.state, "scheduler", None)
    if old_scheduler is not None:
        old_scheduler.stop()

    old_engine = getattr(app.state, "engine", None)
    if old_engine is not None:
        old_engine.dispose()

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
    runtime.scheduler.start()


def shutdown_runtime(app: FastAPI) -> None:
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is not None:
        scheduler.stop()
    engine = getattr(app.state, "engine", None)
    if engine is not None:
        engine.dispose()

def create_app(lifespan: Any = None) -> FastAPI:
    app = FastAPI(title="AI Infra Radar", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(alerts_router)
    app.include_router(jobs_router)
    app.include_router(config_router)
    app.include_router(ui_router)
    app.mount(
        "/static/ui",
        StaticFiles(directory=Path(__file__).resolve().parent / "ui"),
        name="ui-static",
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
    return app
