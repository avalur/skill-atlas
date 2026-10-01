#!/usr/bin/env bash
# CI, after failed visual regression tests: publish the expected/actual/diff screenshots listed in
# artifacts/visual/failures.json to demo-assets and explain every failure with direct image links:
# in the log, as ::error annotations and as image tables in the job summary.
set -euo pipefail

root=$(git rev-parse --show-toplevel)
failures="${VISUAL_FAILURES_JSON:-$root/artifacts/visual/failures.json}"
if [ ! -s "$failures" ] && [ -s "$root/tests/visual/out/failures.json" ]; then
  failures="$root/tests/visual/out/failures.json"
fi
summary=${GITHUB_STEP_SUMMARY:-/dev/null}
repo=${GITHUB_REPOSITORY:-$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || git config --get remote.origin.url 2>/dev/null | sed -E 's/.*github\.com[:\/](.+)(\.git)?/\1/' | sed 's/\.git$//')}
run_url="${GITHUB_SERVER_URL:-https://github.com}/${repo:-avalur/skill-atlas}/actions/runs/${GITHUB_RUN_ID:-}"

if [ ! -s "$failures" ] || [ "$(jq 'length' "$failures" 2>/dev/null || echo 0)" = 0 ]; then
  echo "No screenshot failures recorded in $failures; see the test log above."
  exit 0
fi

# Image paths are relative to repository root; publish them keeping that path, so equal names of different tests don't clash.
images=$(jq -r '.[].snapshots[]? | .expected, .actual, .diff | values' "$failures" | sort -u)
urls='{}'
if [ -n "$images" ]; then
  existing_images=()
  while IFS= read -r img; do
    [ -n "$img" ] || continue
    if [ -f "$root/$img" ]; then
      existing_images+=("$img")
    fi
  done <<< "$images"

  if [ ${#existing_images[@]} -gt 0 ]; then
    # shellcheck disable=SC2086
    links=$(cd "$root" && "$root/scripts/publish-assets.sh" "visual-failures/${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}" "${existing_images[@]}") ||
      echo "::warning::could not publish the screenshots; download the visual-artifacts artifact instead"
    if [ -n "${links:-}" ]; then
      urls=$(paste <(printf "%s\n" "${existing_images[@]}") <(echo "$links") | jq -R 'split("\t") | {(.[0]): .[1]}' | jq -s add)
    fi
  fi
fi

# Paths without a published URL stay as local/artifact paths.
jq -r --argjson u "$urls" '
  def link($p): $u[$p] // "visual-artifacts artifact: \($p)";
  def fpath($p): if ($p | startswith("tests/")) then $p else "tests/visual/\($p)" end;
  .[] | "",
    "✘ Visual test failed: \(.title)  (\(fpath(.file)):\(.line))",
    ((.errors // [])[] | "    \(.)"),
    ((.snapshots // [])[] | "    screenshot \(.name)\(if .message then ": " + .message else "" end)",
      (["expected", "actual", "diff"][] as $k | .[$k] // empty | "      \($k | . + "        " | .[:8]) \(link(.))"))
' "$failures"
echo
echo "Full visual report: the visual-artifacts artifact of $run_url"
echo "An intended UI change? Re-render the baselines: UPDATE_BASELINES=1 uv run pytest tests/visual"

# Annotations: shown on the run page and next to the test in the PR diff.
jq -r --argjson u "$urls" '
  def fpath($p): if ($p | startswith("tests/")) then $p else "tests/visual/\($p)" end;
  .[] | . as $f
  | if ((.snapshots // []) | length) > 0
    then .snapshots[] | "::error file=\(fpath($f.file)),line=\($f.line),title=Visual test failed — \($f.title | gsub("[,:]"; " "))::\(.name) \(.message // "differs") — diff: \($u[.diff] // $u[.actual] // "see visual-artifacts artifact")"
    else "::error file=\(fpath($f.file)),line=\($f.line),title=Visual test failed — \($f.title | gsub("[,:]"; " "))::\((.errors // []) | join(" ") | .[:500])"
    end
' "$failures"

jq -r --argjson u "$urls" --arg run "$run_url" '
  def fpath($p): if ($p | startswith("tests/")) then $p else "tests/visual/\($p)" end;
  def img($p): if $p == null then "—" elif $u[$p] then "<a href=\"\($u[$p])\"><img src=\"\($u[$p])\" width=\"400\"></a>" else "`\($p)`" end;
  "## ❌ Visual tests: \(length) failed", "",
  (.[] | "### \(.title)", "`\(fpath(.file)):\(.line)`", "",
    ((.errors // [])[] | "> \(.)", ""),
    ((.snapshots // [])[] | "**\(.name)**\(if .message then " — " + .message else "" end)", "",
      "| Expected | Actual | Diff |", "|---|---|---|",
      "| \(img(.expected)) | \(img(.actual)) | \(img(.diff)) |", "")),
  "Full visual regression report (HTML, video, artifacts): the `visual-artifacts` artifact of [this run](\($run)#artifacts).",
  "An intended UI change? Re-render the baselines with `UPDATE_BASELINES=1 uv run pytest tests/visual` and commit them."
' "$failures" >>"$summary"
