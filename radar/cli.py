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



if __name__ == "__main__":
    cli()
