"""Console reporter formatting results using Rich."""

from rich.console import Console
from rich.rule import Rule as RichRule

from skill_atlas.models import ScanResult, Severity


class ConsoleReporter:
    """Renders human-readable scan reports to the terminal using Rich."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def render(self, result: ScanResult, fail_on: str = "error") -> None:
        target_display = result.target
        repo_extra = ""
        # Check if first skill has repo_name
        if result.skills and result.skills[0].repo_name:
            repo_extra = f" (repo: {result.skills[0].repo_name})"

        self.console.print(f"[bold]🔍 Scanning skills in:[/bold] {target_display}{repo_extra}")
        self.console.print(f"Found {result.summary.total_skills} skills...\n")

        for skill in result.skills:
            # Determine status based on findings
            status_text = (
                "[bold red][FAIL][/bold red]"
                if not skill.valid
                else "[bold green][PASS][/bold green]"
            )
            self.console.print(f"{status_text} [bold]{skill.name}[/bold]")

            if skill.repo_name:
                self.console.print(f"  [dim]Repo:[/dim]        {skill.repo_name}")

            if skill.commit:
                date_part = f" ({skill.commit_date})" if skill.commit_date else ""
                self.console.print(f"  [dim]Commit:[/dim]      {skill.commit}{date_part}")

            if skill.description:
                self.console.print(f"  [dim]Description:[/dim] {skill.description}")

            self.console.print(f"  [dim]Path:[/dim]        {skill.path}")

            if not skill.findings:
                self.console.print("  [green]✅ All checks passed[/green]\n")
            else:
                for f in skill.findings:
                    if f.severity == Severity.ERROR:
                        icon = "❌ [bold red][ERROR][/bold red]"
                    elif f.severity == Severity.WARN:
                        icon = "⚠️  [bold yellow][WARN][/bold yellow] "
                    else:
                        icon = "ℹ️  [bold blue][INFO][/bold blue] "

                    loc = ""
                    if f.file:
                        loc = f" in {f.file}"
                        if f.line is not None:
                            loc += f":{f.line}"

                    self.console.print(f"  {icon} {f.rule_id}: {f.message}{loc}")
                self.console.print()

        self.console.print(RichRule(style="dim"))
        self.console.print("[bold]Summary:[/bold]")
        self.console.print(f"  Scanned Skills: {result.summary.total_skills}")
        self.console.print(f"  Passed: {result.summary.passed}")
        self.console.print(f"  Failed: {result.summary.failed}")
        counts = result.summary.findings_count
        self.console.print(
            f"  Total Findings: {sum(counts.values())} "
            f"({counts.get('error', 0)} Error, {counts.get('warn', 0)} Warning, {counts.get('info', 0)} Info)"
        )

        # Status & Exit code indication
        has_blocking = (
            result.summary.findings_count.get("error", 0) > 0
            if fail_on == "error"
            else (
                result.summary.findings_count.get("error", 0)
                + result.summary.findings_count.get("warn", 0)
                > 0
            )
        )

        if has_blocking:
            self.console.print("[bold red]Status: FAILED (Exit Code 1)[/bold red]")
        else:
            self.console.print("[bold green]Status: SUCCESS (Exit Code 0)[/bold green]")
