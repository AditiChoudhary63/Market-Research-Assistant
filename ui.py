"""
HTML_UI — single-page application served at GET /.
Imported by api.py and returned via FastAPI's HTMLResponse.
"""

HTML_UI = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Market Intelligence Platform</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/marked@9/marked.min.js"></script>
  <style>
    .prose h2{font-size:1.15rem;font-weight:700;margin-top:1.4rem;margin-bottom:.4rem;color:#1d4ed8}
    .prose h3{font-size:1rem;font-weight:600;margin-top:1rem;margin-bottom:.3rem;color:#374151}
    .prose ul{list-style-type:disc;margin-left:1.4rem;margin-bottom:.8rem}
    .prose li{margin-bottom:.2rem;line-height:1.6}
    .prose p{margin-bottom:.65rem;line-height:1.7}
    .prose a{color:#2563eb;text-decoration:underline}
    .spin{border:2.5px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;
           width:1rem;height:1rem;animation:spin .7s linear infinite;display:inline-block}
    @keyframes spin{to{transform:rotate(360deg)}}
    ::-webkit-scrollbar{width:5px} ::-webkit-scrollbar-thumb{background:#d1d5db;border-radius:9px}
  </style>
</head>
<body class="bg-slate-50 text-gray-800">

<!-- ── Login overlay ─────────────────────────────────────────────────── -->
<div id="loginOverlay"
     class="fixed inset-0 bg-slate-900/75 backdrop-blur-sm flex items-center justify-center z-50">
  <div class="bg-white rounded-2xl shadow-2xl p-8 w-full max-w-sm mx-4">
    <div class="text-center mb-7">
      <div class="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-blue-600 mb-3">
        <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/>
        </svg>
      </div>
      <h1 class="text-xl font-bold text-gray-900">Market Intelligence</h1>
      <p class="text-sm text-gray-500 mt-1">Sign in to continue</p>
    </div>
    <div id="loginErr"
         class="hidden mb-4 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm"></div>
    <form id="loginForm" class="space-y-4">
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Username</label>
        <input id="username" type="text" required autocomplete="username"
               class="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm
                      focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
               placeholder="admin" />
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Password</label>
        <input id="password" type="password" required autocomplete="current-password"
               class="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm
                      focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
               placeholder="••••••••" />
      </div>
      <button type="button" id="loginBtn"
              class="w-full flex items-center justify-center gap-2 py-2.5 bg-blue-600
                     hover:bg-blue-700 text-white text-sm font-semibold rounded-lg transition-colors">
        <span>Sign In</span>
      </button>
    </form>
  </div>
</div>

<!-- ── Main app ──────────────────────────────────────────────────────── -->
<div id="mainApp" class="hidden h-screen flex overflow-hidden">

  <!-- Sidebar -->
  <aside class="w-64 shrink-0 bg-white border-r border-gray-200 flex flex-col">
    <div class="px-5 py-4 border-b border-gray-100">
      <p class="text-xs font-semibold text-blue-600 uppercase tracking-widest">Platform</p>
      <h1 class="text-base font-bold text-gray-900 mt-0.5">Market Intelligence</h1>
    </div>
    <div class="flex-1 overflow-y-auto px-3 py-4">
      <div class="flex items-center justify-between mb-2 px-2">
        <span class="text-xs font-semibold text-gray-500 uppercase tracking-wider">Recent Runs</span>
        <button onclick="loadHistory()"
                class="text-xs text-blue-600 hover:text-blue-800 font-medium">↺ Refresh</button>
      </div>
      <div id="historyList" class="space-y-1">
        <p class="text-xs text-gray-400 px-2 py-3">No runs yet.</p>
      </div>
    </div>
    <div class="px-5 py-3 border-t border-gray-100">
      <button onclick="logout()"
              class="text-xs text-gray-400 hover:text-red-500 transition-colors">Sign out</button>
    </div>
  </aside>

  <!-- Content -->
  <main class="flex-1 overflow-y-auto bg-slate-50">
    <div class="max-w-3xl mx-auto px-6 py-8 space-y-6">

      <!-- Research form card -->
      <div class="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
        <h2 class="text-lg font-semibold text-gray-900">New Research Run</h2>
        <p class="text-sm text-gray-500 mt-0.5 mb-5">
          Enter competitors and source URLs to generate a structured market intelligence report.
        </p>
        <form id="researchForm" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Competitors / Topics
              <span class="text-gray-400 font-normal">(one per line)</span>
            </label>
            <textarea id="competitors" rows="3" required
                      class="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm font-mono
                             focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none resize-none"
                      placeholder="OpenAI&#10;Anthropic&#10;Google DeepMind"></textarea>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Source URLs
              <span class="text-gray-400 font-normal">(one per line — blogs, announcements, articles)</span>
            </label>
            <textarea id="sourceUrls" rows="4" required
                      class="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm font-mono
                             focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none resize-none"
                      placeholder="https://openai.com/blog&#10;https://www.anthropic.com/news"></textarea>
          </div>
          <div id="formError" class="hidden px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm"></div>
          <button type="submit" id="submitBtn"
                  class="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700
                         disabled:opacity-60 text-white text-sm font-semibold rounded-lg transition-colors">
            <span id="submitLabel">Generate Report</span>
            <span id="submitSpin" class="spin hidden"></span>
          </button>
        </form>
      </div>

      <!-- Pipeline progress (shown while streaming) -->
      <div id="progressPanel" class="hidden bg-white rounded-2xl border border-gray-200 shadow-sm p-5 space-y-3">
        <h3 class="text-sm font-semibold text-gray-700 tracking-wide uppercase">Pipeline Progress</h3>
        <div id="progressSteps" class="space-y-2"></div>
        <!-- Live report shimmer while tokens are streaming -->
        <div id="liveReportWrap" class="hidden mt-4 pt-4 border-t border-gray-100">
          <p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Live Report</p>
          <div id="liveReport"
               class="prose prose-sm max-w-none text-gray-800 text-sm leading-relaxed
                      min-h-[6rem]"></div>
        </div>
      </div>

      <!-- Results (hidden until a run completes) -->
      <div id="results" class="hidden space-y-5">

        <!-- Summary card -->
        <div class="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
          <h3 class="font-semibold text-gray-900 mb-4">Intelligence Report</h3>
          <div id="summaryContent" class="prose text-sm text-gray-700 max-w-none"></div>
        </div>

        <!-- Sources card -->
        <div class="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
          <h3 class="font-semibold text-gray-900 mb-3">Sources Analysed</h3>
          <div id="sourcesList" class="space-y-1.5"></div>
        </div>

        <!-- Validation card -->
        <div class="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
          <div class="flex items-start justify-between gap-4">
            <div class="flex-1 min-w-0">
              <h3 class="font-semibold text-gray-900 mb-1">Validation</h3>
              <p id="vSummary" class="text-sm text-gray-500 leading-relaxed"></p>
              <p id="vMediumNote" class="hidden mt-1.5 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-1.5 leading-relaxed">
                <strong>Medium quality</strong> means most claims are supported by the source context, but a few are only partially backed or lack direct evidence. The report is usable but treat highlighted claims with caution.
              </p>
            </div>
            <div class="text-right shrink-0">
              <span id="vBadge" class="text-xs font-bold px-2.5 py-1 rounded-full"></span>
              <p id="vScore" class="text-3xl font-bold mt-1.5"></p>
            </div>
          </div>
          <!-- Claim-by-claim analysis -->
          <div id="claimAnalysisSection" class="hidden mt-4 pt-4 border-t border-gray-100">
            <p class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              Claim Analysis
            </p>
            <div id="claimAnalysisList" class="space-y-2"></div>
          </div>
          <div id="claimsSection" class="hidden mt-4 pt-4 border-t border-gray-100">
            <p class="text-xs font-semibold text-red-500 uppercase tracking-wider mb-2">
              ⚠ Flagged Claims
            </p>
            <ul id="claimsList" class="space-y-1.5"></ul>
          </div>
          <div id="improvementsSection" class="hidden mt-3">
            <p class="text-xs font-semibold text-amber-600 uppercase tracking-wider mb-2">
              💡 Suggested Improvements
            </p>
            <ul id="improvementsList" class="space-y-1.5"></ul>
          </div>
        </div>

      </div>
    </div>
  </main>
</div>

<script>
  // ── State ──────────────────────────────────────────────────────────────────
  let token = localStorage.getItem('mi_token');

  // ── Bootstrap ──────────────────────────────────────────────────────────────
  token ? showApp() : showLogin();

  // ── Auth helpers ───────────────────────────────────────────────────────────
  function showLogin() {
    document.getElementById('loginOverlay').classList.remove('hidden');
    document.getElementById('mainApp').classList.add('hidden');
  }
  function showApp() {
    document.getElementById('loginOverlay').classList.add('hidden');
    document.getElementById('mainApp').classList.remove('hidden');
    loadHistory();
  }
  function logout() {
    localStorage.removeItem('mi_token');
    token = null;
    showLogin();
  }
  function authHeaders() {
    return { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' };
  }

  // ── Login ───────────────────────────────────────────────────────────────────
  async function doLogin() {
    const errEl = document.getElementById('loginErr');
    errEl.classList.add('hidden');
    const btn = document.getElementById('loginBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>';

    const body = new URLSearchParams({
      username: document.getElementById('username').value,
      password: document.getElementById('password').value,
    });
    try {
      const res = await fetch('/auth/login', {
        method: 'POST', body,
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail || 'Login failed'); }
      const data = await res.json();
      token = data.access_token;
      localStorage.setItem('mi_token', token);
      showApp();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove('hidden');
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<span>Sign In</span>';
    }
  }

  document.getElementById('loginBtn').addEventListener('click', doLogin);
  document.getElementById('password').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') doLogin();
  });

  // ── Progress panel helpers ─────────────────────────────────────────────────
  const NODE_LABELS = {
    tavily_search: 'Competitor Research',
    html_loader:   'Content Fetching',
    embedding:     'Vector Indexing',
    llm_invoke:    'Report Generation',
    validation:    'Quality Validation',
  };
  const NODE_ICONS = {
    tavily_search: '🔍',
    html_loader:   '📄',
    embedding:     '🧠',
    llm_invoke:    '\u270D\uFE0F',
    validation:    '\u2713',
  };

  function upsertStep(node, phase, message) {
    const stepsEl = document.getElementById('progressSteps');
    let row = document.getElementById('step-' + node);
    if (!row) {
      row = document.createElement('div');
      row.id = 'step-' + node;
      row.className = 'flex items-start gap-3 text-sm';
      stepsEl.appendChild(row);
    }
    const running = phase === 'start';
    const icon = running
      ? '<span class="spin mt-0.5 shrink-0" style="border-color:rgba(59,130,246,.3);border-top-color:#3b82f6"></span>'
      : '<span class="shrink-0 w-4 h-4 rounded-full bg-green-100 text-green-600 flex items-center justify-center text-xs font-bold">\u2713</span>';
    row.innerHTML = icon +
      '<div><span class="font-medium text-gray-700">' + (NODE_LABELS[node] || node) + '</span>' +
      '<span class="ml-2 text-gray-400 text-xs">' + message + '</span></div>';
  }

  function showRetryBanner(attempt, message) {
    const stepsEl = document.getElementById('progressSteps');
    const banner = document.createElement('div');
    banner.className = 'flex items-center gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg text-amber-700 text-xs font-medium';
    banner.innerHTML = '🔄 ' + message;
    stepsEl.appendChild(banner);
  }

  function resetProgress() {
    document.getElementById('progressSteps').innerHTML = '';
    document.getElementById('liveReport').innerHTML = '';
    document.getElementById('liveReportWrap').classList.add('hidden');
    document.getElementById('progressPanel').classList.remove('hidden');
    document.getElementById('results').classList.add('hidden');
  }

  // ── Research form — streaming ──────────────────────────────────────────────
  document.getElementById('researchForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = document.getElementById('formError');
    errEl.classList.add('hidden');
    const btn = document.getElementById('submitBtn');
    btn.disabled = true;
    document.getElementById('submitLabel').textContent = 'Running\u2026';
    document.getElementById('submitSpin').classList.remove('hidden');

    const competitors = document.getElementById('competitors').value
      .split('\\n').map(s => s.trim().replace(/^["',\\s]+|["',\\s]+$/g, '')).filter(Boolean);
    const urls = document.getElementById('sourceUrls').value
      .split('\\n').map(s => s.trim().replace(/^["'\\s]+|["'\\s]+$/g, '')).filter(Boolean);

    resetProgress();
    let liveText = '';

    try {
      const res = await fetch('/research/stream', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ competitors, urls }),
      });
      if (res.status === 401) { logout(); return; }
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.detail || 'Pipeline failed');
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        // SSE lines are separated by \\n\\n
        const parts = buf.split('\\n\\n');
        buf = parts.pop();          // keep incomplete last chunk

        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith('data:')) continue;
          let evt;
          try { evt = JSON.parse(line.slice(5).trim()); } catch { continue; }

          if (evt.type === 'status') {
            upsertStep(evt.node, evt.phase, evt.message);

            // Show live report area when generation starts
            if (evt.node === 'llm_invoke' && evt.phase === 'start') {
              document.getElementById('liveReportWrap').classList.remove('hidden');
            }

          } else if (evt.type === 'retry') {
            showRetryBanner(evt.attempt, evt.message);
            // Reset live text for the new attempt
            liveText = '';
            document.getElementById('liveReport').innerHTML = '';

          } else if (evt.type === 'token') {
            liveText += evt.content;
            document.getElementById('liveReport').innerHTML = marked.parse(liveText);

          } else if (evt.type === 'complete') {
            document.getElementById('progressPanel').classList.add('hidden');
            renderResults(evt.result);
            loadHistory();

          } else if (evt.type === 'error') {
            throw new Error(evt.message);
          }
        }
      }
    } catch (err) {
      document.getElementById('progressPanel').classList.add('hidden');
      errEl.textContent = 'Error: ' + err.message;
      errEl.classList.remove('hidden');
    } finally {
      btn.disabled = false;
      document.getElementById('submitLabel').textContent = 'Generate Report';
      document.getElementById('submitSpin').classList.add('hidden');
    }
  });

  // ── Render results ─────────────────────────────────────────────────────────
  function renderResults(data) {
    const v = data.validation;
    const quality = v.quality || 'low';
    const valid = data.is_valid;

    const badge = document.getElementById('vBadge');
    const isMedium = quality === 'medium';
    if (valid) {
      badge.textContent = '\u2713 Verified';
      badge.className = 'text-xs font-bold px-2.5 py-1 rounded-full bg-green-100 text-green-700';
    } else if (isMedium) {
      badge.textContent = '\u26A0 Partial';
      badge.className = 'text-xs font-bold px-2.5 py-1 rounded-full bg-amber-100 text-amber-700';
    } else {
      badge.textContent = '\u2717 Invalid';
      badge.className = 'text-xs font-bold px-2.5 py-1 rounded-full bg-red-100 text-red-700';
    }

    const scoreEl = document.getElementById('vScore');
    scoreEl.textContent = quality.toUpperCase();
    scoreEl.className = 'text-3xl font-bold mt-1.5 ' +
      (quality === 'very high' ? 'text-green-600' : quality === 'high' ? 'text-lime-500' : quality === 'medium' ? 'text-amber-500' : 'text-red-600');

    const mediumNote = document.getElementById('vMediumNote');
    if (isMedium) {
      mediumNote.classList.remove('hidden');
    } else {
      mediumNote.classList.add('hidden');
    }

    const summaryText = quality === 'very high'
      ? 'All claims are fully supported by the source context.'
      : (v.summary || v.reasoning || '');
    document.getElementById('vSummary').textContent = summaryText;

    // Claim-by-claim analysis table
    const claimAnalysis = v.claim_analysis || [];
    const claimAnalysisSection = document.getElementById('claimAnalysisSection');
    if (claimAnalysis.length) {
      const statusStyle = {
        SUPPORTED:           'bg-green-50 text-green-700 border-green-100',
        NOT_SUPPORTED:       'bg-red-50 text-red-700 border-red-100',
        PARTIALLY_SUPPORTED: 'bg-amber-50 text-amber-700 border-amber-100',
      };
      document.getElementById('claimAnalysisList').innerHTML = claimAnalysis.map(c => `
        <div class="rounded-lg border p-3 text-xs space-y-1 ${statusStyle[c.status] || 'bg-gray-50 border-gray-100 text-gray-700'}">
          <div class="flex items-center justify-between gap-2">
            <span class="font-semibold">${c.status.replace(/_/g, ' ')}</span>
            <span class="text-gray-400 truncate max-w-[180px]">${c.source || ''}</span>
          </div>
          <p class="leading-relaxed">${c.claim}</p>
          ${c.evidence && c.evidence !== 'NONE'
            ? `<p class="opacity-70 italic">${c.evidence}</p>`
            : ''}
        </div>`).join('');
      claimAnalysisSection.classList.remove('hidden');
    } else {
      claimAnalysisSection.classList.add('hidden');
    }

    const claims = v.hallucinated_claims || [];
    const claimsSection = document.getElementById('claimsSection');
    if (claims.length) {
      document.getElementById('claimsList').innerHTML =
        claims.map(c => `<li class="text-xs text-red-600 bg-red-50 border border-red-100
                                    rounded px-2.5 py-1.5 leading-relaxed">${c}</li>`).join('');
      claimsSection.classList.remove('hidden');
    } else {
      claimsSection.classList.add('hidden');
    }

    const imps = v.improvements || [];
    const impsSection = document.getElementById('improvementsSection');
    if (imps.length) {
      document.getElementById('improvementsList').innerHTML =
        imps.map(i => `<li class="text-xs text-amber-700 bg-amber-50 border border-amber-100
                                   rounded px-2.5 py-1.5 leading-relaxed">${i}</li>`).join('');
      impsSection.classList.remove('hidden');
    } else {
      impsSection.classList.add('hidden');
    }

    document.getElementById('summaryContent').innerHTML =
      marked.parse(data.summary || '');

    const allUrls = [...new Set([...(data.urls || []), ...(data.tavily_urls || [])])];
    document.getElementById('sourcesList').innerHTML = allUrls.length
      ? allUrls.map(u =>
          `<a href="${u}" target="_blank" rel="noopener"
              class="flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-800
                     hover:underline truncate">
             <svg class="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
               <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                     d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/>
             </svg>${u}</a>`).join('')
      : '<p class="text-xs text-gray-400">No sources recorded.</p>';

    document.getElementById('results').classList.remove('hidden');
    document.getElementById('results').scrollIntoView({ behavior: 'smooth' });
  }

  // ── History ────────────────────────────────────────────────────────────────
  async function loadHistory() {
    try {
      const res = await fetch('/history', { headers: authHeaders() });
      if (res.status === 401) { logout(); return; }
      const items = await res.json();
      const el = document.getElementById('historyList');
      if (!items.length) {
        el.innerHTML = '<p class="text-xs text-gray-400 px-2 py-3">No runs yet.</p>';
        return;
      }
      el.innerHTML = items.map(item => `
        <button onclick="loadRun('${item.id}')"
                class="w-full text-left px-3 py-2.5 rounded-lg hover:bg-slate-50
                       border border-transparent hover:border-gray-200 transition-all">
          <div class="flex items-center justify-between gap-1 mb-0.5">
            <span class="text-xs font-medium text-gray-800 truncate">
              ${item.competitors.slice(0,2).join(', ')}${item.competitors.length > 2 ? ' +' + (item.competitors.length - 2) : ''}
            </span>
            <span class="text-xs font-bold shrink-0 ${item.is_valid ? 'text-green-600' : 'text-red-500'}">
              ${(item.quality || 'low').toUpperCase()}
            </span>
          </div>
          <p class="text-xs text-gray-400">${new Date(item.created_at).toLocaleString()}</p>
        </button>`).join('');
    } catch (err) {
      console.error('History load error', err);
    }
  }

  async function loadRun(id) {
    try {
      const res = await fetch('/history/' + id, { headers: authHeaders() });
      if (!res.ok) return;
      const data = await res.json();
      document.getElementById('competitors').value = data.competitors.join('\\n');
      document.getElementById('sourceUrls').value = data.urls.join('\\n');
      renderResults(data);
    } catch (err) {
      console.error('Run load error', err);
    }
  }
</script>
</body>
</html>"""
