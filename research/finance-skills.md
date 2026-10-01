# Finance Skills: Focused Research

**Date**: 2026-10-01
**Scope**: agent skills (SKILL.md) for finance in three segments: personal finance, organizations, and countries / the public sector. Companion to [`product-research.md`](product-research.md).
**Method**: one web-research pass that opened every cited page, plus hands-on scans of seven public finance skill repositories with Skill Atlas itself (`scan … -f json`, `similar … -f json`). The scan numbers below were re-checked against the JSON output. The Anthropic repository README, SkillsMP's category counts and the Unit 42 incident details were re-checked against the primary pages. Items seen only in search snippets are marked *unverified*.

---

## 1. Key takeaways

1. **Finance skills are a large slice of the catalogs.** SkillsMP lists **87,727** skills under Business › Finance & Investment, **9,902** under Payment and **1,548** under Blockchain › DeFi (categories overlap). Vercel's *State of Agent Skills* has no finance category at all.
2. **The serious content comes from vendors.** Anthropic's `financial-services` repo (10 agents, 9 vertical plugins, 12 data connectors including FactSet, S&P Global, Moody's, Morningstar, LSEG and PitchBook) sets the bar for organizations. Stripe, Binance and Coinbase ship skills that **move money or place trades**.
3. **Skill Atlas currently scans those action skills as clean.** Binance's 20 skills (spot and futures trading, transfers, P2P, payments) and Coinbase's agentic wallet (send and swap crypto) produce **0 findings**. Pattern rules look for malice, but the real finance risk is **capability**: a skill that is allowed to spend.
4. **Finance is the main theme of real attacks.** In the documented ClawHub incidents the lures were crypto wallets, trading bots, a pump-and-dump scheme and affiliate-link injection (§4).
5. **The public sector is a white space.** Macro and fiscal data skills exist (FRED, U.S. Treasury Fiscal Data, World Bank, Argentina's BCRA/INDEC), but none were found for IMF, OECD, Eurostat or sovereign debt.

---

## 2. Who publishes finance skills

| Publisher | What it ships | Read-only or acts | Source |
|---|---|---|---|
| **Anthropic**, `anthropics/financial-services` | 10 agents: Pitch, Meeting Prep, Market Researcher, Earnings Reviewer, Model Builder, Valuation Reviewer, GL Reconciler, Month-End Closer, Statement Auditor, KYC Screener. 9 vertical plugins: financial-analysis, investment-banking, equity-research, private-equity, fund-admin, operations, claude-for-financial-advisors, plus partner-built **LSEG** and **S&P Global**. 12 MCP connectors: Daloopa, Morningstar, S&P Global (Kensho), FactSet, Moody's, MT Newswires, Aiera, LSEG, PitchBook, Chronograph, Egnyte, Box. Apache-2.0, ~38.4k stars | Drafts only: "They do not make investment recommendations, execute transactions, bind risk, post to a ledger, or approve onboarding; every output is staged for human sign-off." | [GitHub](https://github.com/anthropics/financial-services), [launch post](https://www.anthropic.com/news/claude-for-financial-services) |
| **Stripe**, `stripe/ai` | 10 skills synced from Stripe docs (best practices, Connect, Stripe Apps, upgrades, …) | Developer guidance | [stripe/ai skills](https://github.com/stripe/ai/tree/main/skills) |
| **Stripe**, `stripe/link-cli` | Agents spend from a Link wallet with one-time cards or tokens. A `financial-insights` skill reads transactions and balances | **Spends money.** Limits per the README: $500 per request, $500 per day, $20,000 per 30 days, approval by push notification | [GitHub](https://github.com/stripe/link-cli) |
| **Binance**, `binance/binance-skills-hub` | 20 skills: spot, futures and convert trading, Web3 wallet, copy trading, P2P, fiat, payments, signals | **Trades and transfers.** The production rule is to ask the user to type `CONFIRM`. Calls itself "an informational tool only" | [GitHub](https://github.com/binance/binance-skills-hub) |
| **Coinbase**, `coinbase/agentic-wallet-skills` | `agentic-wallet`: send USDC/ETH/POL/SOL, swaps, Onramp, x402 payments | **Moves money** | [GitHub](https://github.com/coinbase/agentic-wallet-skills), [CDP docs](https://docs.cdp.coinbase.com/agentic-wallet/welcome) |
| **OctagonAI**, `OctagonAI/skills` | 67 skills over the Octagon MCP: financial metrics, earnings calls, SEC filings, market data, plus Kalshi prediction-market skills | Read-only, except a Kalshi skill with "guarded trade execution". Needs `OCTAGON_API_KEY` | [GitHub](https://github.com/OctagonAI/skills) |
| **Community** | himself65/finance-skills (~3.4k stars), RKiding/awesome-finance-skills (A-share, HK and US markets), JoelLewis/finance_skills (91 skills in 7 plugins incl. compliance), openaccountant/skills (44 skills), gauss314/skills (macro), zph/beancount-skill, calef/us-federal-tax-assistant-skill, 6missedcalls/personal-finance-skill | Mostly read-only; see §3 | links in §3 |

No standalone official finance skill repositories were found from OpenAI, Microsoft, Plaid, Ramp, Brex, FactSet, Moody's, PitchBook or Daloopa. The data vendors appear as MCP connectors inside Anthropic's repo instead.

**How catalogs represent finance**

| Catalog | Finance representation | Source |
|---|---|---|
| SkillsMP | Business › Finance & Investment **87,727**, Business › Payment **9,902**, Blockchain **23,170** (DeFi **1,548**). No accounting, trading or tax category. "A skill may belong to multiple categories" | [skillsmp.com/categories](https://skillsmp.com/categories) |
| Smithery | No finance category. A "finance" search returns 146 skills | [smithery.ai/skills?q=finance](https://smithery.ai/skills?q=finance) |
| skills.sh / Vercel report | No finance topic. The report classifies 66% of skills (87.5% of installs) as cross-industry, and "only one in eight installs is tied to a specific industry" | [Vercel](https://vercel.com/blog/state-of-agent-skills) |

---

## 3. What exists in each segment

### 3.1 Personal finance

| Skill | Data / API | Read or act |
|---|---|---|
| [zph/beancount-skill](https://github.com/zph/beancount-skill) | Local Beancount ledger and Fava | Read-only; "education and analysis, not licensed financial advice" |
| [calef/us-federal-tax-assistant-skill](https://github.com/calef/us-federal-tax-assistant-skill) | Fills IRS PDFs (1040, Schedules A/B/D, 8949, …) | Prepares forms only; no e-filing, no tax advice. SSN handling is not discussed |
| [openaccountant/skills](https://github.com/openaccountant/skills) | CSV, OFX, QIF, bank sync, Stripe, PayPal, Square, Wise | Analysis and guidance; no advice disclaimer shown |
| [6missedcalls/personal-finance-skill](https://github.com/6missedcalls/personal-finance-skill) | Plaid, Alpaca, IBKR, Finnhub, FRED, BLS, SEC EDGAR (75 tools) | **Acts:** `alpaca_create_order` is rated high risk, and `ALPACA_ENV` can be `live`. Policy text: "No live trades without explicit human confirmation, ever" |
| [stripe/link-cli](https://github.com/stripe/link-cli) | Link wallet | **Spends money**, with the limits above |
| [binance-skills-hub](https://github.com/binance/binance-skills-hub), [coinbase agentic-wallet](https://github.com/coinbase/agentic-wallet-skills) | Exchange and wallet CLIs | **Trades, transfers, swaps** |

### 3.2 Organizations

| Skill | Data / API | Read or act |
|---|---|---|
| Anthropic financial-analysis (comps, DCF, LBO, 3-statement, Excel audit) | FactSet, S&P, PitchBook, Daloopa and other MCP connectors | Drafts for human sign-off |
| Anthropic fund-admin and operations (GL reconciliation, NAV tie-out, KYC screening) | Internal documents via Box and Egnyte | Staged for sign-off |
| LSEG partner skills (bond relative value, FX carry, swap curves, macro rates monitor, …) and S&P Global (tear sheets, earnings previews) | LSEG Analytics, Capital IQ | Read-only research |
| [OctagonAI/skills](https://github.com/OctagonAI/skills) | SEC filings, earnings calls, market data | Read-only, except the Kalshi trading skill |
| [JoelLewis/finance_skills](https://github.com/JoelLewis/finance_skills) compliance plugin (KYC, AML/BSA, SARs, OFAC, Reg BI, books and records) | None, guidance only | Educational |
| [himself65/finance-skills](https://github.com/himself65/finance-skills) (company valuation, earnings preview, TradingView) | yfinance, Fintel, TradingView | Read-only |

### 3.3 Countries and the public sector

| Skill | Data / API |
|---|---|
| [gauss314/skills](https://github.com/gauss314/skills): `fred-macro`, BCRA macro, INDEC | FRED (needs a key), Argentina's central bank and statistics office (no key) |
| [awesome-econ-ai-stuff `api-data-fetcher`](https://meleantonio.github.io/awesome-econ-ai-stuff/skills/data/api-data-fetcher/index/) | Claims FRED, World Bank, IMF, BLS and OECD; only FRED and World Bank are implemented |
| [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) | U.S. Treasury Fiscal Data (national debt, auctions); a lookup skill covering FRED and SEC EDGAR |
| Anthropic LSEG `macro-rates-monitor`, `swap-curve-strategy` | LSEG |
| Country tax skills (France, Belgium) | *unverified*, seen only in search results |

No dedicated IMF, OECD, Eurostat or sovereign-debt skills were found.

---

## 4. Finance-specific risks

- **Skills that can move money.** Binance (trading, futures, transfers, P2P), Coinbase (send, swap), Stripe Link (purchases), Alpaca orders (6missedcalls), Kalshi trades (Octagon). Except for Stripe Link's server-side limits, the safeguards are written instructions to the agent, such as "type CONFIRM", which a prompt injection can override.
- **Credential handling.** Binance's README offers pasting API keys "directly into the agent chat" as one option. The Kalshi skill documents a `KALSHI_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----..."` environment variable. 6missedcalls requires `PLAID_SECRET`, `ALPACA_API_SECRET` and similar keys without saying how they are stored. Stripe Link is the good example: one-time credentials, masked card data, output files written with mode 0600.
- **Regulation.** FINRA's 2026 oversight report names agent risks: "AI agents acting autonomously without human validation and approval", acting "beyond the user's actual or intended scope and authority", and auditability. It asks firms to consider "how to track agent actions and decisions". [FINRA](https://www.finra.org/rules-guidance/guidance/reports/2026-finra-annual-regulatory-oversight-report/gen-ai)
- **Privacy.** Ledgers, tax forms with SSNs, Plaid account and transaction data, KYC documents.
- **Documented incidents** (Unit 42, published 2026-06-23, covering February–May 2026; [source](https://unit42.paloaltonetworks.com/openclaw-ai-supply-chain-risk/)):
  - **letssendit**: "an agentic front-running scheme". Installed agents "autonomously pooled … SOL into the operator's digital wallet" while the operator bought the SENDIT token cheaply first; "a novel documented case of an attacker weaponizing an autonomous AI agent network to execute a pump-and-dump scheme".
  - **money-radar**: posed as an advisor on overseas financial products and pulled a remote `referrals.json` with "approximately 60 products across eight categories", routing "all financial recommendations through affiliate links from a known-malicious domain".
  - **polymarketbtc** skills: "exfiltrated cryptocurrency private keys via the Telegram Bot API".
  - **TradingView-themed skills** (published 2026-05-17): delivered the "cluw" macOS infostealer. As of mid-May one of them had a "Pass" verdict from ClawHub's audit.
  - The earlier ClawHavoc campaign (341 malicious ClawHub skills, February 2026) relied heavily on crypto-wallet lures; the per-theme breakdown is *unverified* because Koi's original post now redirects.

---

## 5. Hands-on: seven finance repositories scanned with Skill Atlas

| Repository | Skills | Origins | Findings | What they show |
|---|---|---|---|---|
| anthropics/financial-services | **112** (64 unique names) | product 111, agent-config 1 | **0** | Clean. Each agent bundles synced copies of shared skills |
| OctagonAI/skills | 67 | standalone 67 | **SEC-003 ×63**, **SEC-001 ×1** | SEC-003 fires on every `references/mcp-setup.md` (`bash -c "$(curl …)"` install line). SEC-001 is a **false positive**: the placeholder `KALSHI_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----..."` contains no key |
| himself65/finance-skills | 26 | product 26 | SEC-003 ×1 | `curl -sSL …/install.sh \| sudo bash` in the telegram-reader skill |
| binance/binance-skills-hub | 20 | standalone 20 | **0** | Trading, transfer and payment skills, all clean |
| coinbase/agentic-wallet-skills | 1 | standalone 1 | **0** | Sends and swaps crypto, clean |
| openaccountant/skills | 44 | standalone 44 | 0 | |
| 6missedcalls/personal-finance-skill | 1 | standalone 1 | SEC-003 ×1 | `curl -fsSL https://openclaw.ai/install.sh \| bash` in a reference file |

**Duplicates.** `similar --threshold 0.6 -k 2000` on the Anthropic repository returns 137 pairs. **101 of them score 1.0**: identical synced copies with the same name, description and body (xlsx-author ×9, audit-xls ×7, comps-analysis ×4, pptx-author ×4; dcf-model, lbo-model, 3-statement-model and sector-overview ×3). None of the copies have drifted. The scan's per-skill `duplicates` field is empty here **by design**: these copies are classified as `product`, and product skills with the same name are never merged (a fix from the iteration-2 review, so distinct plugins are not hidden). That rule is right for distinct plugins, but here it reports 112 skills where 64 exist. Note also that `similar` defaults to `--top-k 10`, which hides most pairs in a whole-repository run.

---

## 6. Opportunities for Skill Atlas

| # | Opportunity | Evidence | How to measure impact |
|---|---|---|---|
| 1 | **Capability labels and FIN rules**: `executes-trades` (order, swap, futures, `create_order`), `moves-money` (send, transfer, withdraw, payout, x402, virtual card), `live-not-paper` (`ALPACA_ENV=live`, mainnet), `reads-bank-data` (Plaid, Financial Connections). Show them as filters in the Web UI and in the trust card | Binance, Coinbase and Link-style skills scan clean today | Label precision and recall on a hand-labeled set of 100 finance skills (target ≥ 0.9 / 0.85); share of action-capable skills in the seven repos correctly labeled (target 100%) |
| 2 | **Human-in-the-loop check**: WARN when an action-capable skill has no confirmation step, no spending limit and no paper or testnet default | FINRA's "without human validation and approval"; written "CONFIRM" rules are the only safeguard in most repos | Share of flagged skills confirmed by a reviewer as lacking a safeguard (≥ 80%) |
| 3 | **Finance credential patterns with placeholder awareness**: Stripe `sk_live_`, Binance, Kraken, Alpaca, Plaid and Kalshi keys, wallet seed phrases and private keys; ignore `...`, `<key>` and empty values; flag "paste your keys into chat" guidance | The Octagon SEC-001 false positive; Binance's chat-paste option | False-positive rate on the seven repos (target 0 placeholder hits) with no loss on a seeded set of real-format test keys |
| 4 | **Account and identity data in skills and fixtures**: IBAN, routing and account numbers, card numbers (Luhn-checked), SSN/TIN | Tax and ledger skills handle exactly this data | Detection rate on seeded fixtures (≥ 95%) and findings per 100 benign skills (≤ 1) |
| 5 | **Incident-derived rules**: remote affiliate configs (money-radar), wallet-pooling or token-launch instructions (letssendit), Telegram Bot API exfiltration, "prerequisite" download lures. Raise SEC-003 to ERROR when the skill is finance or crypto themed | Unit 42 incidents in §4 | Recall on a corpus rebuilt from the documented cases (≥ 90%) |
| 6 | **Advice disclaimer and compliance evidence**: INFO when an investment, tax or trading skill has no not-advice disclaimer; export per-skill evidence (first commit, capabilities, findings) for supervision and change-control reviews | Anthropic and JoelLewis include disclaimers, openaccountant does not; FINRA asks firms to "track agent actions" | Time for a finance-team reviewer to assemble evidence for 20 skills, with and without the export |
| 7 | **Synced-bundle awareness**: recognise identical copies in product bundles, report canonical skills plus drift, and raise the `similar` default `--top-k` for whole-repository runs | Anthropic's 112 files for 64 skills | Reported skill count matches unique skills on the Anthropic repo; drift still detected in a seeded drift test |
| 8 | **Public-sector data map**: a curated view of macro and fiscal data skills (FRED, Treasury Fiscal Data, World Bank, BCRA/INDEC) with key requirements | No IMF, OECD, Eurostat or sovereign-debt skills found | Usage of the view by public-sector analysts in a pilot; number of new public-data skills indexed per month |

Opportunities 1 and 2 also strengthen the **pre-install trust card** recommended in `product-research.md`: "this skill can move money, has a $500/day limit, asks for confirmation" is the line a finance user needs most.

---

## 7. Caveats
- Catalog counts are self-reported and overlap across categories.
- Some publisher details come from READMEs that the vendors maintain (for example Stripe Link's limits); they were not tested.
- The scans use Skill Atlas at `main` on 2026-10-01 and reflect its current pattern-based rules. A clean result does not mean a skill is safe.
