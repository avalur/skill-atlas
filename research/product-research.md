# Product Research: Skill Atlas

**Date**: 2026-10-01
**Scope**: workshop task "Product research", steps 1 (existing tools) and 2 (ideas).
**Companion**: [`finance-skills.md`](finance-skills.md), a focused study of finance skills (personal, organizations, public sector) with scans of seven finance repositories.
**Method**: two parallel web-research passes, one on catalogs and registries and one on scanners, validators and studies. A tool is listed only if its page was opened and confirmed. The headline numbers (arXiv 2601.10338, Vercel *State of Agent Skills*, Snyk ToxicSkills, Cisco skill-scanner, SkillsMP, NVIDIA SkillSpector) were then re-checked against the primary source. Claims seen only in search snippets are marked *unverified*. Counts and dates are as stated by each source on the access date.

---

## 1. Existing tools: who else indexes agent skills?

### 1.1 Catalogs, registries and marketplaces

| Tool | What it indexes, and how | Scale (as stated) | Quality / security checks | How it differs from Skill Atlas | Source |
|---|---|---|---|---|---|
| **skills.sh** + Vercel `skills` CLI | Open directory and leaderboard ranked by installs. Install with `npx skills add owner/repo`; the CLI supports ~80 agents and sends anonymous install telemetry | "one million agent skills", "nearly 280 million installs" (report of 2026-09-25) | `/audits` shows third-party ratings from Gen Agent Trust Hub, Socket and Snyk, and many are still "pending". The CLI requires `name` and `description` | Ranks by popularity, and the security verdict comes from outside vendors. No structural lint, no git provenance, no duplicate detection | [skills.sh](https://skills.sh), [skills.sh/audits](https://skills.sh/audits), [State of Agent Skills](https://vercel.com/blog/state-of-agent-skills), [vercel-labs/skills](https://github.com/vercel-labs/skills) |
| **SkillsMP** | Aggregates SKILL.md files "from public GitHub repositories" into 12 domains and 800+ occupations. Has a REST API and an MCP server | "3M+ skills" | None. It "does not rush to judge skills" and tells users to "Always review code before installation." Deduplication is not mentioned | The largest crawl, with no quality, security or duplicate analysis | [skillsmp.com/about](https://skillsmp.com/about) |
| **Claude plugin directory** and Claude Code marketplaces | A curated directory of plugins (bundles of skills, tools and integrations), submitted through a portal and reviewed per version. Anyone can also host a git-based marketplace (`marketplace.json`) | 340 plugins on the page | `claude plugin validate` checks manifest and marketplace JSON (fields, naming, `..` paths). There is an "Anthropic verified" badge whose criteria are not stated. SKILL.md content is not audited | A submission-based plugin catalog that validates manifests, not the skill content | [claude.com/plugins](https://claude.com/plugins), [Publish docs](https://code.claude.com/docs/en/plugins/publish), [Marketplace docs](https://code.claude.com/docs/en/plugin-marketplaces) |
| **anthropics/skills** | Anthropic's official example skills plus the spec and a template. Also works as a Claude Code marketplace | Not stated, ~179k stars | None. The skills are marked as demonstration-only | A single first-party source | [github.com/anthropics/skills](https://github.com/anthropics/skills), [Anthropic engineering post](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) |
| **agentskills.io** | The open Agent Skills specification and a showcase of ~45 adopting clients (Claude Code, Codex, Cursor, Copilot, Junie, Gemini CLI, …) | n/a, it lists no skills | The spec defines the rules, and the `skills-ref` validator ships separately (§1.2) | The standard that Skill Atlas validates against, not an index | [agentskills.io](https://agentskills.io) |
| **Smithery**, Skills section | Hosted catalog of `publisher/name` entries with install counts and 12 categories. The rest of the site is about MCP servers | 24,005 skills on the page | A "Verified" badge and filter; what it checks is not stated | An opaque badge, no audit output, no similarity | [smithery.ai/skills](https://smithery.ai/skills) |
| **ClawHub** (OpenClaw) | Publish-gated registry (`clawhub skill publish`) | Not stated on the page. 49,592 skills (Apr 2026) per search snippets, *unverified* | Every release is SHA-256 hashed and scanned by VirusTotal Code Insight (LLM-based). Malicious skills are blocked, and all skills are rescanned daily | The strongest gate, but for one ecosystem and only at publish time. It cannot see skills that already sit in arbitrary GitHub repos | [clawhub.ai](https://clawhub.ai), [VirusTotal partnership](https://openclaw.ai/blog/virustotal-partnership) |
| **NVIDIA Verified Agent Skills** | First-party skills, mirrored daily from NVIDIA product repos | ~47 product areas | Each skill is scanned by SkillSpector, signed with OpenSSF Model Signing (`skill.oms.sig`), and ships a `skill-card.md` (ownership, provenance, risks) plus an eval benchmark | The most rigorous provenance model on the market, but it covers NVIDIA's own skills only | [github.com/nvidia/skills](https://github.com/nvidia/skills), [NVIDIA blog](https://developer.nvidia.com/blog/nvidia-verified-agent-skills-provide-capability-governance-for-ai-agents/) |
| **openai/plugins** (formerly `openai/skills`) | Curated Codex plugins, which can contain `skills/`. `openai/skills` is deprecated | Not stated | Not stated | A vendor catalog for one agent | [openai/plugins](https://github.com/openai/plugins), [openai/skills](https://github.com/openai/skills) |
| **cursor/plugins** | Cursor plugin spec plus a marketplace of first- and third-party plugins | 86 plugins in the README table. Skill Atlas found 101 skills in it (§1.4) | JSON schemas and a scaffold/validate tool, no security review described | A single-vendor marketplace with schema checks | [github.com/cursor/plugins](https://github.com/cursor/plugins) |
| **github/awesome-copilot** + `gh skill` | Community collection of agents, instructions, skills and plugins, plus an installer. GitHub docs point here and to anthropics/skills | "hundreds of resources", ~39.6k stars | Schemas and spellcheck. Users are told to inspect skills before installing | A curated list plus an installer | [awesome-copilot](https://github.com/github/awesome-copilot), [GitHub docs](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills) |
| **claude-plugins.dev** | Community registry of plugins and skills with an `npx` installer | Not stated | Not stated | Optimized for installing, with no auditing | [claude-plugins.dev](https://claude-plugins.dev) |
| **VoltAgent/awesome-agent-skills** | Hand-curated list of official vendor and community skills | "1000+" | None | A manual awesome-list | [github.com/VoltAgent/awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills) |

### 1.2 Scanners and validators (direct competitors)

| Tool | Type | What it checks | Input scope | How it differs from Skill Atlas | Source |
|---|---|---|---|---|---|
| **Cisco AI Defense skill-scanner** | OSS CLI / SDK / API / GitHub Action, Apache-2.0 | YAML and YARA-X patterns, shell taint analysis, Python AST dataflow, source-to-sink correlation, optional LLM-as-judge and VirusTotal. SARIF output. `scan-all --check-overlap` compares descriptions across skills. Its own benchmark: F1 47.7%, recall 31.4%. On a source-disjoint split, recall drops to **7.75%**. "No findings ≠ no risk" | One skill, a directory tree, or one GitHub repo (`scan-repo`) | Much deeper detection than ours. No discovery across repos or orgs, no first-commit provenance, and similarity limited to description overlap | [github.com/cisco-ai-defense/skill-scanner](https://github.com/cisco-ai-defense/skill-scanner) |
| **NVIDIA SkillSpector** | OSS CLI / MCP server, Apache-2.0 | 71 patterns in 17 categories (prompt injection, exfiltration, privilege escalation, memory poisoning, …), an optional LLM pass, OSV CVE lookups, a typosquat check on **dependency** names, and a 0–100 risk score. SARIF, JSON and Markdown output. It recognizes `skill.oms.sig` but "does not verify the signature" | A git repo, URL, zip, directory or file. Batch mode works on a local directory | No crawling across repos, no first-commit provenance, no skill-to-skill similarity | [github.com/NVIDIA/SkillSpector](https://github.com/NVIDIA/SkillSpector) |
| **Snyk Agent Scan** (formerly Invariant Labs mcp-scan) | CLI + cloud, Apache-2.0 + Snyk terms | Auto-discovers agent configs on the local machine (Claude, Cursor, VS Code, Copilot, Codex, …). Checks MCP servers for tool poisoning and toxic flows, and skills for prompt injection, malicious code and secrets. Needs `SNYK_TOKEN`, and component content is sent to the Snyk API | Local machine, a config file, a SKILL.md, or a folder | Inventories the endpoint rather than GitHub. Requires the cloud, no provenance, no similarity | [github.com/snyk/agent-scan](https://github.com/snyk/agent-scan) |
| **SkillGuard** | OSS CLI / MCP / Action, Apache-2.0, ~1 month old | 10 rule packs: remote code execution and curl\|bash, path traversal, credential harvesting, frontmatter scope spoofing, hidden-Unicode prompt injection, cross-skill privilege chaining, Levenshtein typosquats | Local paths only | Its rule set overlaps most with ours. No GitHub discovery, no provenance | [github.com/RudrenduPaul/skillguard](https://github.com/RudrenduPaul/skillguard) |
| **skills-ref** (agentskills.io) | Reference validator, Apache-2.0 | Frontmatter and naming rules from the spec. Its README says it is "not meant to be used in production" | One skill | Schema only | [skills-ref](https://github.com/agentskills/agentskills/tree/main/skills-ref), [spec](https://agentskills.io/specification) |
| **Anthropic `quick_validate.py`** | A script inside skill-creator | YAML parses, allowed keys, kebab-case name ≤64 characters, description ≤1024 characters. Stops at the first error | One skill | A minimal sanity check | [quick_validate.py](https://github.com/anthropics/skills/blob/main/skills/skill-creator/scripts/quick_validate.py) |
| **skillcheck** | OSS npm CLI / Action, MIT | 36 structural rules, claims message-for-message parity with skills-ref, SARIF output, one security rule (hidden Unicode) | A file, folder or tree | A structure linter only | [github.com/Sagargupta16/skillcheck](https://github.com/Sagargupta16/skillcheck) |
| **skill-lint** | OSS CLI, MIT, early | 11 structural rules (frontmatter, references, name matches directory, body size) | Recursive search from the working directory | A structure linter only | [github.com/duoluoxi123/skill-lint](https://github.com/duoluoxi123/skill-lint) |

### 1.3 Evidence of the problem (studies and incidents)

| Source | Dataset | Key findings |
|---|---|---|
| Liu et al., *Agent Skills in the Wild*, arXiv:2601.10338 (2026-01-15) | 42,447 skills from two marketplaces, 31,132 analyzed | **26.1%** have at least one vulnerability, **5.2%** show high-severity patterns suggesting malicious intent, and skills with scripts are 2.12× more likely to be vulnerable. SkillScan reaches 86.7% precision and 82.5% recall. [arxiv.org/abs/2601.10338](https://arxiv.org/abs/2601.10338) |
| Liu et al., *"Do Not Mention This to the User"*, arXiv:2602.06547 (USENIX Security 2026) | 98,380 skills from two registries | 157 confirmed malicious skills. **More than half trace back to a single actor using templated brand impersonation.** All were removed after disclosure. [arxiv.org/abs/2602.06547](https://arxiv.org/abs/2602.06547) |
| Snyk, *ToxicSkills* (2026-02-05) | 3,984 skills from ClawHub and skills.sh | **36.82%** (1,467) have at least one security flaw, **13.4%** (534) have a critical one, 76 malicious payloads were confirmed, and daily submissions grew from <50 to >500. Pain point quoted: "A SKILL.md Markdown file and a GitHub account that's one week old. No code signing. No security review." [snyk.io](https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub/) |
| Koi Security, *ClawHavoc* (via eSecurity Planet, 2026-02-03) | All 2,857 ClawHub skills | 341 malicious, 335 of them from one campaign (AMOS stealer behind fake "prerequisites", including typosquats). [esecurityplanet.com](https://www.esecurityplanet.com/threats/hundreds-of-malicious-skills-found-in-openclaws-clawhub/) |
| Palo Alto Unit 42 (2026-06-23) | ClawHub, Feb–May 2026, after scanning was added | Five malicious skills still got through. One payload hid behind 22 MB of padding, so VirusTotal reported it clean. "Each case passed existing detection tools at the time of our analysis." [unit42.paloaltonetworks.com](https://unit42.paloaltonetworks.com/openclaw-ai-supply-chain-risk/) |
| Cloud Security Alliance research note (2026-05-06) | Review of SKILL.md context poisoning | Unicode tag characters can hide instructions, poisoned skills persist by writing into CLAUDE.md / AGENTS.md, and single-LLM or regex scanners "could be bypassed". [labs.cloudsecurityalliance.org](https://labs.cloudsecurityalliance.org/research/csa-research-note-skill-md-agent-context-poisoning-20260506/) |
| Vercel, *State of Agent Skills* (2026-09-25) | The skills.sh registry | 375 skills (0.04%) account for 62% of installs, and the top 1.2% for 94%. "Nearly half of all skills were installed exactly once." Popularity is therefore a weak trust signal for the long tail. [vercel.com](https://vercel.com/blog/state-of-agent-skills) |

### 1.4 Where Skill Atlas stands

**Gaps no tool above covers, and where Skill Atlas already plays:**
1. **Discovery across repositories.** Catalogs crawl or accept submissions, and scanners take a path or a single repository. None scans a list of repos, or a whole org, and builds a joint inventory. Skill Atlas does this for multiple targets and, since PR #19, for entire organizations (`org:<name>`, concurrent, no cloning).
2. **Git provenance.** Nobody records the commit where a skill first appeared. NVIDIA signs content, but only its own skills. Skill Atlas records first and last commits.
3. **Similarity and duplicate detection.** At best there are name typosquat checks (SkillGuard) or description overlap (Cisco). Yet more than half of confirmed malicious skills came from **templated** variants by a single actor (arXiv:2602.06547), and SkillsMP counts 3M+ raw files without deduplication. Skill Atlas has similarity scoring and `DSC-001` for drifted copies.
4. **Schema lint, security audit and browsable catalog in one local, token-optional tool.** The linters only lint, the scanners only scan, and no tool offers a local web catalog.

**Where competitors are ahead:**
- Detection depth: AST and dataflow analysis, YARA, LLM judges (Cisco, SkillSpector).
- Output formats: SARIF and code-scanning integration (Cisco, SkillSpector, skillcheck).
- Spec-exact schema rules (skills-ref / skillcheck parity).
- Evasion coverage: hidden Unicode (SkillGuard, skillcheck), oversized-file padding (Unit 42's case).
- Remote scanning beyond GitHub.

**Validation of the gap on real data.** Our own demo scan of `cursor/plugins` + `avalur/skill-atlas` finds 125 skills with 28 findings in about 2 minutes. Find Similar matches the `thermo-nuclear-code-quality-review` pair at 100% across two paths of the same repository (`cursor-team-kit/skills/…` and `thermos/skills/…`), and `pr-review-canvas` at 60% between two directories. Those are exactly the copies that catalogs count as separate skills.

---

## 2. Ideas: five features with impact metrics

Every idea builds on a strength from §1.4 or closes a weakness. Each has one **primary metric**, the result that counts as success, plus a **guardrail** that must not get worse.

### Idea 1. Skill lineage: "Where did this skill come from, and who copied it?"
- **Problem.** Copies, forks and re-templated variants inflate catalogs and spread malicious skills. One actor produced more than half of the confirmed malicious skills (arXiv:2602.06547), and SkillsMP counts 3M+ raw files.
- **Feature.** Combine content fingerprinting (MinHash/SimHash over the normalized SKILL.md body and the companion scripts) with first-commit provenance. Cluster copies, mark the earliest commit as the **origin**, and show a lineage view: origin → copies → drifted variants. A skill that is a near copy of a known-bad skill inherits a warning.
- **Primary metric.** Cluster precision and recall on a labeled set. Build it from the released malicious-skill dataset (arXiv:2602.06547) plus a hand-labeled sample of 200 skill pairs from `cursor/plugins`, `anthropics/skills` and `github/awesome-copilot`. **Success:** precision ≥ 0.9 and recall ≥ 0.8 for "same origin" pairs, and ≥ 80% of the confirmed malicious skills attached to a cluster containing at least one other malicious skill.
- **User metric.** Median time to answer "Is this an original, and where is the origin?" in a moderated test, with and without the lineage view. **Success:** at least 2× faster.
- **Guardrail.** False "copy" labels on independently written skills that solve the same task (≤ 5% of the labeled negatives).

### Idea 2. Change alerts on top of the org-wide inventory (`skill-atlas watch`)
- **Problem.** Every tool needs an explicit path or repository. Security teams cannot answer "Which skills exist across our 400 repos, and which changed this week?" Unit 42 advises users to "verify who published a skill", but no tool keeps that answer up to date.
- **Feature.** The org-wide scan (`org:<name>`) shipped in PR #19. What is still missing is the *change* dimension. A scheduled `watch` mode would store snapshots of each org scan and emit a diff: new skills, deleted skills, changed scripts, newly added network or shell capabilities, and a new author. Notifications go to the console, JSON, or a webhook (Slack).
- **Primary metric.** Coverage against ground truth. For three pilot orgs, compare skills found against a GitHub code search for `filename:SKILL.md` plus manual review. **Success:** ≥ 98% coverage.
- **Secondary metrics.** Median time from the commit that adds or changes a skill to the alert (**success:** ≤ 24 h in scheduled mode). Number of orgs that keep `watch` running for 4+ weeks.
- **Guardrail.** API budget per scan, measured in requests per 100 repos. It must stay inside the 5,000 req/h token quota for orgs with ≤ 500 repos.

### Idea 3. CI-native findings: SARIF, GitHub code scanning and PR annotations
- **Problem.** Competitors already emit SARIF, and teams triage findings in the tools they already use. JSON output plus an exit code is not enough to get adoption in PR review.
- **Feature.** Add `--format sarif` and an official GitHub Action. Findings appear as code-scanning alerts and inline PR comments, with a "new in this PR" mode that needs no baseline.
- **Primary metric.** The share of findings resolved before merge, counting findings introduced in PRs during the pilot. **Success:** ≥ 60% fixed or removed before merge, measured from code-scanning alert states.
- **Secondary metrics.** Number of repositories with the Action installed (adoption), and median time to fix.
- **Guardrail.** The dismissal rate as "false positive" in code scanning must stay ≤ 15%. A higher rate means the rules are too noisy for PR-time use.

### Idea 4. Pre-install trust card for a single skill URL
- **Problem.** Users install skills from skills.sh, ClawHub or SkillsMP based on stars and installs. Installs are extremely concentrated (top 1.2% = 94%), so for the long tail popularity says little about trust. Pain point: "a GitHub account that's one week old. No code signing. No security review." (Snyk)
- **Feature.** `skill-atlas inspect <url>`, plus a web view, produces a one-page card:
  - **provenance**: first commit, author account age, how many repositories carry copies, lineage origin from Idea 1
  - **integrity**: content hash; a signature, if one exists, is verified
  - **capabilities** declared versus actually used (network, shell, file writes outside the skill, writes into CLAUDE.md or AGENTS.md)
  - **audit findings**
  - a **clear verdict** with the reason behind it
- **Primary metric.** Decision accuracy in a controlled test. Colleagues judge 12 skills (a mix of benign skills, flawed ones, and sanitized malicious samples from §1.3) as "install / don't install". One group has the card and the other only has the GitHub page. **Success:** ≥ 25 percentage points higher accuracy with the card, and no loss in decision time.
- **Secondary metric.** Self-reported confidence calibration: the gap between stated confidence and actual correctness gets smaller.
- **Guardrail.** Benign skills wrongly rejected (≤ 10%), so the card does not just teach people to say "no".

### Idea 5. Evasion-resistant rules: hidden Unicode, padding, context-file persistence
- **Problem.** Real attacks bypass today's scanners in four documented ways:
  - **Unicode tag characters** that hide instructions (CSA)
  - **oversized-file padding**: a 22 MB pad got past VirusTotal (Unit 42)
  - **persistence by writing into CLAUDE.md / AGENTS.md** (CSA)
  - **frontmatter scope spoofing**, where a skill declares harmless tools but its scripts do more
- **Feature.** Add new `SEC` rules for each vector:
  - invisible and bidirectional Unicode in any text file
  - an "oversized or padded file" rule that scans the head and tail instead of skipping the file
  - writes to agent context files (CLAUDE.md, AGENTS.md, `.cursor/rules`, …)
  - declared `allowed-tools` versus capabilities observed in scripts

  Each rule ships with positive and negative fixtures, as `AGENTS.md` requires.
- **Primary metric.** Recall on an evasion benchmark built from the documented cases plus generated variants (≥ 50 samples). **Success:** ≥ 90% recall, against a baseline of current Skill Atlas and the competitors run on the same set.
- **Guardrail.** No more than 1 new finding per 100 skills on popular benign corpora (`anthropics/skills`, `cursor/plugins`, `nvidia/skills`), checked in CI with pinned network tests.

### Recommendation for step 3 ("Mock up the most promising one")
**Idea 4 (pre-install trust card)** is the best candidate to mock up and test with colleagues:
- It fits the "with the mockup and without it" protocol directly: the same 12 skills are judged by two groups, one with the card and one without.
- It reuses what Skill Atlas already computes (provenance, findings, similarity), so even a static mockup is realistic.
- It addresses the most widely cited pain point: installing unknown skills on trust.

Ideas 1 and 5 feed the card's content later. Ideas 2 and 3 are distribution plays for teams that already use Skill Atlas.

---

## 3. Caveats
- Counts are vendor-reported and use different units: "listings", "SKILL.md files", "plugins". They are not comparable with each other and are not deduplicated.
- Partly unverified items: LobeHub's skills marketplace (its page returned 403), ClawHub's total count, and parts of the Snyk Agent Scan lineage (the old mcp-scan URL now serves the Snyk repo, but the rename is not stated there).
- The scanner benchmark numbers are each tool's own claims on its own benchmark. They were not reproduced here.
