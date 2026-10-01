"""Command-line interface for Skill Atlas."""

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape

from skill_atlas import __version__
from skill_atlas.discovery.org import DEFAULT_ORG_CONCURRENCY
from skill_atlas.map import classify_skills_jev, cluster_skills_ai, group_skills_heuristic
from skill_atlas.models import ProgressEvent, ScanResult, SkillOrigin
from skill_atlas.reporters import ConsoleReporter, JsonReporter
from skill_atlas.scanner import Scanner, normalize_targets, parse_targets_file
from skill_atlas.similarity import find_similar_skills

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
    targets: Annotated[
        list[str] | None,
        typer.Argument(
            metavar="[TARGETS...]",
            help="One or more paths to skill directories, local Git repositories, or remote Git repository URLs.",
        ),
    ] = None,
    targets_file: Annotated[
        Path | None,
        typer.Option(
            "--targets-file",
            "-T",
            help="Path to a newline-delimited text file containing target repository paths or URLs.",
        ),
    ] = None,
    query: Annotated[
        str | None,
        typer.Option(
            "--query",
            "-q",
            help="Search query to filter skills across all repositories before static rule auditing.",
        ),
    ] = None,
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
    sample: Annotated[
        bool,
        typer.Option(
            "--sample",
            help="Scan bundled sample test fixtures.",
        ),
    ] = False,
    concurrency: Annotated[
        int,
        typer.Option(
            "--concurrency",
            "-j",
            help="Max concurrent repositories to scan when auditing a GitHub organization.",
        ),
    ] = DEFAULT_ORG_CONCURRENCY,
    include_forks: Annotated[
        bool,
        typer.Option(
            "--include-forks",
            help="Include forked repositories when scanning a GitHub organization.",
        ),
    ] = False,
    include_archived: Annotated[
        bool,
        typer.Option(
            "--include-archived",
            help="Include archived repositories when scanning a GitHub organization.",
        ),
    ] = False,
    max_repos: Annotated[
        int | None,
        typer.Option(
            "--max-repos",
            help="Limit the number of organization repositories scanned (default: all).",
        ),
    ] = None,
) -> None:
    """Scan skills for structural consistency and security vulnerabilities."""
    raw_targets = list(targets) if targets else []

    file_targets: list[str] = []
    if targets_file is not None:
        try:
            file_targets = parse_targets_file(targets_file)
        except FileNotFoundError as err:
            typer.secho(f"Error: {err}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2) from err
        except (OSError, UnicodeDecodeError) as err:
            typer.secho(
                f"Error: Failed to read targets file '{targets_file}': {err}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2) from err
        except ValueError as err:
            typer.secho(f"Error: {err}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2) from err

    combined_targets = raw_targets + file_targets
    if not combined_targets:
        combined_targets = ["."]

    fixtures_dir = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"
    sample_target = (
        str(fixtures_dir / "vulnerable_skills")
        if (fixtures_dir / "vulnerable_skills").is_dir()
        else str(fixtures_dir)
    )
    if sample:
        if not Path(sample_target).is_dir():
            typer.secho("Error: Sample fixtures not found.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        combined_targets = [sample_target]
    else:
        new_targets: list[str] = []
        for t in combined_targets:
            if t in (":sample", "sample"):
                if not Path(sample_target).is_dir():
                    typer.secho("Error: Sample fixtures not found.", fg=typer.colors.RED, err=True)
                    raise typer.Exit(code=2)
                new_targets.append(sample_target)
            else:
                new_targets.append(t)
        combined_targets = new_targets

    # Validate target strings
    for t in combined_targets:
        if t.startswith("-"):
            typer.secho(
                f"Error: Invalid target '{t}'. Target cannot start with '-'.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2)

    normalized_targets = normalize_targets(combined_targets)
    query_clean = query.strip() if (query and query.strip()) else None

    if concurrency < 1:
        typer.secho(
            f"Error: Invalid --concurrency '{concurrency}'. Must be >= 1.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    if max_repos is not None and max_repos < 1:
        typer.secho(
            f"Error: Invalid --max-repos '{max_repos}'. Must be >= 1.",
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
                stderr_console.print(f"[dim]⟳ {escape(event.message)}[/dim]", end="\r")

        scanner = Scanner(
            rules_category=rules_clean,
            ignored_rules=ignore or [],
            fail_on=fail_on_clean,
            include_test_data=include_test_data,
        )
        result: ScanResult = scanner.scan(
            targets=normalized_targets,
            ref=ref,
            query=query_clean,
            include_test_data=include_test_data,
            on_progress=on_progress,
            concurrency=concurrency,
            include_forks=include_forks,
            include_archived=include_archived,
            max_repos=max_repos,
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


@app.command(name="similar")
def similar_command(
    target: Annotated[
        str,
        typer.Argument(
            metavar="TARGET",
            help="Path to a skill directory, a local Git repository, or a remote Git repository URL.",
        ),
    ] = ".",
    skill: Annotated[
        str | None,
        typer.Option(
            "--skill",
            "-s",
            help="Specific skill name or path to find similar skills for.",
        ),
    ] = None,
    threshold: Annotated[
        float,
        typer.Option(
            "--threshold",
            "-t",
            help="Minimum similarity score threshold between 0.0 and 1.0 (default: 0.5).",
        ),
    ] = 0.5,
    top_k: Annotated[
        int,
        typer.Option(
            "--top-k",
            "-k",
            help="Maximum number of similar skill matches to return (default: 10).",
        ),
    ] = 10,
    format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output report format (text, json).",
            case_sensitive=False,
        ),
    ] = "text",
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
            help="Include test-data skills in similarity analysis.",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Verbose output including score breakdown.",
        ),
    ] = False,
) -> None:
    """Find similar skills within a target or matching a specific skill using non-AI heuristics."""
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

    if not (0.0 <= threshold <= 1.0):
        typer.secho(
            f"Error: Invalid threshold '{threshold}'. Must be between 0.0 and 1.0.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    if top_k < 0:
        typer.secho(
            f"Error: Invalid --top-k '{top_k}'. Must be greater than or equal to 0.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    try:
        stderr_console = Console(stderr=True)

        def on_progress(event: ProgressEvent) -> None:
            if format_clean != "json" and sys.stderr.isatty():
                stderr_console.print(f"[dim]⟳ {escape(event.message)}[/dim]", end="\r")

        scanner = Scanner(
            include_test_data=include_test_data,
        )
        scan_res = scanner.scan(
            target=target,
            ref=ref,
            include_test_data=include_test_data,
            on_progress=on_progress,
            discovery_only=True,
        )

        if format_clean != "json" and sys.stderr.isatty():
            stderr_console.print(" " * 80, end="\r")

        skills = scan_res.skills
        if not include_test_data:
            skills = [s for s in skills if s.origin != SkillOrigin.TEST_DATA]

        sim_res = find_similar_skills(
            skills=skills,
            query_skill=skill,
            threshold=threshold,
            top_k=top_k,
            target=target,
        )

        if format_clean == "json":
            typer.echo(sim_res.model_dump_json(indent=2))
        else:
            console_reporter = ConsoleReporter()
            console_reporter.render_similarity(sim_res, verbose=verbose)

        raise typer.Exit(code=0)

    except typer.Exit:
        raise
    except Exception as err:
        typer.secho(f"Fatal error: {err}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from err


@app.command(name="map")
def map_command(
    target: Annotated[
        str,
        typer.Argument(
            metavar="TARGET",
            help="Path to a skill directory, a local Git repository, or a remote Git repository URL.",
        ),
    ] = ".",
    method: Annotated[
        str,
        typer.Option(
            "--method",
            "-m",
            help="Clustering method: 'heuristic' (shared words), 'ai' (Claude CLI), or 'jev' (TypeSafe Jev).",
            case_sensitive=False,
        ),
    ] = "heuristic",
    ai: Annotated[
        bool,
        typer.Option(
            "--ai",
            help="Shortcut flag for --method ai (uses claude -p).",
        ),
    ] = False,
    jev: Annotated[
        bool,
        typer.Option(
            "--jev",
            help="Shortcut flag for --method jev (uses TypeSafe AI Jev).",
        ),
    ] = False,
    threshold: Annotated[
        float,
        typer.Option(
            "--threshold",
            "-t",
            help="Similarity threshold for heuristic grouping (0.0 to 1.0).",
        ),
    ] = 0.35,
    replay: Annotated[
        str | None,
        typer.Option(
            "--replay",
            help="Path to recorded JSON file to replay instead of calling live AI.",
        ),
    ] = None,
    record: Annotated[
        str | None,
        typer.Option(
            "--record",
            help="Path to JSON file to record AI clustering response.",
        ),
    ] = None,
    format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output report format (text, json).",
            case_sensitive=False,
        ),
    ] = "text",
    include_test_data: Annotated[
        bool,
        typer.Option(
            "--include-test-data",
            help="Include test-data skills in the map.",
        ),
    ] = False,
    ref: Annotated[
        str | None,
        typer.Option(
            "--ref",
            help="Pinned Git reference for remote repository scans.",
        ),
    ] = None,
) -> None:
    """Generate a Skill Map grouping skills by heuristic shared words, Claude AI, or TypeSafe Jev."""
    if target.startswith("-"):
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

    effective_method = "ai" if ai else ("jev" if jev else method.lower().strip())
    if effective_method not in ("heuristic", "ai", "jev"):
        typer.secho(
            f"Error: Invalid method '{method}'. Choose 'heuristic', 'ai', or 'jev'.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    try:
        stderr_console = Console(stderr=True)

        def on_progress(event: ProgressEvent) -> None:
            if format_clean != "json" and sys.stderr.isatty():
                stderr_console.print(f"[dim]⟳ {escape(event.message)}[/dim]", end="\r")

        scanner = Scanner(include_test_data=include_test_data)
        scan_res = scanner.scan(
            target=target,
            ref=ref,
            include_test_data=include_test_data,
            on_progress=on_progress,
            discovery_only=True,
        )

        if format_clean != "json" and sys.stderr.isatty():
            stderr_console.print(" " * 80, end="\r")

        skills = scan_res.skills
        if not include_test_data:
            skills = [s for s in skills if s.origin != SkillOrigin.TEST_DATA]

        if effective_method == "jev":
            map_res = classify_skills_jev(skills, replay_file=replay, record_file=record)
        elif effective_method == "ai":
            map_res = cluster_skills_ai(skills, replay_file=replay, record_file=record)
        else:
            map_res = group_skills_heuristic(skills, threshold=threshold)

        if format_clean == "json":
            typer.echo(map_res.model_dump_json(indent=2))
        else:
            console_reporter = ConsoleReporter()
            console_reporter.render_skill_map(map_res, target=target)

        raise typer.Exit(code=0)

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
    reload: Annotated[
        bool,
        typer.Option("--reload", help="Enable auto-reload on code changes (development)."),
    ] = False,
) -> None:
    """Start local web interface for Skill Atlas."""
    try:
        from skill_atlas.web import run_server
    except ImportError as err:
        typer.secho(
            "Error: Web dependencies are not installed. Please install with: pip install 'skill-atlas[web]'",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2) from err

    run_server(
        host=host, port=port, open_browser=open_browser, allow_local=allow_local, reload=reload
    )


if __name__ == "__main__":
    app()
