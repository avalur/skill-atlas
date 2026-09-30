"""Command-line interface for Skill Atlas."""

import sys
from typing import Annotated

import typer
from rich.console import Console

from skill_atlas import __version__
from skill_atlas.models import ProgressEvent, ScanResult
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
            help="Filter rule categories (all, schema, security, discovery).",
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
    ref: Annotated[
        str | None,
        typer.Option(
            "--ref",
            help="Pinned Git reference (branch, tag, or commit SHA) for remote scans.",
        ),
    ] = None,
    include_test_data: Annotated[
        bool,
        typer.Option(
            "--include-test-data",
            help="Treat test-data skills as blocking for exit codes.",
        ),
    ] = False,
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
    target_clean = target.strip()
    if target_clean.startswith("-"):
        typer.secho(
            f"Error: Invalid target '{target}'. Target cannot start with '-'.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

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
    if rules_clean not in ("all", "schema", "security", "discovery"):
        typer.secho(
            f"Error: Invalid --rules '{rules}'. Choose 'all', 'schema', 'security', or 'discovery'.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    try:
        stderr_console = Console(stderr=True)

        def on_progress(event: ProgressEvent) -> None:
            if format_clean != "json" and sys.stderr.isatty():
                stderr_console.print(f"[dim]⟳ {event.message}[/dim]", end="\r")

        scanner = Scanner(
            rules_category=rules_clean,
            ignored_rules=ignore or [],
            fail_on=fail_on_clean,
            include_test_data=include_test_data,
        )
        result: ScanResult = scanner.scan(
            target=target,
            ref=ref,
            include_test_data=include_test_data,
            on_progress=on_progress,
        )

        # Clear progress line if printed
        if format_clean != "json" and sys.stderr.isatty():
            stderr_console.print(" " * 80, end="\r")

        # Output rendering
        if format_clean == "json":
            json_reporter = JsonReporter()
            typer.echo(json_reporter.render(result))
        else:
            console_reporter = ConsoleReporter()
            console_reporter.render(
                result,
                fail_on=fail_on_clean,
                include_test_data=include_test_data,
                verbose=verbose,
            )

        raise typer.Exit(
            code=result.exit_code(fail_on=fail_on_clean, include_test_data=include_test_data)
        )

    except typer.Exit:
        raise
    except Exception as err:
        typer.secho(f"Fatal error: {err}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from err


@app.command(name="serve")
def serve_command(
    host: Annotated[
        str,
        typer.Option("--host", help="Server host to bind to (e.g. 127.0.0.1)."),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", help="Server port to listen on."),
    ] = 8765,
    open_browser: Annotated[
        bool,
        typer.Option("--open", help="Open browser automatically on startup."),
    ] = False,
    allow_local: Annotated[
        bool,
        typer.Option("--allow-local", help="Allow scanning local directories via web interface."),
    ] = False,
) -> None:
    """Start local web interface for Skill Atlas."""
    from skill_atlas.web import run_server

    run_server(host=host, port=port, open_browser=open_browser, allow_local=allow_local)


if __name__ == "__main__":
    app()
