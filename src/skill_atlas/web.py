"""FastAPI web server and interactive UI for Skill Atlas."""

import asyncio
import os
import queue
import secrets
import threading
import time
import uuid
import webbrowser
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from skill_atlas import __version__
from skill_atlas.git.client import parse_github_url
from skill_atlas.git.github import GitHubClient
from skill_atlas.models import (
    ProgressEvent,
    ScanResult,
    SkillOrigin,
    Stage,
)
from skill_atlas.scanner import Scanner, normalize_targets
from skill_atlas.similarity import SimilarSkillMatch, SimilarSkillsResult, find_similar_skills

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'self' 'unsafe-inline';">
  <title>Skill Atlas</title>
  <style>
    :root, html[data-theme="light"] {
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --text: #0f172a;
      --text-muted: #64748b;
      --border: #e2e8f0;
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --success: #10b981;
      --warn: #f59e0b;
      --error: #ef4444;
      --status-bg: #1e293b;
      --status-text: #f8fafc;
    }
    @media (prefers-color-scheme: dark) {
      :root:not([data-theme="light"]) {
        --bg: #0f172a;
        --card-bg: #1e293b;
        --text: #f8fafc;
        --text-muted: #94a3b8;
        --border: #334155;
        --primary: #3b82f6;
        --primary-hover: #60a5fa;
        --status-bg: #020617;
      }
    }
    html[data-theme="dark"] {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --border: #334155;
      --primary: #3b82f6;
      --primary-hover: #60a5fa;
      --status-bg: #020617;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); padding-bottom: 70px; }
    header { background: var(--card-bg); border-bottom: 1px solid var(--border); padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; }
    header h1 { font-size: 1.25rem; font-weight: 700; }
    .theme-toggle-btn { background: var(--bg); color: var(--text); border: 1px solid var(--border); padding: 0.35rem 0.65rem; border-radius: 0.375rem; font-size: 0.95rem; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; transition: background 0.2s, border-color 0.2s; }
    .theme-toggle-btn:hover { border-color: var(--primary); }
    .badge { font-size: 0.75rem; padding: 0.2rem 0.5rem; border-radius: 9999px; font-weight: 600; }
    .badge-primary { background: rgba(59, 130, 246, 0.1); color: var(--primary); }
    .badge-success { background: rgba(16, 185, 129, 0.1); color: var(--success); }
    .badge-warn { background: rgba(245, 158, 11, 0.1); color: var(--warn); }
    .badge-error { background: rgba(239, 68, 68, 0.1); color: var(--error); }
    .badge-magenta { background: rgba(217, 70, 239, 0.1); color: #d946ef; }
    .container { max-width: 1000px; margin: 1.5rem auto; padding: 0 1rem; }
    .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 0.5rem; padding: 1.25rem; margin-bottom: 1.5rem; }
    .form-group { margin-bottom: 1rem; }
    .input-row { display: flex; gap: 0.5rem; }
    input[type="text"], select { flex: 1; padding: 0.6rem 0.8rem; border: 1px solid var(--border); border-radius: 0.375rem; background: var(--bg); color: var(--text); font-size: 0.95rem; }
    button { cursor: pointer; padding: 0.6rem 1.25rem; border-radius: 0.375rem; font-weight: 600; font-size: 0.95rem; border: none; transition: background 0.2s; }
    .btn-primary { background: var(--primary); color: white; }
    .btn-primary:hover { background: var(--primary-hover); }
    .btn-danger { background: var(--error); color: white; }
    .btn-secondary { background: var(--border); color: var(--text); }
    .options-row { display: flex; flex-wrap: wrap; gap: 1rem; margin-top: 0.75rem; font-size: 0.85rem; color: var(--text-muted); align-items: center; }
    .options-row label { display: flex; align-items: center; gap: 0.35rem; }
    .filter-chips { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem; }
    .chip { cursor: pointer; padding: 0.3rem 0.75rem; border-radius: 9999px; background: var(--card-bg); border: 1px solid var(--border); font-size: 0.85rem; color: var(--text-muted); transition: all 0.15s ease; }
    .chip.active { background: var(--primary); color: white; border-color: var(--primary); }
    .chip#chip-starred.active { background: #f59e0b; color: white; border-color: #f59e0b; }
    .filter-row { display: flex; gap: 0.75rem; align-items: center; margin-top: 0.75rem; }
    .filter-input { flex: 1; padding: 0.55rem 0.8rem; border: 1px solid var(--border); border-radius: 0.375rem; background: var(--bg); color: var(--text); font-size: 0.9rem; }
    .skill-item { border: 1px solid var(--border); border-radius: 0.375rem; margin-bottom: 0.75rem; padding: 1rem; background: var(--card-bg); }
    .skill-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem; }
    .skill-title { font-weight: 600; font-size: 1.05rem; display: flex; align-items: center; gap: 0.5rem; }
    .skill-desc { color: var(--text-muted); font-size: 0.9rem; margin-bottom: 0.5rem; }
    .skill-meta { font-size: 0.8rem; color: var(--text-muted); display: flex; flex-wrap: wrap; gap: 1rem; margin-bottom: 0.5rem; }
    .findings-list { margin-top: 0.75rem; border-top: 1px solid var(--border); padding-top: 0.5rem; }
    .finding-row { font-size: 0.85rem; margin-top: 0.35rem; display: flex; gap: 0.5rem; align-items: baseline; }
    .btn-star { display: inline-flex; align-items: center; justify-content: center; gap: 0.35rem; padding: 0.25rem 0.55rem; font-size: 0.75rem; background: var(--card-bg); border: 1px solid var(--border); color: var(--text-muted); border-radius: 0.375rem; cursor: pointer; transition: all 0.2s ease; }
    .btn-star:hover { border-color: #f59e0b; color: #f59e0b; }
    .btn-star.active { background: rgba(245, 158, 11, 0.12); border-color: #f59e0b; color: #f59e0b; font-weight: 600; }
    .btn-star .star-icon { width: 14px; height: 14px; fill: transparent; stroke: currentColor; transition: fill 0.2s ease, stroke 0.2s ease, transform 0.2s ease; }
    .btn-star.active .star-icon { fill: #f59e0b; stroke: #f59e0b; }
    .modal-backdrop { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.55); display: flex; align-items: center; justify-content: center; z-index: 200; padding: 1rem; backdrop-filter: blur(2px); }
    .modal-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 0.5rem; max-width: 750px; width: 100%; max-height: 85vh; display: flex; flex-direction: column; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3); overflow: hidden; }
    .modal-header { padding: 1rem 1.25rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
    .modal-body { padding: 1.25rem; overflow-y: auto; }
    .modal-close-btn { background: none; border: none; font-size: 1.2rem; color: var(--text-muted); cursor: pointer; padding: 0.2rem 0.5rem; border-radius: 0.25rem; }
    .modal-close-btn:hover { background: var(--border); color: var(--text); }
    #status-bar { position: fixed; bottom: 0; left: 0; right: 0; height: 56px; background: var(--status-bg); color: var(--status-text); display: flex; align-items: center; justify-content: space-between; padding: 0 1.5rem; font-size: 0.85rem; border-top: 1px solid rgba(255,255,255,0.1); z-index: 100; }
    .status-left { display: flex; align-items: center; gap: 0.75rem; flex: 1; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
    .progress-track { width: 140px; height: 8px; background: rgba(255,255,255,0.2); border-radius: 4px; overflow: hidden; }
    .progress-fill { height: 100%; background: var(--primary); width: 0%; transition: width 0.2s; }
  </style>
</head>
<body>
  <header>
    <h1>Skill Atlas</h1>
    <div style="display: flex; align-items: center; gap: 0.75rem;">
      <button id="theme-toggle" class="theme-toggle-btn" onclick="toggleTheme()" title="Toggle theme" aria-label="Toggle theme">🌙</button>
      <span class="badge badge-primary">v0.2.0</span>
    </div>
  </header>

  <div class="container">
    <div class="card">
      <div class="form-group">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
          <label style="font-weight:600; display:block;" for="target-input">Repository or Folder</label>
          <button type="button" id="load-sample-btn" onclick="loadSampleMultiTargets()" style="background:none; border:none; color:var(--primary); font-size:0.8rem; font-weight:500; cursor:pointer;" title="Load sample repositories">Load Sample Repos</button>
        </div>
        <div class="input-row">
          <textarea id="target-input" rows="2" placeholder="https://github.com/JetBrains/kotlin&#10;https://github.com/modelcontextprotocol/servers" style="flex:1; padding:0.6rem 0.8rem; border:1px solid var(--border); border-radius:0.375rem; background:var(--bg); color:var(--text); font-size:0.95rem; font-family:inherit; resize:vertical; min-height:42px; line-height:1.4;">https://github.com/JetBrains/kotlin</textarea>
          <button id="scan-btn" class="btn-primary" onclick="startScan()" style="align-self:stretch;">Scan</button>
        </div>
      </div>
      <div class="options-row">
        <label>Query: <input type="text" id="query-input" placeholder="e.g. git" style="width:110px; padding:0.2rem 0.4rem;"></label>
        <label>Ref: <input type="text" id="ref-input" placeholder="default" style="width:90px; padding:0.2rem 0.4rem;"></label>
        <label>Fail On:
          <select id="fail-on-select" style="padding:0.2rem 0.4rem;">
            <option value="error">Error</option>
            <option value="warn">Warn</option>
          </select>
        </label>
        <label>Rules:
          <select id="rules-select" style="padding:0.2rem 0.4rem;">
            <option value="all">All</option>
            <option value="schema">Schema</option>
            <option value="security">Security</option>
            <option value="discovery">Discovery</option>
          </select>
        </label>
        <label><input type="checkbox" id="test-data-check"> Include test data</label>
      </div>
    </div>

    <div id="initial-hint" class="card" style="text-align:center; padding:2.5rem 1rem; color:var(--text-muted); margin-bottom:1.5rem;">
      <div style="font-size:1.6rem; margin-bottom:0.5rem;">🔍</div>
      <div style="font-weight:600; font-size:1rem; color:var(--text); margin-bottom:0.35rem;">Ready to scan</div>
      <div style="font-size:0.875rem;">Enter a repository URL or folder path above and click <b>Scan</b> to discover skills, validate rules, inspect findings, filter skills, and find similar implementations.</div>
    </div>

    <div id="summary-section" style="display:none;" class="card">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 1rem; flex-wrap:wrap; gap:0.5rem;">
        <div>
          <h2 id="summary-headline" style="font-size:1.15rem;">Scan Summary</h2>
          <div id="summary-sub" style="font-size:0.85rem; color:var(--text-muted); margin-top:0.2rem;"></div>
        </div>
        <div style="display:flex; gap:0.5rem;">
          <button id="map-btn" class="btn-secondary" onclick="toggleSkillMap()">Skill Map</button>
          <button id="similar-btn" class="btn-secondary" onclick="toggleSimilarSkills()">Find Similar</button>
          <button class="btn-secondary" onclick="downloadJson()">Download JSON</button>
        </div>
      </div>
      <div id="repo-filter-section" style="margin-bottom:0.75rem; display:none;">
        <div style="font-size:0.75rem; font-weight:600; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-muted); margin-bottom:0.35rem;">Repositories</div>
        <div class="filter-chips" id="repo-chips">
          <div class="chip active" id="chip-repo-all" onclick="setRepoFilter('all', event)">All Repos (<span id="count-repo-all">0</span>)</div>
        </div>
      </div>
      <div id="origin-filter-section" style="margin-bottom:1rem;">
        <div style="font-size:0.75rem; font-weight:600; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-muted); margin-bottom:0.35rem;">Origins &amp; Favorites</div>
        <div class="filter-chips" id="origin-chips">
          <div class="chip active" id="chip-all" onclick="setOriginFilter('all', event)">All (<span id="count-all">0</span>)</div>
          <div class="chip" id="chip-starred" onclick="toggleStarredFilter(event)" style="border-color:rgba(245,158,11,0.4);" title="Filter and view only starred skills">★ Starred (<span id="count-starred">0</span>)</div>
          <div class="chip" id="chip-agent-config" onclick="setOriginFilter('agent-config', event)">Agent Config (<span id="count-agent-config">0</span>)</div>
          <div class="chip" id="chip-product" onclick="setOriginFilter('product', event)">Product (<span id="count-product">0</span>)</div>
          <div class="chip" id="chip-standalone" onclick="setOriginFilter('standalone', event)">Standalone (<span id="count-standalone">0</span>)</div>
          <div class="chip" id="chip-test-data" onclick="setOriginFilter('test-data', event)">Test Data (<span id="count-test-data">0</span>)</div>
        </div>
      </div>
      <div class="filter-row">
        <input type="text" id="filter-input" class="filter-input" placeholder="Filter skills by words in name or description..." oninput="renderSkills()">
        <select id="status-filter-select" style="max-width:140px; padding:0.55rem 0.6rem; font-size:0.85rem;" onchange="setStatusFilter(this.value)">
          <option value="all">All statuses</option>
          <option value="pass">Passed only</option>
          <option value="fail">Failed only</option>
        </select>
      </div>
    </div>

    <div id="map-section" style="display:none;" class="card">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 0.75rem; flex-wrap:wrap; gap:0.5rem;">
        <div style="display:flex; align-items:center; gap:0.75rem;">
          <h3 style="font-size:1.05rem;">Skill Map</h3>
          <span id="map-count" style="font-size:0.85rem; color:var(--text-muted);"></span>
        </div>
        <div style="display:flex; align-items:center; gap:0.5rem; font-size:0.85rem;">
          <label style="color:var(--text-muted); display:flex; align-items:center; gap:0.3rem;">
            Method:
            <select id="map-method" style="padding:0.25rem 0.5rem; font-size:0.85rem;" onchange="loadSkillMap()">
              <option value="heuristic">Heuristic (Shared Words)</option>
              <option value="ai">AI Clustered (Claude)</option>
              <option value="jev">TypeSafe Jev (System 1)</option>
            </select>
          </label>
          <button class="btn-secondary" style="padding:0.25rem 0.6rem; font-size:0.85rem;" onclick="closeSkillMap()" title="Close skill map">✕</button>
        </div>
      </div>
      <div id="map-clusters-list" style="display:grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 0.75rem;"></div>
    </div>

    <div id="similar-section" style="display:none;" class="card">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 0.75rem; flex-wrap:wrap; gap:0.5rem;">
        <div style="display:flex; align-items:center; gap:0.75rem;">
          <h3 style="font-size:1.05rem;">Similar Skills</h3>
          <span id="similar-count" style="font-size:0.85rem; color:var(--text-muted);"></span>
        </div>
        <div style="display:flex; align-items:center; gap:0.5rem; font-size:0.85rem;">
          <label style="color:var(--text-muted); display:flex; align-items:center; gap:0.3rem;">
            Threshold:
            <select id="similar-threshold" style="padding:0.25rem 0.5rem; font-size:0.85rem;" onchange="loadSimilarSkills()">
              <option value="0.3">≥ 0.3 (broad)</option>
              <option value="0.4">≥ 0.4</option>
              <option value="0.5" selected>≥ 0.5 (standard)</option>
              <option value="0.6">≥ 0.6</option>
              <option value="0.7">≥ 0.7 (strict)</option>
              <option value="0.8">≥ 0.8 (very strict)</option>
            </select>
          </label>
          <button class="btn-secondary" style="padding:0.25rem 0.6rem; font-size:0.85rem;" onclick="closeSimilarSkills()" title="Close similar panel">✕</button>
        </div>
      </div>
      <div id="similar-query-banner" style="display:none; background:rgba(59,130,246,0.1); border:1px solid rgba(59,130,246,0.3); border-radius:0.375rem; padding:0.4rem 0.75rem; font-size:0.85rem; margin-bottom:0.75rem; justify-content:space-between; align-items:center;">
        <span>Showing skills similar to: <b id="similar-query-name"></b></span>
        <button class="btn-secondary" style="padding:0.15rem 0.5rem; font-size:0.75rem;" onclick="clearSimilarQuery()">Show all pairs</button>
      </div>
      <div id="similar-list"></div>
    </div>

    <div id="skills-list"></div>
  </div>

  <div id="status-bar" aria-live="polite">
    <div class="status-left">
      <span id="status-spinner">⚪</span>
      <span id="status-text">Ready. Paste a repository URL and click Scan.</span>
    </div>
    <div style="display:flex; align-items:center; gap: 1rem;">
      <div id="progress-container" style="display:none;" class="progress-track">
        <div id="progress-fill" class="progress-fill"></div>
      </div>
      <span id="rate-limit-badge" style="font-size:0.75rem; opacity:0.8;"></span>
      <button id="cancel-btn" style="display:none;" class="btn-danger" style="padding:0.2rem 0.6rem; font-size:0.75rem;" onclick="cancelScan()">Cancel</button>
    </div>
  </div>

  <script>
    const CSRF_TOKEN = "{{CSRF_TOKEN}}";
    const STARRED_STORAGE_KEY = 'skill_atlas_starred_skills';
    let currentScanId = null;
    let eventSource = null;
    let scanResult = null;
    let activeFilter = 'all';
    let activeRepoFilter = 'all';
    let activeStatusFilter = 'all';
    let activeStarredFilter = false;
    let currentSimilarQuery = null;
    let currentModalSkill = null;

    function loadSampleMultiTargets() {
      const input = document.getElementById('target-input');
      if (input) {
        input.value = "https://github.com/JetBrains/kotlin\\nhttps://github.com/modelcontextprotocol/servers";
      }
    }

    function initTheme() {
      const saved = localStorage.getItem('skill-atlas-theme');
      if (saved === 'dark' || saved === 'light') {
        document.documentElement.setAttribute('data-theme', saved);
        updateThemeIcon(saved);
      } else {
        const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        updateThemeIcon(prefersDark ? 'dark' : 'light');
      }
    }

    function toggleTheme() {
      const current = document.documentElement.getAttribute('data-theme');
      const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      const isDark = current ? (current === 'dark') : prefersDark;
      const next = isDark ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('skill-atlas-theme', next);
      updateThemeIcon(next);
    }

    function updateThemeIcon(theme) {
      const btn = document.getElementById('theme-toggle');
      if (btn) {
        btn.textContent = theme === 'dark' ? '☀️' : '🌙';
        btn.setAttribute('title', theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
      }
    }
    initTheme();

    async function checkHealth() {
      try {
        const res = await fetch('/api/health');
        if (res.ok) {
          const data = await res.json();
          const tokenText = data.github_token_configured ? 'Token Active' : 'No Token (~60 req/hr)';
          document.getElementById('rate-limit-badge').textContent = tokenText;
          if (!data.github_token_configured) {
            const statusText = document.getElementById('status-text');
            if (statusText && (statusText.textContent.includes('Ready to scan') || !statusText.textContent)) {
              statusText.textContent = 'Ready to scan · No GITHUB_TOKEN: limited to ~25 skills per hour';
            }
          }
        }
      } catch (e) {}
    }
    checkHealth();

    async function startScan() {
      const targetVal = document.getElementById('target-input').value.trim();
      if (!targetVal) return;
      const targets = targetVal.split(/[\\r\\n,]+/).map(t => t.trim()).filter(Boolean);
      if (targets.length === 0) return;

      const queryInput = document.getElementById('query-input');
      const query = queryInput ? (queryInput.value.trim() || null) : null;
      const ref = document.getElementById('ref-input').value.trim() || null;
      const failOn = document.getElementById('fail-on-select').value;
      const rules = document.getElementById('rules-select').value;
      const includeTestData = document.getElementById('test-data-check').checked;

      document.getElementById('scan-btn').disabled = true;
      document.getElementById('status-spinner').textContent = '⟳';
      document.getElementById('status-text').textContent = 'Starting scan...';
      document.getElementById('skills-list').innerHTML = '';
      if (document.getElementById('filter-input')) {
        document.getElementById('filter-input').value = '';
      }
      if (document.getElementById('status-filter-select')) {
        document.getElementById('status-filter-select').value = 'all';
      }
      activeFilter = 'all';
      activeRepoFilter = 'all';
      activeStatusFilter = 'all';
      activeStarredFilter = false;
      currentSimilarQuery = null;

      document.querySelectorAll('#origin-chips .chip').forEach(c => c.classList.remove('active'));
      const chipAll = document.getElementById('chip-all');
      if (chipAll) chipAll.classList.add('active');
      const chipRepoAll = document.getElementById('chip-repo-all');
      if (chipRepoAll) chipRepoAll.classList.add('active');
      const chipStarred = document.getElementById('chip-starred');
      if (chipStarred) chipStarred.classList.remove('active');

      document.getElementById('summary-section').style.display = 'none';
      document.getElementById('similar-section').style.display = 'none';
      if (document.getElementById('initial-hint')) {
        document.getElementById('initial-hint').style.display = 'none';
      }
      document.getElementById('cancel-btn').style.display = 'inline-block';

      try {
        const resp = await fetch('/api/scans', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-SkillAtlas-Token': CSRF_TOKEN
          },
          body: JSON.stringify({
            targets: targets,
            target: targets[0] || '',
            query: query,
            ref: ref,
            fail_on: failOn,
            rules: rules,
            include_test_data: includeTestData
          })
        });

        if (!resp.ok) {
          const errData = await resp.json();
          throw new Error(errData.detail || 'Failed to start scan');
        }

        const data = await resp.json();
        currentScanId = data.scan_id;
        listenEvents(currentScanId);
      } catch (err) {
        document.getElementById('status-spinner').textContent = '✖';
        document.getElementById('status-text').textContent = err.message;
        document.getElementById('scan-btn').disabled = false;
        document.getElementById('cancel-btn').style.display = 'none';
      }
    }

    function listenEvents(scanId) {
      if (eventSource) eventSource.close();
      eventSource = new EventSource(`/api/scans/${scanId}/events`);

      eventSource.onmessage = (e) => {
        const ev = JSON.parse(e.data);
        let msg = ev.message;
        if (ev.target_index != null && ev.target_total != null && ev.target_total > 1) {
          const rawPrefix = `[${ev.target_index}/${ev.target_total}] `;
          if (msg.startsWith(rawPrefix)) {
            msg = msg.slice(rawPrefix.length);
          }
          const targetPrefix = ev.target_name ? `[${ev.target_index}/${ev.target_total}: ${ev.target_name}] ` : rawPrefix;
          msg = targetPrefix + msg;
        }
        document.getElementById('status-text').textContent = msg;

        if (ev.current != null && ev.total != null && ev.total > 0) {
          document.getElementById('progress-container').style.display = 'block';
          const pct = Math.round((ev.current / ev.total) * 100);
          document.getElementById('progress-fill').style.width = pct + '%';
        }

        if (ev.rate_limit_remaining != null) {
          document.getElementById('rate-limit-badge').textContent = `API: ${ev.rate_limit_remaining}`;
        }

        if (ev.stage === 'done') {
          eventSource.close();
          finishScan(scanId);
        } else if (ev.stage === 'error') {
          eventSource.close();
          document.getElementById('status-spinner').textContent = '✖';
          document.getElementById('scan-btn').disabled = false;
          document.getElementById('cancel-btn').style.display = 'none';
        }
      };

      eventSource.onerror = () => {
        eventSource.close();
        document.getElementById('status-spinner').textContent = '✖';
        document.getElementById('status-text').textContent = 'Connection closed or lost.';
        document.getElementById('scan-btn').disabled = false;
        document.getElementById('cancel-btn').style.display = 'none';
      };
    }

    async function finishScan(scanId) {
      document.getElementById('status-spinner').textContent = '✔';
      document.getElementById('scan-btn').disabled = false;
      document.getElementById('cancel-btn').style.display = 'none';
      document.getElementById('progress-container').style.display = 'none';

      const resp = await fetch(`/api/scans/${scanId}`);
      if (resp.ok) {
        scanResult = await resp.json();
        renderResults();
      }
    }

    async function cancelScan() {
      if (!currentScanId) return;
      await fetch(`/api/scans/${currentScanId}`, {
        method: 'DELETE',
        headers: { 'X-SkillAtlas-Token': CSRF_TOKEN }
      });
      document.getElementById('status-text').textContent = 'Scan cancelled.';
      document.getElementById('cancel-btn').style.display = 'none';
      document.getElementById('scan-btn').disabled = false;
    }

    function setStatusFilter(status) {
      activeStatusFilter = status;
      renderSkills();
    }

    function setRepoFilter(repo, evt) {
      activeRepoFilter = repo;
      const repoContainer = document.getElementById('repo-chips');
      if (repoContainer) {
        repoContainer.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
      }
      const chip = evt ? (evt.currentTarget || evt.target.closest('.chip')) : null;
      if (chip) {
        chip.classList.add('active');
      }
      renderSkills();
    }

    function setOriginFilter(origin, evt) {
      activeFilter = origin;
      const originContainer = document.getElementById('origin-chips') || document;
      originContainer.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
      const chip = evt ? (evt.currentTarget || evt.target.closest('.chip')) : (window.event ? (window.event.currentTarget || window.event.target.closest('.chip')) : null);
      if (chip) {
        chip.classList.add('active');
      }
      // Preserve the independent "Starred" toggle state across origin changes.
      const chipStarred = document.getElementById('chip-starred');
      if (chipStarred) chipStarred.classList.toggle('active', activeStarredFilter);
      renderSkills();
    }

    // --- Starred skills (persisted in localStorage) ---

    function getStarredSet() {
      try {
        const raw = localStorage.getItem(STARRED_STORAGE_KEY);
        if (!raw) return new Set();
        const arr = JSON.parse(raw);
        return new Set(Array.isArray(arr) ? arr : []);
      } catch (e) {
        return new Set();
      }
    }

    function saveStarredSet(set) {
      try {
        localStorage.setItem(STARRED_STORAGE_KEY, JSON.stringify([...set]));
      } catch (e) {
        /* localStorage may be unavailable (private mode / quota) */
      }
    }

    function skillKey(sk) {
      return `${sk.repo_name || 'local'}::${sk.path || ''}::${sk.name || ''}`;
    }

    function isStarred(sk) {
      return getStarredSet().has(skillKey(sk));
    }

    function toggleStar(sk) {
      const set = getStarredSet();
      const key = skillKey(sk);
      if (set.has(key)) {
        set.delete(key);
      } else {
        set.add(key);
      }
      saveStarredSet(set);
      updateStarredCount();
      return set.has(key);
    }

    function countStarredSkills() {
      if (!scanResult || !scanResult.skills) return 0;
      const set = getStarredSet();
      return scanResult.skills.filter(sk => set.has(skillKey(sk))).length;
    }

    function updateStarredCount() {
      const el = document.getElementById('count-starred');
      if (el) el.textContent = countStarredSkills();
    }

    function createStarButton(sk, labelled) {
      const btn = document.createElement('button');
      const starred = isStarred(sk);
      btn.className = 'btn-star' + (starred ? ' active' : '');
      btn.setAttribute('aria-pressed', starred ? 'true' : 'false');
      btn.title = starred ? 'Remove from starred' : 'Add to starred';
      btn.innerHTML =
        '<svg class="star-icon" viewBox="0 0 24 24" aria-hidden="true">' +
        '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>' +
        '</svg>';
      if (labelled) {
        const lbl = document.createElement('span');
        lbl.className = 'star-label';
        lbl.textContent = starred ? 'Starred' : 'Star';
        btn.appendChild(lbl);
      }
      btn.onclick = (e) => {
        e.stopPropagation();
        const nowStarred = toggleStar(sk);
        btn.classList.toggle('active', nowStarred);
        btn.setAttribute('aria-pressed', nowStarred ? 'true' : 'false');
        btn.title = nowStarred ? 'Remove from starred' : 'Add to starred';
        const lbl = btn.querySelector('.star-label');
        if (lbl) lbl.textContent = nowStarred ? 'Starred' : 'Star';
        if (activeStarredFilter) renderSkills();
      };
      return btn;
    }

    function toggleStarredFilter(evt) {
      activeStarredFilter = !activeStarredFilter;
      const chip = document.getElementById('chip-starred');
      if (chip) chip.classList.toggle('active', activeStarredFilter);
      renderSkills();
    }

    // --- Skill detail modal ---

    function modalKeyHandler(e) {
      if (e.key === 'Escape') closeSkillModal();
    }

    function closeSkillModal() {
      const m = document.getElementById('skill-modal-root');
      if (m) m.remove();
      document.removeEventListener('keydown', modalKeyHandler);
      currentModalSkill = null;
    }

    function openSkillDetail(sk) {
      closeSkillModal();
      currentModalSkill = sk;

      const backdrop = document.createElement('div');
      backdrop.className = 'modal-backdrop';
      backdrop.id = 'skill-modal-root';
      backdrop.onclick = (e) => { if (e.target === backdrop) closeSkillModal(); };

      const card = document.createElement('div');
      card.className = 'modal-card';

      const header = document.createElement('div');
      header.className = 'modal-header';

      const htitle = document.createElement('div');
      htitle.className = 'skill-title';
      const hName = document.createElement('span');
      hName.textContent = sk.name;
      htitle.appendChild(hName);
      const hOrigin = document.createElement('span');
      hOrigin.className = 'badge badge-primary';
      hOrigin.textContent = sk.origin;
      htitle.appendChild(hOrigin);

      const headerActions = document.createElement('div');
      headerActions.style.display = 'flex';
      headerActions.style.alignItems = 'center';
      headerActions.style.gap = '0.5rem';
      headerActions.appendChild(createStarButton(sk, true));
      const closeBtn = document.createElement('button');
      closeBtn.className = 'modal-close-btn';
      closeBtn.textContent = '✕';
      closeBtn.title = 'Close';
      closeBtn.onclick = closeSkillModal;
      headerActions.appendChild(closeBtn);

      header.appendChild(htitle);
      header.appendChild(headerActions);

      const body = document.createElement('div');
      body.className = 'modal-body';

      if (sk.description) {
        const desc = document.createElement('div');
        desc.className = 'skill-desc';
        desc.style.marginBottom = '0.75rem';
        desc.textContent = sk.description;
        body.appendChild(desc);
      }

      const meta = document.createElement('div');
      meta.className = 'skill-meta';
      const addMeta = (text) => {
        const span = document.createElement('span');
        span.textContent = text;
        meta.appendChild(span);
      };
      addMeta(`Path: ${sk.path}`);
      if (sk.repo_name) addMeta(`Repo: ${sk.repo_name}`);
      if (sk.updated_date) addMeta(`Updated: ${sk.updated_date}`);
      if (sk.tags && sk.tags.length > 0) addMeta(`Tags: ${sk.tags.join(', ')}`);
      body.appendChild(meta);

      if (sk.findings && sk.findings.length > 0) {
        const findingsList = document.createElement('div');
        findingsList.className = 'findings-list';
        for (const f of sk.findings) {
          const fRow = document.createElement('div');
          fRow.className = 'finding-row';
          const badgeClass = f.severity === 'ERROR' ? 'badge-error' : f.severity === 'WARN' ? 'badge-warn' : 'badge-primary';
          const bSpan = document.createElement('span');
          bSpan.className = `badge ${badgeClass}`;
          bSpan.textContent = f.severity;
          fRow.appendChild(bSpan);
          const ruleB = document.createElement('b');
          ruleB.textContent = f.rule_id ? `${f.rule_id}: ` : '';
          fRow.appendChild(ruleB);
          const msgSpan = document.createElement('span');
          msgSpan.textContent = f.message || '';
          fRow.appendChild(msgSpan);
          findingsList.appendChild(fRow);
        }
        body.appendChild(findingsList);
      }

      card.appendChild(header);
      card.appendChild(body);
      backdrop.appendChild(card);
      document.body.appendChild(backdrop);
      document.addEventListener('keydown', modalKeyHandler);
    }

    function renderResults() {
      if (!scanResult) return;
      document.getElementById('summary-section').style.display = 'block';
      if (document.getElementById('initial-hint')) {
        document.getElementById('initial-hint').style.display = 'none';
      }
      const s = scanResult.summary;
      const targetCount = (scanResult.targets && scanResult.targets.length > 1) ? scanResult.targets.length : 0;
      const targetStr = targetCount > 1 ? ` across ${targetCount} targets` : '';
      document.getElementById('summary-headline').textContent =
        `Scanned ${s.total_skills} skills${targetStr} · ${s.passed} passed · ${s.failed} failed`;
      const f = s.findings_count;
      const queryStr = scanResult.query ? `Query: '${scanResult.query}' · ` : '';
      document.getElementById('summary-sub').textContent =
        `${queryStr}${f.error} errors · ${f.warn} warnings · ${f.info} info`;

      document.getElementById('count-all').textContent = s.total_skills;
      document.getElementById('count-agent-config').textContent = s.by_origin['agent-config'] || 0;
      document.getElementById('count-product').textContent = s.by_origin['product'] || 0;
      document.getElementById('count-standalone').textContent = s.by_origin['standalone'] || 0;
      document.getElementById('count-test-data').textContent = s.by_origin['test-data'] || 0;
      updateStarredCount();

      // Populate dynamic repo chips
      const repoMap = {};
      let totalRepoSkills = 0;
      for (const sk of scanResult.skills) {
        const repo = sk.repo_name || 'local';
        repoMap[repo] = (repoMap[repo] || 0) + 1;
        totalRepoSkills++;
      }
      const repoNames = Object.keys(repoMap).sort();
      const repoSection = document.getElementById('repo-filter-section');
      const repoChipsContainer = document.getElementById('repo-chips');
      if (repoSection && repoChipsContainer) {
        if (repoNames.length > 0) {
          repoSection.style.display = 'block';
          repoChipsContainer.innerHTML = '';
          const allChip = document.createElement('div');
          allChip.className = 'chip' + (activeRepoFilter === 'all' ? ' active' : '');
          allChip.id = 'chip-repo-all';
          allChip.onclick = (e) => setRepoFilter('all', e);
          allChip.innerHTML = `All Repos (<span id="count-repo-all">${totalRepoSkills}</span>)`;
          repoChipsContainer.appendChild(allChip);

          for (const repo of repoNames) {
            const chip = document.createElement('div');
            chip.className = 'chip' + (activeRepoFilter === repo ? ' active' : '');
            chip.setAttribute('data-repo', repo);
            chip.onclick = (e) => setRepoFilter(repo, e);
            chip.textContent = `${repo} (${repoMap[repo]})`;
            repoChipsContainer.appendChild(chip);
          }
        } else {
          repoSection.style.display = 'none';
        }
      }

      renderSkills();
    }

    function renderSkills() {
      const list = document.getElementById('skills-list');
      list.innerHTML = '';
      if (!scanResult) return;

      const filterInput = document.getElementById('filter-input');
      const filterText = filterInput ? filterInput.value.trim().toLowerCase() : '';
      const filterWords = filterText ? filterText.split(/\\s+/).filter(Boolean) : [];

      const starredSet = getStarredSet();
      const filtered = scanResult.skills.filter(sk => {
        if (activeStarredFilter && !starredSet.has(skillKey(sk))) {
          return false;
        }
        if (activeRepoFilter !== 'all') {
          const repo = sk.repo_name || 'local';
          if (repo !== activeRepoFilter) {
            return false;
          }
        }
        if (activeFilter !== 'all' && sk.origin !== activeFilter) {
          return false;
        }
        const isPassing = (sk.passing !== undefined && sk.passing !== null) ? sk.passing : sk.valid;
        if (activeStatusFilter === 'pass' && !isPassing) {
          return false;
        }
        if (activeStatusFilter === 'fail' && isPassing) {
          return false;
        }
        if (filterWords.length > 0) {
          const nameLower = (sk.name || '').toLowerCase();
          const descLower = (sk.description || '').toLowerCase();
          const tagsLower = (sk.tags || []).join(' ').toLowerCase();
          const pathLower = (sk.path || '').toLowerCase();
          const repoLower = (sk.repo_name || '').toLowerCase();
          const combined = `${nameLower} ${descLower} ${tagsLower} ${pathLower} ${repoLower}`;
          const matches = filterWords.every(w => combined.includes(w));
          if (!matches) {
            return false;
          }
        }
        return true;
      });

      if (filtered.length === 0) {
        const hasFilters = filterWords.length > 0 || activeFilter !== 'all' || activeRepoFilter !== 'all' || activeStatusFilter !== 'all' || activeStarredFilter;
        const msg = activeStarredFilter
          ? 'No starred skills yet. Click the star on a skill to add it here.'
          : (hasFilters
            ? 'No skills matching the filter.'
            : (activeFilter !== 'all' ? 'No skills in this category.' : 'No skills found.'));
        list.innerHTML = `<div style="text-align:center; padding:2rem; color:var(--text-muted);">${msg}</div>`;
        return;
      }

      for (const sk of filtered) {
        const item = document.createElement('div');
        item.className = 'skill-item';

        const header = document.createElement('div');
        header.className = 'skill-header';

        const titleDiv = document.createElement('div');
        titleDiv.className = 'skill-title';

        const isPassing = (sk.passing !== undefined && sk.passing !== null) ? sk.passing : sk.valid;
        const statusBadge = document.createElement('span');
        statusBadge.className = 'badge ' + (isPassing ? 'badge-success' : 'badge-error');
        statusBadge.textContent = isPassing ? 'PASS' : 'FAIL';

        const nameSpan = document.createElement('span');
        nameSpan.textContent = sk.name;
        nameSpan.style.cursor = 'pointer';
        nameSpan.title = 'View skill details';
        nameSpan.onclick = () => openSkillDetail(sk);

        const originBadge = document.createElement('span');
        originBadge.className = 'badge badge-primary';
        originBadge.textContent = sk.origin;

        titleDiv.appendChild(statusBadge);
        titleDiv.appendChild(nameSpan);
        titleDiv.appendChild(originBadge);

        if (sk.duplicates && sk.duplicates.length > 0) {
          const dupBadge = document.createElement('span');
          dupBadge.className = 'badge badge-magenta';
          dupBadge.textContent = `⧉ duplicated (${sk.duplicates.length + 1} copies)`;
          titleDiv.appendChild(dupBadge);
        }

        header.appendChild(titleDiv);

        const actionsDiv = document.createElement('div');
        actionsDiv.style.display = 'flex';
        actionsDiv.style.alignItems = 'center';
        actionsDiv.style.gap = '0.5rem';

        const simBtn = document.createElement('button');
        simBtn.className = 'btn-secondary';
        simBtn.style.padding = '0.25rem 0.55rem';
        simBtn.style.fontSize = '0.75rem';
        simBtn.textContent = '⧉ Similar';
        simBtn.title = `Find skills similar to ${sk.name}`;
        simBtn.onclick = () => findSimilarForSkill(sk.name);
        actionsDiv.appendChild(simBtn);

        actionsDiv.appendChild(createStarButton(sk, false));

        header.appendChild(actionsDiv);
        item.appendChild(header);

        if (sk.description) {
          const desc = document.createElement('div');
          desc.className = 'skill-desc';
          desc.textContent = sk.description;
          item.appendChild(desc);
        }

        const meta = document.createElement('div');
        meta.className = 'skill-meta';
        const pSpan = document.createElement('span');
        pSpan.textContent = `Path: ${sk.path}`;
        meta.appendChild(pSpan);
        if (sk.repo_name) {
          const rSpan = document.createElement('span');
          rSpan.textContent = `Repo: ${sk.repo_name}`;
          meta.appendChild(rSpan);
        }
        if (sk.updated_date) {
          const uSpan = document.createElement('span');
          uSpan.textContent = `Updated: ${sk.updated_date}`;
          meta.appendChild(uSpan);
        }
        if (sk.tags && sk.tags.length > 0) {
          const tSpan = document.createElement('span');
          tSpan.textContent = `Tags: ${sk.tags.join(', ')}`;
          meta.appendChild(tSpan);
        }
        item.appendChild(meta);

        if (sk.duplicates && sk.duplicates.length > 0) {
          const dupSection = document.createElement('div');
          dupSection.style.fontSize = '0.8rem';
          dupSection.style.color = 'var(--text-muted)';
          dupSection.style.marginBottom = '0.5rem';
          const dupLabel = document.createElement('div');
          dupLabel.textContent = 'Other copies:';
          dupSection.appendChild(dupLabel);
          sk.duplicates.forEach(d => {
            const status = d.identical ? 'identical' : 'differs';
            const dRow = document.createElement('div');
            dRow.textContent = `• ${d.path} (${d.updated_date || ''}) [${status}]`;
            dupSection.appendChild(dRow);
          });
          item.appendChild(dupSection);
        }

        if (sk.findings && sk.findings.length > 0) {
          const findingsList = document.createElement('div');
          findingsList.className = 'findings-list';
          for (const f of sk.findings) {
            const fRow = document.createElement('div');
            fRow.className = 'finding-row';
            const badgeClass = f.severity === 'ERROR' ? 'badge-error' : f.severity === 'WARN' ? 'badge-warn' : 'badge-primary';
            const bSpan = document.createElement('span');
            bSpan.className = `badge ${badgeClass}`;
            bSpan.textContent = f.severity;
            fRow.appendChild(bSpan);

            const ruleB = document.createElement('b');
            ruleB.textContent = ` ${f.rule_id}`;
            fRow.appendChild(ruleB);

            const loc = f.file ? ` (${f.file}${f.line ? ':' + f.line : ''})` : '';
            const msgSpan = document.createElement('span');
            msgSpan.textContent = `: ${f.message}${loc}`;
            fRow.appendChild(msgSpan);

            findingsList.appendChild(fRow);
          }
          item.appendChild(findingsList);
        }

        list.appendChild(item);
      }
    }

    function escapeHtml(str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    function downloadJson() {
      if (!scanResult) return;
      const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(scanResult, null, 2));
      const a = document.createElement('a');
      a.setAttribute('href', dataStr);
      a.setAttribute('download', 'skill-atlas-scan.json');
      document.body.appendChild(a);
      a.click();
      a.remove();
    }

    function closeSkillMap() {
      document.getElementById('map-section').style.display = 'none';
    }

    async function toggleSkillMap() {
      const section = document.getElementById('map-section');
      if (section.style.display === 'block') {
        section.style.display = 'none';
        return;
      }
      await loadSkillMap();
    }

    async function loadSkillMap() {
      if (!currentScanId) return;
      const section = document.getElementById('map-section');
      section.style.display = 'block';

      const methodSelect = document.getElementById('map-method');
      const method = methodSelect ? methodSelect.value : 'heuristic';

      const list = document.getElementById('map-clusters-list');
      list.innerHTML = '<div style="color:var(--text-muted); font-size:0.9rem; padding:0.5rem 0;">Generating skill map...</div>';

      try {
        const resp = await fetch(`/api/scans/${currentScanId}/map?method=${encodeURIComponent(method)}&replay=true`);
        if (!resp.ok) throw new Error('Failed to generate skill map');
        const data = await resp.json();

        document.getElementById('map-count').textContent =
          `${data.clusters.length} clusters · ${data.total_skills} skills (${data.method}${data.replayed ? ', replayed' : ''})`;

        list.innerHTML = '';
        if (!data.clusters || data.clusters.length === 0) {
          list.innerHTML = '<div style="color:var(--text-muted); font-size:0.9rem; padding:0.75rem 0;">No clusters formed.</div>';
          return;
        }

        for (const c of data.clusters) {
          const card = document.createElement('div');
          card.className = 'map-cluster-card';
          card.style.cssText = 'border:1px solid var(--border); border-radius:0.375rem; padding:0.85rem; background:var(--card-bg); display:flex; flex-direction:column; justify-content:space-between;';

          const topDiv = document.createElement('div');

          const headerDiv = document.createElement('div');
          headerDiv.style.cssText = 'display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem;';

          const titleSpan = document.createElement('span');
          titleSpan.style.cssText = 'font-weight:600; font-size:0.95rem; color:var(--text);';
          titleSpan.textContent = c.name;

          const countBadge = document.createElement('span');
          countBadge.className = 'badge badge-primary';
          countBadge.textContent = `${c.skills.length} skills`;

          headerDiv.appendChild(titleSpan);
          headerDiv.appendChild(countBadge);

          const reasonDiv = document.createElement('div');
          reasonDiv.style.cssText = 'color:var(--text-muted); font-size:0.825rem; margin-bottom:0.6rem; line-height:1.35;';
          reasonDiv.textContent = c.reason;

          topDiv.appendChild(headerDiv);
          topDiv.appendChild(reasonDiv);

          const skillsDiv = document.createElement('div');
          skillsDiv.style.cssText = 'display:flex; flex-wrap:wrap; gap:0.35rem; margin-top:0.25rem;';

          for (const sName of c.skills) {
            const pill = document.createElement('span');
            pill.style.cssText = 'background:rgba(59,130,246,0.1); color:var(--primary); border:1px solid rgba(59,130,246,0.25); border-radius:9999px; padding:0.15rem 0.5rem; font-size:0.75rem; font-weight:500; cursor:pointer; transition:background 0.15s;';
            pill.textContent = sName;
            pill.title = `Click to filter by ${sName}`;
            pill.onclick = () => filterByKeyword(sName);
            skillsDiv.appendChild(pill);
          }

          card.appendChild(topDiv);
          card.appendChild(skillsDiv);
          list.appendChild(card);
        }
      } catch (err) {
        list.innerHTML = `<div style="color:var(--error); font-size:0.9rem;">${err.message}</div>`;
      }
    }

    function closeSimilarSkills() {
      document.getElementById('similar-section').style.display = 'none';
      currentSimilarQuery = null;
    }

    function clearSimilarQuery() {
      currentSimilarQuery = null;
      loadSimilarSkills();
    }

    async function toggleSimilarSkills() {
      const section = document.getElementById('similar-section');
      if (section.style.display === 'block' && !currentSimilarQuery) {
        section.style.display = 'none';
        return;
      }
      currentSimilarQuery = null;
      await loadSimilarSkills();
    }

    async function findSimilarForSkill(skillName) {
      currentSimilarQuery = skillName;
      await loadSimilarSkills();
      const section = document.getElementById('similar-section');
      section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    async function loadSimilarSkills() {
      if (!currentScanId) return;
      const section = document.getElementById('similar-section');
      section.style.display = 'block';

      const banner = document.getElementById('similar-query-banner');
      if (currentSimilarQuery) {
        banner.style.display = 'flex';
        document.getElementById('similar-query-name').textContent = currentSimilarQuery;
      } else {
        banner.style.display = 'none';
      }

      const thresholdSelect = document.getElementById('similar-threshold');
      const threshold = thresholdSelect ? parseFloat(thresholdSelect.value) : 0.5;

      const list = document.getElementById('similar-list');
      list.innerHTML = '<div style="color:var(--text-muted); font-size:0.9rem; padding:0.5rem 0;">Finding similar skills...</div>';

      try {
        let url = `/api/scans/${currentScanId}/similar?threshold=${threshold}&top_k=20`;
        if (currentSimilarQuery) {
          url += `&skill=${encodeURIComponent(currentSimilarQuery)}`;
        }
        const resp = await fetch(url);
        if (!resp.ok) throw new Error('Failed to compute similarity');
        const data = await resp.json();

        document.getElementById('similar-count').textContent =
          `${data.matches.length} matches (threshold >= ${data.threshold})`;

        if (data.matches.length === 0) {
          list.innerHTML = '';
          const emptyDiv = document.createElement('div');
          emptyDiv.style.cssText = 'color:var(--text-muted); font-size:0.9rem; padding:0.75rem 0; text-align:center;';
          emptyDiv.textContent = `No similar skills found exceeding threshold >= ${data.threshold}.`;
          const hintDiv = document.createElement('div');
          hintDiv.style.cssText = 'font-size:0.8rem; margin-top:0.3rem;';
          hintDiv.textContent = 'Try selecting a lower threshold (e.g. 0.3 or 0.4) above.';
          emptyDiv.appendChild(hintDiv);
          list.appendChild(emptyDiv);
          return;
        }

        list.innerHTML = '';
        for (const m of data.matches) {
          const mDiv = document.createElement('div');
          mDiv.style.border = '1px solid var(--border)';
          mDiv.style.borderRadius = '0.375rem';
          mDiv.style.padding = '0.75rem';
          mDiv.style.marginBottom = '0.5rem';
          mDiv.style.background = 'var(--card-bg)';

          const pct = Math.round(m.score * 100);
          const badgeClass = pct >= 80 ? 'badge-success' : (pct >= 60 ? 'badge-warn' : 'badge-primary');

          const topRow = document.createElement('div');
          topRow.style.display = 'flex';
          topRow.style.justifyContent = 'space-between';
          topRow.style.alignItems = 'center';
          topRow.style.marginBottom = '0.4rem';

          const titleDiv = document.createElement('div');
          titleDiv.style.fontWeight = '600';
          titleDiv.style.fontSize = '0.95rem';

          const spanA = document.createElement('span');
          spanA.style.color = 'var(--primary)';
          spanA.style.cursor = 'pointer';
          spanA.textContent = m.skill_a;
          spanA.onclick = () => filterByKeyword(m.skill_a);

          const arrowSpan = document.createElement('span');
          arrowSpan.style.color = 'var(--text-muted)';
          arrowSpan.style.fontWeight = 'normal';
          arrowSpan.style.margin = '0 0.3rem';
          arrowSpan.textContent = '↔';

          const spanB = document.createElement('span');
          spanB.style.color = 'var(--primary)';
          spanB.style.cursor = 'pointer';
          spanB.textContent = m.skill_b;
          spanB.onclick = () => filterByKeyword(m.skill_b);

          titleDiv.appendChild(spanA);
          titleDiv.appendChild(arrowSpan);
          titleDiv.appendChild(spanB);

          const badgeSpan = document.createElement('span');
          badgeSpan.className = `badge ${badgeClass}`;
          badgeSpan.textContent = `${pct}% match`;

          topRow.appendChild(titleDiv);
          topRow.appendChild(badgeSpan);
          mDiv.appendChild(topRow);

          const pathsDiv = document.createElement('div');
          pathsDiv.style.fontSize = '0.8rem';
          pathsDiv.style.color = 'var(--text-muted)';
          pathsDiv.style.marginBottom = '0.4rem';

          const pA = document.createElement('div');
          pA.textContent = `• ${m.skill_a}: ${m.skill_a_path}`;
          const pB = document.createElement('div');
          pB.textContent = `• ${m.skill_b}: ${m.skill_b_path}`;
          pathsDiv.appendChild(pA);
          pathsDiv.appendChild(pB);
          mDiv.appendChild(pathsDiv);

          if (m.reasons && m.reasons.length > 0) {
            const reasonsDiv = document.createElement('div');
            reasonsDiv.style.fontSize = '0.85rem';
            for (const r of m.reasons) {
              const rDiv = document.createElement('div');
              rDiv.style.color = 'var(--text)';
              rDiv.style.marginTop = '0.2rem';
              rDiv.textContent = `↳ ${r}`;
              reasonsDiv.appendChild(rDiv);
            }
            mDiv.appendChild(reasonsDiv);
          }

          list.appendChild(mDiv);
        }
      } catch (err) {
        list.innerHTML = '';
        const errDiv = document.createElement('div');
        errDiv.style.color = 'var(--error)';
        errDiv.style.fontSize = '0.9rem';
        errDiv.textContent = `Error: ${err.message}`;
        list.appendChild(errDiv);
      }
    }

    function filterByKeyword(word) {
      const input = document.getElementById('filter-input');
      if (input) {
        input.value = word;
        renderSkills();
        input.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  </script>
</body>
</html>
"""


class ScanRequest(BaseModel):
    target: str = ""
    targets: list[str] = Field(default_factory=list)
    query: str | None = None
    ref: str | None = None
    fail_on: Literal["error", "warn"] = "error"
    rules: Literal["all", "schema", "security", "discovery"] = "all"
    ignore: list[str] = Field(default_factory=list)
    include_test_data: bool = False


class ScanJob:
    """Manages execution state, progress events, and cancellation for a scan."""

    def __init__(self, job_id: str, request: ScanRequest) -> None:
        self.id = job_id
        self.request = request
        self.status = "queued"
        self.result: ScanResult | None = None
        self.error: str | None = None
        self.events: list[ProgressEvent] = []
        self.cancel_event = threading.Event()
        self.listeners: list[asyncio.Queue[ProgressEvent]] = []
        self.loop: asyncio.AbstractEventLoop | None = None
        self.lock = threading.Lock()
        self.cached_all_matches: list[SimilarSkillMatch] | None = None

    def add_event(self, event: ProgressEvent) -> None:
        self.events.append(event)
        if self.loop:
            for q in list(self.listeners):
                self.loop.call_soon_threadsafe(q.put_nowait, event)

    def cancel(self) -> bool:
        with self.lock:
            if self.status in ("completed", "failed", "cancelled"):
                return False
            self.cancel_event.set()
            self.status = "cancelled"
            self.error = "Scan cancelled by user"
            return True


class JobManager:
    """In-memory coordinator for background scans with bounded concurrency and LRU eviction."""

    def __init__(self, max_jobs: int = 20) -> None:
        self.jobs: dict[str, ScanJob] = {}
        self.lock = threading.Lock()
        self.max_jobs = max_jobs
        self.queue: queue.Queue[tuple[ScanJob, Scanner]] = queue.Queue()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def create_job(self, req: ScanRequest) -> ScanJob:
        with self.lock:
            # Evict oldest completed/failed/cancelled jobs if limit reached (M7)
            finished_keys = [
                jid
                for jid, j in self.jobs.items()
                if j.status in ("completed", "failed", "cancelled")
            ]
            while len(self.jobs) >= self.max_jobs and finished_keys:
                evict_id = finished_keys.pop(0)
                self.jobs.pop(evict_id, None)

            job_id = str(uuid.uuid4())
            job = ScanJob(job_id, req)
            self.jobs[job_id] = job
            return job

    def enqueue(self, job: ScanJob, scanner: Scanner) -> None:
        self.queue.put((job, scanner))

    def _worker_loop(self) -> None:
        while True:
            job, scanner = self.queue.get()
            try:
                with job.lock:
                    if job.status == "cancelled":
                        continue
                    job.status = "running"
                try:
                    effective_targets = job.request.targets or (
                        [job.request.target] if job.request.target else ["."]
                    )
                    res = scanner.scan(
                        targets=effective_targets,
                        ref=job.request.ref,
                        query=job.request.query,
                        include_test_data=job.request.include_test_data,
                        on_progress=job.add_event,
                        cancel_event=job.cancel_event,
                    )
                    with job.lock:
                        if job.status != "cancelled":
                            job.result = res
                            job.status = "completed"
                except Exception as err:  # noqa: BLE001
                    with job.lock:
                        if job.cancel_event.is_set() or job.status == "cancelled":
                            job.status = "cancelled"
                            job.error = "Scan cancelled by user"
                        else:
                            job.status = "failed"
                            job.error = str(err)
            finally:
                self.queue.task_done()

    def get_job(self, job_id: str) -> ScanJob | None:
        with self.lock:
            return self.jobs.get(job_id)


def create_app(
    allow_local: bool = False,
    scanner: Scanner | None = None,
    job_manager: JobManager | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> FastAPI:
    """Create configured FastAPI application."""
    app = FastAPI(title="Skill Atlas Web", version=__version__)
    app.state.csrf_token = secrets.token_hex(16)

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )

    manager = job_manager or JobManager()
    allowed_origins = {
        f"http://{host}:{port}",
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
        "http://testserver",
        "https://testserver",
    }

    @app.middleware("http")
    async def origin_and_security_headers(request: Request, call_next: Any) -> Response:
        origin = request.headers.get("origin")
        if origin:
            clean_origin = origin.rstrip("/")
            if clean_origin not in allowed_origins:
                return Response(
                    content='{"detail": "Forbidden: cross-origin requests are not allowed"}',
                    status_code=403,
                    media_type="application/json",
                )
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';"
        )
        return response

    _health_cache: dict[str, Any] = {"time": 0.0, "data": None}

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return HTML_CONTENT.replace("{{CSRF_TOKEN}}", app.state.csrf_token)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        now = time.time()
        if _health_cache["data"] is not None and (now - _health_cache["time"]) < 30.0:
            return _health_cache["data"]

        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        gh_client = GitHubClient(token=token)
        rem = gh_client.get_rate_limit()
        data = {
            "version": __version__,
            "status": "healthy",
            "github_token_configured": bool(gh_client.token),
            "rate_limit_remaining": rem,
        }
        _health_cache["time"] = now
        _health_cache["data"] = data
        return data

    @app.post("/api/scans")
    def start_scan(req: ScanRequest, request: Request) -> dict[str, str]:
        # Validate CSRF token if Origin header is present
        origin = request.headers.get("origin")
        if origin:
            tok = request.headers.get("x-skillatlas-token")
            if tok != app.state.csrf_token:
                raise HTTPException(status_code=403, detail="Invalid CSRF token")

        raw_targets: list[str] = []
        if req.targets:
            raw_targets.extend(req.targets)
        if req.target:
            raw_targets.append(req.target)

        parsed_targets: list[str] = []
        for item in raw_targets:
            for line in str(item).splitlines():
                for part in line.split(","):
                    cleaned = part.strip()
                    if cleaned:
                        parsed_targets.append(cleaned)

        if not parsed_targets:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="At least one target repository or directory must be provided",
            )

        effective_targets = normalize_targets(parsed_targets)

        # Input validation per SPEC
        if not allow_local:
            for t in effective_targets:
                if parse_github_url(t) is None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Only GitHub repository URLs are supported for scanning",
                    )

        req.targets = effective_targets
        req.target = effective_targets[0] if effective_targets else ""

        job = manager.create_job(req)
        scan_to_use = scanner or Scanner(
            rules_category=req.rules,
            ignored_rules=req.ignore,
            fail_on=req.fail_on,
            include_test_data=req.include_test_data,
        )
        manager.enqueue(job, scan_to_use)
        return {"scan_id": job.id}

    @app.get("/api/scans/{scan_id}/events")
    async def get_scan_events(scan_id: str, request: Request) -> StreamingResponse:
        job = manager.get_job(scan_id)
        if not job:
            raise HTTPException(status_code=404, detail="Scan not found")

        loop = asyncio.get_running_loop()
        job.loop = loop

        async def event_generator():
            # 1. Replay historical events
            for ev in list(job.events):
                yield f"data: {ev.model_dump_json()}\n\n"

            if job.status in ("completed", "failed", "cancelled"):
                return

            # 2. Listen to active events
            q: asyncio.Queue[ProgressEvent] = asyncio.Queue()
            job.listeners.append(q)
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        ev = await asyncio.wait_for(q.get(), timeout=1.0)
                        yield f"data: {ev.model_dump_json()}\n\n"
                        if ev.stage in (Stage.DONE, Stage.ERROR):
                            break
                    except TimeoutError:
                        if job.status in ("completed", "failed", "cancelled"):
                            break
            finally:
                if q in job.listeners:
                    job.listeners.remove(q)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    @app.get("/api/scans/{scan_id}")
    def get_scan_result(scan_id: str) -> Any:
        job = manager.get_job(scan_id)
        if not job:
            raise HTTPException(status_code=404, detail="Scan not found")

        if job.status == "completed" and job.result:
            return JSONResponse(content=job.result.model_dump())
        if job.status == "failed":
            raise HTTPException(status_code=500, detail=job.error or "Scan failed")
        if job.status == "cancelled":
            raise HTTPException(status_code=400, detail="Scan was cancelled")

        return {"status": job.status, "message": "Scan in progress"}

    @app.get("/api/scans/{scan_id}/similar")
    def get_scan_similar_skills(
        scan_id: str,
        threshold: float = 0.5,
        skill: str | None = None,
        top_k: int = 10,
    ) -> Any:
        if not (0.0 <= threshold <= 1.0):
            raise HTTPException(status_code=422, detail="threshold must be between 0.0 and 1.0")
        if not (1 <= top_k <= 100):
            raise HTTPException(status_code=422, detail="top_k must be between 1 and 100")

        job = manager.get_job(scan_id)
        if not job:
            raise HTTPException(status_code=404, detail="Scan not found")
        if job.status != "completed" or not job.result:
            raise HTTPException(status_code=400, detail="Scan is not completed")

        skills = job.result.skills
        if not job.request.include_test_data:
            skills = [s for s in skills if s.origin != SkillOrigin.TEST_DATA]

        with job.lock:
            if not skill:
                if job.cached_all_matches is None:
                    full_res = find_similar_skills(
                        skills=skills,
                        query_skill=None,
                        threshold=0.0,
                        top_k=0,
                        target=job.request.target,
                    )
                    job.cached_all_matches = full_res.matches
                filtered_matches = [m for m in job.cached_all_matches if m.score >= threshold][
                    :top_k
                ]
                sim_res = SimilarSkillsResult(
                    target=job.request.target,
                    threshold=threshold,
                    total_skills=len(skills),
                    matches=filtered_matches,
                )
            else:
                sim_res = find_similar_skills(
                    skills=skills,
                    query_skill=skill,
                    threshold=threshold,
                    top_k=top_k,
                    target=job.request.target,
                )
        return JSONResponse(content=sim_res.model_dump())

    @app.get("/api/scans/{scan_id}/map")
    def get_scan_skill_map(
        scan_id: str,
        method: str = "heuristic",
        threshold: float = 0.35,
        replay: bool = True,
    ) -> Any:
        job = manager.get_job(scan_id)
        if not job:
            raise HTTPException(status_code=404, detail="Scan not found")
        if job.status != "completed" or not job.result:
            raise HTTPException(status_code=400, detail="Scan is not completed")

        skills = job.result.skills
        if not job.request.include_test_data:
            skills = [s for s in skills if s.origin != SkillOrigin.TEST_DATA]

        method_clean = method.lower().strip()
        if method_clean not in ("heuristic", "ai", "jev"):
            raise HTTPException(
                status_code=422, detail="method must be 'heuristic', 'ai', or 'jev'"
            )

        from skill_atlas.map import (
            classify_skills_jev,
            cluster_skills_ai,
            group_skills_heuristic,
        )

        if method_clean == "jev":
            replay_p = Path("tests/fixtures/recorded_jev_map_visual.json") if replay else None
            map_res = classify_skills_jev(skills, replay_file=replay_p)
        elif method_clean == "ai":
            replay_p = Path("tests/fixtures/recorded_claude_map_visual.json") if replay else None
            map_res = cluster_skills_ai(skills, replay_file=replay_p)
        else:
            map_res = group_skills_heuristic(skills, threshold=threshold)

        return JSONResponse(content=map_res.model_dump())

    @app.delete("/api/scans/{scan_id}")
    def cancel_scan_endpoint(scan_id: str, request: Request) -> dict[str, str]:
        origin = request.headers.get("origin")
        if origin:
            tok = request.headers.get("x-skillatlas-token")
            if tok != app.state.csrf_token:
                raise HTTPException(status_code=403, detail="Invalid CSRF token")

        job = manager.get_job(scan_id)
        if not job:
            raise HTTPException(status_code=404, detail="Scan not found")
        success = job.cancel()
        if not success:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot cancel scan in '{job.status}' state",
            )
        return {"status": "cancelled"}

    return app


def run_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    allow_local: bool = False,
    reload: bool = False,
) -> None:
    """Launch Uvicorn server hosting Skill Atlas web interface."""
    import uvicorn

    if host == "0.0.0.0":  # noqa: S104
        print("⚠️  Warning: Binding server to 0.0.0.0 exposes Skill Atlas to your local network.")

    if reload:
        if open_browser:
            threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()
        print(f"🚀 Skill Atlas Web Interface running at http://{host}:{port} (auto-reload enabled)")
        uvicorn.run(
            "skill_atlas.web:create_app",
            host=host,
            port=port,
            log_level="info",
            reload=True,
            factory=True,
        )
        return

    app = create_app(allow_local=allow_local, host=host, port=port)

    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()

    print(f"🚀 Skill Atlas Web Interface running at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
