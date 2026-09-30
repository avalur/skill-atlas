# Rules Taxonomy, Layouts & Similarity

This document summarizes the validation rules, origin layouts, and similarity scoring mechanisms implemented in `Skill Atlas`.

## 1. Rule Catalog

### Schema Rules (`SCH`)
| Rule ID | Severity | Name | Description & Checks |
|---|---|---|---|
| `SCH-001` | `ERROR` | Valid Frontmatter | `SKILL.md` must start with valid YAML frontmatter between `---` delimiters. |
| `SCH-002` | `ERROR` | Valid Skill Name | Name must be lowercase-hyphenated (`^[a-z0-9]+(-[a-z0-9]+)*$`). |
| `SCH-003` | `ERROR` | Required Fields | Frontmatter must contain non-empty `name` and `description`. |
| `SCH-004` | `ERROR` | Non-Empty Body | The markdown body after frontmatter must not be blank. |
| `SCH-005` | `WARN`  | Description Quality | Description must be between 10 and 1024 characters. |
| `SCH-006` | `ERROR` | Broken Link References | Referenced markdown links, scripts, and docs must exist in the skill directory or repository tree. |

### Security Rules (`SEC`)
| Rule ID | Severity | Name | Description & Checks |
|---|---|---|---|
| `SEC-001` | `ERROR` | Hardcoded Secrets | Detects high-entropy API keys (OpenAI, AWS, GitHub tokens, private keys). |
| `SEC-002` | `ERROR` | Dangerous Commands | Detects destructive shell commands (`rm -rf /`, `rm -rf ~`, `mkfs`, fork bombs). |
| `SEC-003` | `ERROR` | Unsafe Piping | Detects piped downloads (`curl ... \| bash`, `wget ... \| sh`, unverified pip installs). |
| `SEC-004` | `WARN`  | Sensitive Paths | Detects references to credentials paths (`/etc/shadow`, `~/.ssh/id_*`, `/etc/passwd`). |
| `SEC-005` | `ERROR` | Prompt Injection | Detects injection vectors (`ignore previous instructions`, `bypass safety protocols`). |

### Discovery Rules (`DSC`)
| Rule ID | Severity | Name | Description & Checks |
|---|---|---|---|
| `DSC-001` | `WARN`  | Stale Duplicate | Emitted when duplicate mirror copies of a skill have divergent content hashes. |

## 2. Layouts & Origin Classification

The scanner classifies skill paths into four primary origins (`SkillOrigin`):
1. **`agent-config`**: Skills configured for AI agents (`.claude/skills`, `.agents/skills`, `.junie`, `.cursor`, `.codex`, `.github/skills`).
   - *Behavior*: Duplicate copies with identical names are treated as mirrors; the newest version is displayed, with `DSC-001` raised if out of sync.
   - *Repository Skills*:
     - `shared-memory`: Persistent cross-session project memory management.
     - `browser-video-tester`: Autonomous human-like QA browser testing with live MP4 video recording and self-eval reporting.
2. **`product`**: Skills bundled as end-user application features (`src/main/resources`, `resources/`, `plugins/*/`, `languages/*/`).
   - *Behavior*: Same-named skills in distinct plugins remain separate entities and are never merged.
3. **`test-data`**: Synthetic skills in test suites (`tests/`, `testData/`, `fixtures/`).
   - *Behavior*: Excluded from failing scan runs by default (return exit code `0`), unless `--include-test-data` is explicitly passed.
4. **`standalone`**: Any skill directory not matching the patterns above.

## 3. Similarity Algorithm
The `similar` command and web panel calculate similarity using composite scoring:
- $S_{name} = \text{Jaccard}(\text{tokens}_A, \text{tokens}_B) \times 0.25$
- $S_{desc} = \text{Cosine}(\text{TF-IDF}_A, \text{TF-IDF}_B) \times 0.35$
- $S_{tags} = \text{Jaccard}(\text{tags}_A, \text{tags}_B) \times 0.15$
- $S_{struct} = \text{Jaccard}(\text{headings}_A, \text{headings}_B) \times 0.15$
- $S_{scripts} = \text{Jaccard}(\text{scripts}_A, \text{scripts}_B) \times 0.10$

$S_{composite} = S_{name} + S_{desc} + S_{tags} + S_{struct} + S_{scripts}$
Matches with $S_{composite} \ge \text{threshold}$ are reported.
