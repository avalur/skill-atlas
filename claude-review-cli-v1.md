# Code Review: Skill Atlas CLI v1 (uncommitted working tree)

**Date**: 2026-09-30
**Scope**: `pyproject.toml`, `src/skill_atlas/**` (19 files, ~1.5k LOC), checked against `SPEC.md` 0.1.0-draft and `AGENTS.md`.
**Method**: Read every file, then ran the CLI against temporary fixtures to confirm each behavioral claim. Findings marked **[verified]** were reproduced by a run. The others come from reading the code.

---

## 1. Summary

The skeleton follows the spec: package layout, Typer CLI, Pydantic models, rule registry, console and JSON reporters, local and remote discovery. The code is easy to read and the module boundaries match `SPEC.md` §6.

The core function is not there yet. **Security rules never look at companion scripts**, the headline `rm -rf /` pattern does not match, several **exit codes are wrong for CI**, and **provenance picks the wrong commit** in common cases. There are no tests, although `AGENTS.md` requires fixtures for every rule.

| Severity | Count |
|---|---|
| Critical (breaks core purpose / CI contract) | 6 |
| Major (wrong results in realistic cases) | 9 |
| Minor (quality, consistency, maintainability) | 11 |

---

## 2. Critical

### C1. Security rules scan only `SKILL.md`, never scripts **[verified]**
`rules/security.py:63,95,124,153,187`: every `SEC-*` rule only runs on `skill.raw_content`, which is the manifest text. `available_files` is collected but no file content is ever read. The spec asks for "dangerous shell patterns in companion scripts" (README, SPEC §3.2), and its example output flags `scripts/install.sh:12`.

*Repro*: `scripts/install.sh` containing `curl … | bash`, `rm -rf /` and `AKIAABCDEFGHIJKLMNOP` gives **0 SEC findings**.

*Fix*: give the rules a list of `(relative_path, text)` for every text file in the skill directory. Skip binaries (NUL byte check), cap file size (e.g. 1 MB) and do not follow symlinks out of the skill directory. The remote GitHub-API path must fetch these files too, or fall back to cloning.

### C2. `SEC-002` misses `rm -rf /` and `rm -rf ~`, but flags `rm -rf /tmp/build` **[verified]**
`rules/security.py:87`: `\brm\s+-rf\s+([/~]|\$HOME)\b`. The trailing `\b` needs a word character after `/` or `~`, so the regex matches only when a path follows. Line by line:

| Input | Expected | Actual |
|---|---|---|
| `rm -rf /` | match | **no match** |
| `rm -rf ~` | match | **no match** |
| `sudo rm -rf /*` | match | **no match** |
| `rm -rf /tmp/build` | no match | **match** |

Variants `rm -fr`, `rm -r -f` and `--no-preserve-root` are also missed.

*Fix*: something like `\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r|-r\s+-f|-f\s+-r)\s+(--no-preserve-root\s+)?(/|~|\$HOME)(\*|/\*)?(\s|$|;|&|\|)`, plus table-driven tests.

### C3. A target that does not exist exits `0` **[verified]**
`discovery/local.py:43` returns `[]` for a missing path, so `skill-atlas scan /nonexistent` prints "Found 0 skills" and exits **0**. SPEC §4.3 says exit code `2`. A typo in a CI config would pass without anyone noticing.

*Fix*: check existence in the CLI (or raise a dedicated `TargetNotFoundError`) and exit 2. Also decide whether "0 skills found" should be an error or at least a warning.

### C4. A failed clone exits `0` **[inferred from code]**
`discovery/remote.py:105-122`: neither clone result is checked. If both attempts fail (bad URL, private repo, no network), the empty temp dir is scanned and the run exits **0**. The second attempt also clones into a directory the first one may have partly filled, so it fails with "destination path already exists".

*Fix*: raise on a non-zero return code (include git's stderr), `rmtree` and recreate the dir before retrying, and map the error to exit 2.

### C5. Crashes exit `1`, which CI reads as "violations found" **[verified]**
The `try/except` in `cli.py:108-116` wraps only the scan. A reporter exception escapes to Typer, which prints a traceback and exits **1**. Example: a SKILL.md with `description: "… [/bold] …"` crashes with `rich.errors.MarkupError` (see M1). CI cannot distinguish that from real findings.

*Fix*: wrap rendering too, or add a top-level handler that turns any unexpected exception into exit 2.

### C6. Argument injection into `git clone` **[inferred from code]**
`discovery/remote.py:106,115` passes the user's URL as a positional argument with no `--` in front. `is_remote_target` (`remote.py:18`) accepts any string that ends in `.git`, so `--upload-pack=<cmd>;.git` is treated as a URL and reaches git as an **option**. This matters when the target comes from untrusted input, such as a CI matrix built from a registry or a web wrapper around the CLI.

*Fix*: `["git", "clone", …, "--", url, tmp_dir]`, accept only an allowlist of schemes (`https://`, `ssh://`, `git@host:`), and reject targets that start with `-`.

---

## 3. Major

### M1. Untrusted skill content is rendered as Rich markup **[verified]**
`reporters/console.py:28,31,38,59` interpolate `skill.name`, `description` and finding messages (which quote matched file content) into markup strings. A skill can crash the reporter (C5) or restyle its own output, e.g. print a fake green `[PASS]` or inject `[link=…]`. That is a real problem for a security scanner.

*Fix*: wrap untrusted values with `rich.markup.escape()`, or build `rich.text.Text` objects. Also strip ANSI and other control characters.

### M2. Provenance returns the **latest** add, not the first **[verified]**
`git/client.py:86`: `git log` lists newest first, so `--diff-filter=A -1` returns the most recent commit that added the file. After an add → delete → re-add history, the tool reports the re-add (2023) instead of the original (2020). The fallback at `:98` is worse: without `--diff-filter` it returns the last commit that *touched* the file.

*Fix*: drop `-1`, take the **last** line of the output (or use `--reverse` and take the first), and apply the same rule in the fallback. Decide in the spec whether "first introduced" means the original add or the add of the current lineage.

### M3. Shallow clone makes remote provenance meaningless **[inferred from code]**
`remote.py:106,115` clone with `--depth 1`, so every skill gets the HEAD commit as its "introducing" commit. `SPEC.md` §7 phase 2 also says "shallow/temporary clone", which contradicts §3.1.

*Fix*: use `--filter=blob:none` without `--depth`. That downloads the full history but no file contents. Note that `--follow` rename detection lazily fetches blobs, so consider dropping `--follow` or making it optional. Update the SPEC wording.

### M4. GitHub API provenance is wrong for files with more than 30 commits **[inferred from code]**
`git/github.py:72-77` reads only the first page of `/commits?path=` (30 items, newest first) and takes `commits[-1]`. That is the oldest commit on page 1, not the oldest overall. Other problems in the same code:
- `path` is not URL-encoded.
- The tree response's `truncated: true` flag is ignored (`github.py:52-55`), so large repos silently lose skills.
- One provenance request per skill against a 60 req/h unauthenticated limit. A medium-size repo hits the limit, and the whole API path then silently falls back to a shallow clone (M3).

*Fix*: follow the `Link: rel="last"` header and read the last page, handle `truncated`, and quote paths. For v1, consider dropping the API path and using a single `blob:none` clone as the only remote strategy. It is simpler, gets provenance right, and makes C1 (reading scripts) easy.

### M5. Private repos fail when a token is set **[inferred from code]**
`github.py:61-66`: raw downloads from `raw.githubusercontent.com` are sent without `Authorization`. For a private repo the API calls succeed with the token, but every manifest fetch returns 404. Each skill then gets `SCH-001` + `SCH-002` + 2× `SCH-003` false errors.

*Fix*: send the token to raw downloads too, or use the contents API (`/repos/{o}/{r}/contents/{path}` with `Accept: application/vnd.github.raw`).

### M6. `SCH-006` path normalisation is wrong **[verified]**
`rules/schema.py:158,161`: `str.lstrip("./")` strips **characters**, not a prefix.
- `../shared/x.md` becomes `shared/x.md`, so a reference outside the skill directory resolves against the wrong place.
- A link to a directory (`[docs](scripts/)`) is always reported as broken, because `available_files` contains only files **[verified]**.
- URL-encoded targets (`my%20file.md`), `<angle bracket>` targets and `file:`/`data:` schemes are not handled.
- Links inside fenced code blocks are counted as references.

*Fix*: use `posixpath.normpath` and check the result on disk relative to the skill directory. Directories count as existing. Flag paths that escape the skill root separately (it could be a new rule). Strip code fences before extracting links.

### M7. Duplicate skills on case-insensitive filesystems **[verified]**
On macOS, a skill whose manifest is `skill.md` is reported **twice**. `local.py:57-59` adds `target/"SKILL.md"` (`is_file()` succeeds because the FS ignores case), then `os.walk` adds `target/skill.md`, and the two `Path`s compare as different. The direct check is redundant with the walk anyway.

*Fix*: remove the direct check and deduplicate with `os.path.samefile` / `Path.resolve()`. Make the accepted spellings the same everywhere: the API path in `remote.py:31` accepts `SKILL.md` and `*/skill.md` but not a root-level `skill.md`.

### M8. `--verbose` does nothing **[inferred from code]**
`cli.py:82-89` declares the option but never uses it. The spec says it should include passed checks.

### M9. `[PASS]` / `Passed` disagree with `--fail-on warn` **[verified]**
`Skill.valid` only looks at `ERROR` (`models.py:47`). With `--fail-on warn`, a skill that has only warnings shows `[PASS]` and "Passed: 1" while the run ends with `Status: FAILED (Exit Code 1)`.

*Fix*: compute pass/fail from the threshold in one place (e.g. `ScanResult.is_failing(threshold)`, `Skill.status(threshold)`).

---

## 4. Minor

1. **No tests.** `tests/` does not exist, and `pytest` collects nothing and exits 0 with a config warning. `AGENTS.md` #5 requires positive and negative fixtures for each rule. Tests for C2, M2, M6 and M7 would have caught those bugs.
2. **Lint and format.** `ruff check` reports 51 issues (unsorted imports, unused imports, blind `except`, mutable class defaults, `Optional`/`List` instead of PEP 604/585). `ruff format --check` would reformat 6 files. The rule set comes from a global ruff config, so pin `[tool.ruff.lint] select = [...]` in `pyproject.toml` to make results the same for everyone.
3. **Duplicated exit-code logic** in `cli.py:127-133` and `console.py:74-78`. A reporter should not decide exit codes. Compute once and pass it in.
4. **Too many errors for one problem.** An unreadable or unparsable manifest produces `SCH-001` + `SCH-002` + 2× `SCH-003`. `SCH-001` fires only on a read error (e.g. non-UTF-8) and its message says "missing", which is misleading. Skip the field checks when parsing fails, and rename `SCH-001` or fold it into `SCH-002`.
5. **`SCH-004` checks the fallback name.** When `name` is missing, it validates the directory name, so users see a warning about a name they never wrote. Check only `frontmatter["name"]`.
6. **Inconsistent `Finding.file`**: `SCH-001` uses `f"{skill.path}/SKILL.md"`, every other rule uses `"SKILL.md"`. Pick one convention: relative to the skill dir, or relative to the scan root, which is better for CI annotations.
7. **Secret masking relies on label text** (`security.py:26`: `"Secret" in desc or "Token" in desc …`). Renaming a label turns masking off. Put a `mask: bool` on each pattern. The `sk-` pattern is labelled "OpenAI" but also matches Anthropic `sk-ant-…` keys. Also consider `github_pat_…`, Google `AIza…` and generic `api_key = "…"` patterns.
8. **Regex false positives and negatives in `SEC-003`/`SEC-004`** **[verified]**:
   - `curl … | shasum` is flagged (the regex needs `\b` after `sh`).
   - `curl … | sudo bash`, `bash <(curl …)` and `sh -c "$(curl …)"` are missed.
   - `cat ~/.ssh` is missed because the regex needs a trailing slash.
9. **Runtime-only fields on the public model.** `raw_content`, `frontmatter`, etc. live on `Skill` and `JsonReporter` removes them with a hand-written exclude list. Use `Field(exclude=True)`, or split into an internal `SkillContext` and a public `Skill`. `ScanSummary.findings_count` should be a typed model, not `dict[str, int]`.
10. **Version string hard-coded** in `models.py:61`, `scanner.py:71` and `github.py:21`. Use `skill_atlas.__version__`.
11. **Assorted**:
    - A local directory named `foo.git` is treated as remote (`remote.py:18`).
    - Subprocess calls have no `timeout`, and `GIT_TERMINAL_PROMPT=0` is not set, so a private-repo clone can hang in CI waiting for credentials.
    - One `git log --follow` process per skill is slow on large repos.
    - `typing_extensions` is imported but not declared (Python 3.11 has `typing.Annotated`).
    - `has_frontmatter` is computed and never used.
    - Invalid `--format`/`--fail-on`/`--rules` values are validated by hand; `Enum`/`Literal` parameters would give validation, help text and exit 2 for free.
    - Unknown `--ignore` IDs are accepted without a warning.
    - One rule that raises aborts the whole scan. Isolate rules and report the failure as an internal finding.
    - `httpx` and the GitHub API client are not in the `AGENTS.md` tech stack or the SPEC. Either document them or drop them (see M4).

---

## 5. Spec-level notes (for `SPEC.md` discussion)

- **Provenance semantics** (M2, M3): define "first introduced" for the delete/re-add and rename cases, and remove "shallow clone" from §7.
- **Which files the SEC rules scan** (C1): the SPEC should list the file set, size cap, binary handling and symlink policy.
- **Name format**: the Agent Skills convention is lowercase letters, digits and hyphens, at most 64 characters, and usually the same as the directory name. `^[a-z0-9_-]+$` allows `_` and has no length limit.
- **Zero skills found**: decide whether that is exit 0, a warning or exit 2.
- **`.junie` in the ignore list** could hide real skills stored under agent config dirs (`.claude/skills/`, `.junie/…`). Confirm this is intended.

---

## 6. Suggested fix order

1. Tests and fixtures for the current rules. Pin the ruff config.
2. Exit-code contract: C3, C4, C5 and a single threshold computation (M9, minor #3).
3. Scan companion scripts (C1) and fix the `SEC-002`/`SEC-003`/`SEC-004` regexes (C2, minor #8).
4. Escape untrusted output (M1) and harden `git clone` (C6, timeouts, `GIT_TERMINAL_PROMPT=0`).
5. Provenance: a single `blob:none` clone and the right `git log` selection (M2, M3). Then decide whether to keep the GitHub API path (M4, M5).
6. Rewrite `SCH-006` (M6), deduplicate discovery (M7), wire up `--verbose` (M8), then the remaining minor items.
