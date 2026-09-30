"""Command-line interface for Skill Atlas."""

from typing import Annotated

import typer

from skill_atlas import __version__
from skill_atlas.models import ScanResult
from skill_atlas.reporters import ConsoleReporter, JsonReporter
from skill_atlas.scanner import Scanner

app = typer.Typer(
    name="skill-atlas",
    help="Skill Atlas — Discovery, structural validation, and static security auditing for AI Agent Skills.",
    add_completion=False,
)


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"skill-atlas version: {__version__}")
        raise typer.Exit(0)


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            callback=version_callback,
            is_eager=True,
            help="Show the application version and exit.",
        ),
    ] = None,
) -> None:
    pass


@app.command(name="scan")
def scan_command(
    target: Annotated[
        str,
        typer.Argument(
            metavar="TARGET",
            help="Path to a skill directory, a local Git repository, or a remote Git repository URL.",
        ),
    ] = ".",
    format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output report format (text, json).",
            case_sensitive=False,
        ),
    ] = "text",
    fail_on: Annotated[
        str,
        typer.Option(
            "--fail-on",
            help="Minimum severity level triggering a non-zero exit code (error, warn).",
            case_sensitive=False,
        ),
    ] = "error",
    rules: Annotated[
        str,
        typer.Option(
            "--rules",
            "-r",
            help="Filter rule categories (all, schema, security).",
            case_sensitive=False,
        ),
    ] = "all",
    ignore: Annotated[
        list[str] | None,
        typer.Option(
            "--ignore",
            help="Rule IDs to ignore (e.g. --ignore SCH-004 --ignore SEC-005).",
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Verbose output including passed checks.",
        ),
    ] = False,
) -> None:
    """Scan skills for structural consistency and security vulnerabilities."""
    # Validate options
    format_clean = format.lower().strip()
    if format_clean not in ("text", "json"):
        typer.secho(
            f"Error: Invalid format '{format}'. Choose 'text' or 'json'.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    fail_on_clean = fail_on.lower().strip()
    if fail_on_clean not in ("error", "warn"):
        typer.secho(
            f"Error: Invalid --fail-on '{fail_on}'. Choose 'error' or 'warn'.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    rules_clean = rules.lower().strip()
    if rules_clean not in ("all", "schema", "security"):
        typer.secho(
            f"Error: Invalid --rules '{rules}'. Choose 'all', 'schema', or 'security'.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    try:
        scanner = Scanner(
            rules_category=rules_clean,
            ignored_rules=ignore or [],
        )
        result: ScanResult = scanner.scan(target)
    except Exception as err:
        typer.secho(f"Fatal scanning error: {err}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    # Output rendering
    if format_clean == "json":
        json_reporter = JsonReporter()
        typer.echo(json_reporter.render(result))
    else:
        console_reporter = ConsoleReporter()
        console_reporter.render(result, fail_on=fail_on_clean)

    # Determine exit code
    errors = result.summary.findings_count.get("error", 0)
    warnings = result.summary.findings_count.get("warn", 0)

    if fail_on_clean == "error":
        has_failed = errors > 0
    else:  # fail_on == "warn"
        has_failed = (errors + warnings) > 0

    if has_failed:
        raise typer.Exit(code=1)
    raise typer.Exit(code=0)


if __name__ == "__main__":
    app()
