"""Console reporter formatting results using Rich."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from rich.console import Console
from rich.markup import escape
from rich.rule import Rule as RichRule

from skill_atlas.models import ScanResult, Severity
from skill_atlas.similarity import SimilarSkillsResult

if TYPE_CHECKING:
    from skill_atlas.map import SkillMapResult

ANSI_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _sanitize(text: str) -> str:
    """Strip ANSI escape characters and escape Rich markup."""
    clean_text = ANSI_PATTERN.sub("", text)
    return escape(clean_text)


class ConsoleReporter:
    """Renders human-readable scan reports to the terminal using Rich."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def render(
        self,
        result: ScanResult,
        fail_on: str = "error",
        include_test_data: bool = False,
        verbose: bool = False,
    ) -> None:
        target_display = _sanitize(result.target)
        repo_extra = ""
        # Check if first skill has repo_name
        if result.skills and result.skills[0].repo_name:
            repo_extra = f" (repo: {_sanitize(result.skills[0].repo_name)})"

        self.console.print(f"[bold]🔍 Scanning skills in:[/bold] {target_display}{repo_extra}")
        self.console.print(f"Found {result.summary.total_skills} skills...\n")

        for skill in result.skills:
            # Determine status based on findings, fail_on threshold, and origin
            is_pass = skill.is_passing(fail_on, include_test_data=include_test_data)
            status_text = (
                "[bold green][PASS][/bold green]" if is_pass else "[bold red][FAIL][/bold red]"
            )
            origin_badge = f" [cyan]({skill.origin.value})[/cyan]"
            self.console.print(f"{status_text} [bold]{_sanitize(skill.name)}[/bold]{origin_badge}")

            if skill.duplicates:
                total_copies = len(skill.duplicates) + 1
                self.console.print(f"  [magenta]⧉ duplicated ({total_copies} copies)[/magenta]")
                for dup in skill.duplicates:
                    date_info = f" ({_sanitize(dup.updated_date)})" if dup.updated_date else ""
                    diff_info = "identical" if dup.identical else "differs"
                    self.console.print(
                        f"    [dim]also at:[/dim] {_sanitize(dup.path)}{date_info} [dim][{diff_info}][/dim]"
                    )

            if skill.repo_name:
                self.console.print(f"  [dim]Repo:[/dim]        {_sanitize(skill.repo_name)}")

            if skill.commit:
                date_part = f" ({_sanitize(skill.commit_date)})" if skill.commit_date else ""
                self.console.print(
                    f"  [dim]Commit:[/dim]      {_sanitize(skill.commit)}{date_part}"
                )

            if skill.updated_date:
                updated_part = f" ({_sanitize(skill.updated_date)})" if skill.updated_date else ""
                commit_part = f"{_sanitize(skill.updated_commit)}" if skill.updated_commit else ""
                self.console.print(f"  [dim]Updated:[/dim]     {commit_part}{updated_part}")

            if skill.description:
                self.console.print(f"  [dim]Description:[/dim] {_sanitize(skill.description)}")

            self.console.print(f"  [dim]Path:[/dim]        {_sanitize(skill.path)}")

            if not skill.findings:
                if verbose:
                    self.console.print(
                        "  [green]✅ All checks passed (no findings detected)[/green]\n"
                    )
                else:
                    self.console.print("  [green]✅ All checks passed[/green]\n")
            else:
                for f in skill.findings:
                    if f.severity == Severity.ERROR:
                        icon = "❌ [bold red][ERROR][/bold red]"
                    elif f.severity == Severity.WARN:
                        icon = "⚠️  [bold yellow][WARN][/bold yellow] "
                    else:
                        icon = "ℹ️  [bold blue][INFO][/bold blue] "  # noqa: RUF001

                    loc = ""
                    if f.file:
                        loc = f" in {_sanitize(f.file)}"
                        if f.line is not None:
                            loc += f":{f.line}"

                    self.console.print(f"  {icon} {f.rule_id}: {_sanitize(f.message)}{loc}")
                    if verbose and f.suggestion:
                        self.console.print(
                            f"      [dim]Suggestion: {_sanitize(f.suggestion)}[/dim]"
                        )
                self.console.print()

        if result.warnings:
            self.console.print("[bold yellow]⚠️  Warnings:[/bold yellow]")
            for w in result.warnings:
                self.console.print(f"  [yellow]• {_sanitize(w)}[/yellow]")
            self.console.print()

        self.console.print(RichRule(style="dim"))
        self.console.print("[bold]Summary:[/bold]")
        self.console.print(f"  Scanned Skills: {result.summary.total_skills}")
        self.console.print(f"  Passed: {result.summary.passed}")
        self.console.print(f"  Failed: {result.summary.failed}")
        by_origin = result.summary.by_origin
        self.console.print(
            f"  Origins: Agent config: {by_origin.get('agent-config', 0)}, "
            f"Product: {by_origin.get('product', 0)}, "
            f"Standalone: {by_origin.get('standalone', 0)}, "
            f"Test data: {by_origin.get('test-data', 0)}"
        )
        counts = result.summary.findings_count
        self.console.print(
            f"  Total Findings: {sum(counts.values())} "
            f"({counts.get('error', 0)} Error, {counts.get('warn', 0)} Warning, {counts.get('info', 0)} Info)"
        )

        # Status & Exit code indication computed consistently
        has_blocking = result.has_failures(fail_on, include_test_data=include_test_data)
        if has_blocking:
            self.console.print("[bold red]Status: FAILED (Exit Code 1)[/bold red]")
        else:
            self.console.print("[bold green]Status: SUCCESS (Exit Code 0)[/bold green]")

    def render_similarity(
        self,
        result: SimilarSkillsResult,
        verbose: bool = False,
    ) -> None:
        target_display = _sanitize(result.target)
        self.console.print(
            f"[bold]🔍 Finding similar skills in:[/bold] {target_display} "
            f"[dim](threshold: {result.threshold:.2f}, total skills: {result.total_skills})[/dim]\n"
        )
        if not result.matches:
            self.console.print("  [dim]No similar skills found matching the criteria.[/dim]\n")
        else:
            for match in result.matches:
                score_pct = round(match.score * 100)
                if score_pct >= 80:
                    score_badge = f"[bold green]{score_pct}%[/bold green]"
                elif score_pct >= 60:
                    score_badge = f"[bold yellow]{score_pct}%[/bold yellow]"
                else:
                    score_badge = f"[cyan]{score_pct}%[/cyan]"

                self.console.print(
                    f"• [bold]{_sanitize(match.skill_a)}[/bold] [dim]({_sanitize(match.skill_a_path)})[/dim] "
                    f"↔ [bold]{_sanitize(match.skill_b)}[/bold] [dim]({_sanitize(match.skill_b_path)})[/dim] "
                    f"— Similarity: {score_badge}"
                )
                for r in match.reasons:
                    self.console.print(f"    [dim]↳ {_sanitize(r)}[/dim]")

                if verbose:
                    b = match.breakdown
                    self.console.print(
                        f"    [dim]Breakdown: name={b.name:.2f}, desc={b.description:.2f}, "
                        f"tags={b.tags:.2f}, body={b.body:.2f}, files={b.files:.2f}[/dim]"
                    )
                self.console.print()

        self.console.print(RichRule(style="dim"))
        self.console.print(
            f"[bold]Summary:[/bold] Found {len(result.matches)} similar skill match(es) "
            f"across {result.total_skills} skills."
        )

    def render_skill_map(
        self,
        result: SkillMapResult,
        target: str = ".",
    ) -> None:
        target_display = _sanitize(target)
        if result.method == "ai":
            method_badge = "[bold cyan]AI (Claude)[/bold cyan]"
        elif result.method == "jev":
            method_badge = "[bold magenta]AI (TypeSafe Jev)[/bold magenta]"
        else:
            method_badge = "[bold yellow]Heuristic (Shared Words)[/bold yellow]"

        replayed_badge = " [dim](replayed)[/dim]" if result.replayed else ""
        self.console.print(
            f"[bold]🗺️  Skill Map for:[/bold] {target_display} "
            f"— Method: {method_badge}{replayed_badge} [dim]({result.total_skills} skills, {len(result.clusters)} clusters)[/dim]\n"
        )

        for idx, cluster in enumerate(result.clusters, 1):
            skills_count = len(cluster.skills)
            self.console.print(
                f"[bold cyan]{idx}. {cluster.name}[/bold cyan] "
                f"[dim]({skills_count} skill{'s' if skills_count != 1 else ''})[/dim]"
            )
            self.console.print(f"   [dim]↳ Reason: {_sanitize(cluster.reason)}[/dim]")
            skills_str = ", ".join(f"[bold]{_sanitize(s)}[/bold]" for s in cluster.skills)
            self.console.print(f"   [dim]↳ Skills:[/dim] {skills_str}\n")

        self.console.print(RichRule(style="dim"))
        self.console.print(
            f"[bold]Summary:[/bold] Grouped {result.total_skills} skill(s) into "
            f"{len(result.clusters)} cluster(s)."
        )
