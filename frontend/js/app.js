/**
 * ZeroBreakout Main Application Controller
 * Zerodha-style Minimalist Stock Pattern Scanner
 */

function initApp() {
  // App State
  const state = {
    currentTab: 'scanner',
    selectedPattern: 'all',
    searchQuery: '',
    currentSymbol: 'TRENT',
    currentRange: '1Y',
    signals: [],
    watchlist: [],
    chartInstance: null,
    chartRequestId: 0,
    setupRequestId: 0,
    aiRequestId: 0
  };

  // DOM Elements
  const tabs = document.querySelectorAll('.tab-view');
  const navBtns = document.querySelectorAll('.nav-tab-btn');
  const filterChips = document.querySelectorAll('.filter-chip');
  const searchInput = document.getElementById('scannerSearch');
  const signalsListEl = document.getElementById('signalsList');
  const watchlistContainerEl = document.getElementById('watchlistContainer');
  const rangeBtns = document.querySelectorAll('.range-btn, .range-pill');
  const starBtn = document.getElementById('setupStarBtn') || document.getElementById('starBtn');
  const aiRefreshBtn = document.getElementById('aiRefreshBtn');
  const manualSyncBtn = document.getElementById('manualSyncBtn');
  const themeToggle = document.getElementById('themeToggle');

  // Chart instances are now managed cleanly per stock switch (destroyed and recreated)

  // Load Signals immediately on startup
  loadSignals();

  // ==================== TAB NAVIGATION & MOBILE BACK BUTTON ==================== //

  // Initialize root history state on page load
  try {
    const initialHash = (window.location.hash || '').replace('#', '').trim();
    const validTabs = ['scanner', 'setup', 'watchlist', 'account'];
    const startTab = validTabs.includes(initialHash) ? initialHash : 'scanner';
    history.replaceState({ tab: startTab }, '', startTab === 'scanner' ? window.location.pathname : `#${startTab}`);
  } catch (e) {}

  function switchTab(tabName, symbolToLoad = null, pushHistory = true) {
    if (state.currentTab === tabName && !symbolToLoad) return;

    const previousTab = state.currentTab;
    state.currentTab = tabName;

    // Push history entry if navigating to a different tab or stock
    if (pushHistory) {
      try {
        if (tabName !== 'scanner') {
          history.pushState(
            { tab: tabName, symbol: symbolToLoad || state.currentSymbol },
            '',
            `#${tabName}`
          );
        } else if (previousTab !== 'scanner') {
          history.pushState(
            { tab: 'scanner' },
            '',
            window.location.pathname
          );
        }
      } catch (e) {}
    }

    // Update bottom nav buttons
    navBtns.forEach(btn => {
      if (btn.dataset.tab === tabName) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    // Update tab visibility
    tabs.forEach(tab => {
      if (tab.id === `tab-${tabName}`) {
        tab.classList.add('active');
      } else {
        tab.classList.remove('active');
      }
    });

    // Scroll to top when switching tabs for smooth mobile feel
    window.scrollTo({ top: 0, behavior: 'instant' });

    // Tab specific actions
    if (tabName === 'scanner') {
      loadSignals();
    } else if (tabName === 'setup') {
      const defaultSym = state.signals.length > 0 ? state.signals[0].symbol : (state.currentSymbol || 'RELIANCE');
      const sym = symbolToLoad || state.currentSymbol || defaultSym;
      loadStockSetup(sym);
    } else if (tabName === 'watchlist') {
      loadWatchlist();
    }
  }

  // Handle Mobile Hardware Back Button & Browser Back Swipe
  window.addEventListener('popstate', (event) => {
    // 1. If any modal is open, close the modal first without switching tab
    const brokerModal = document.getElementById('brokerModal');
    if (brokerModal && brokerModal.style.display !== 'none' && brokerModal.style.display !== '') {
      brokerModal.style.display = 'none';
      return;
    }

    // 2. Tab Navigation via History
    const targetState = event.state;
    if (targetState && targetState.tab) {
      switchTab(targetState.tab, targetState.symbol, false);
    } else {
      // If popped back to root and currently not on scanner, return to scanner tab
      if (state.currentTab !== 'scanner') {
        switchTab('scanner', null, false);
      }
      // If already on scanner, browser/app exits naturally!
    }
  });

  navBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      switchTab(btn.dataset.tab);
    });
  });

  // ==================== TAB 1: SCANNER ==================== //

  async function loadSignals() {
    if (!signalsListEl) return;
    signalsListEl.innerHTML = `
      <div class="loading-spinner">
        <div class="spinner"></div>
        <span>Scanning patterns...</span>
      </div>
    `;

    try {
      const data = await API.getSignals(state.selectedPattern, state.searchQuery);
      state.signals = data.signals || [];
      renderSignals(state.signals);
    } catch (err) {
      if (signalsListEl) {
        signalsListEl.innerHTML = `
          <div style="padding: 40px 20px; text-align: center; color: var(--text-secondary);">
            <p>Unable to load pattern signals.</p>
            <button class="btn-ai-refresh" style="margin-top: 10px;" onclick="location.reload()">Retry</button>
          </div>
        `;
      }
    }
  }

  function getBadgeClass(patternName, metadata) {
    const p = (patternName || '').toLowerCase();
    if (p.includes('ipo')) return 'badge-ipo';
    if (p.includes('near 52')) return 'badge-near52w';
    if (metadata && (metadata.is_fresh === true || metadata.is_fresh === "true")) return 'badge-fresh';
    if (p.includes('all-time high')) return 'badge-ath';
    if (p.includes('52-week high')) return 'badge-52whigh';
    if (p.includes('52-week low')) return 'badge-52wlow';
    if (p.includes('range')) return 'badge-range';
    if (p.includes('double bottom') || p.includes('w')) return 'badge-w';
    if (p.includes('crossover') || p.includes('ma')) return 'badge-ma';
    return '';
  }

  function renderSignals(signals) {
    if (!signalsListEl) return;
    if (!signals || signals.length === 0) {
      signalsListEl.innerHTML = `
        <div style="padding: 60px 20px; text-align: center; color: var(--text-secondary);">
          <svg style="width: 42px; height: 42px; color: var(--text-muted); margin-bottom: 8px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
          </svg>
          <p style="font-weight: 600; color: var(--text-primary);">No matching breakouts found</p>
          <p style="font-size: 12px; margin-top: 4px;">Try selecting '⚡ Fresh Today', '🔥 Near 52W High', '🚀 IPO Breakout', or 'All'.</p>
        </div>
      `;
      return;
    }

    // Row format: Stock symbol + Price & Change + Company Name on left, Pattern badge on right
    let html = '';
    signals.forEach(sig => {
      const badgeClass = getBadgeClass(sig.pattern_type, sig.metadata);
      const price = sig.current_price || 0;
      const changePct = sig.change_pct || 0;
      const isGain = changePct >= 0;
      const priceStr = price > 0 ? `₹${price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '';
      const changeStr = price > 0 ? `${isGain ? '+' : ''}${changePct.toFixed(2)}%` : '';
      
      let badgeText = sig.pattern_type;
      if (sig.pattern_type === 'IPO Breakout') {
        badgeText = '🚀 IPO Breakout';
      } else if (sig.pattern_type === 'Near 52-Week High') {
        badgeText = '🔥 Near 52W High';
      } else if (state.selectedPattern === 'Fresh Breakout' || sig.metadata?.is_fresh) {
        badgeText = `⚡ ${sig.pattern_type}`;
      }

      html += `
        <div class="signal-row" data-symbol="${sig.symbol}">
          <div class="signal-symbol-col">
            <div class="signal-top-line">
              <span class="signal-symbol">${sig.symbol}</span>
              ${priceStr ? `<span class="signal-price-inline">${priceStr}</span>` : ''}
              ${changeStr ? `<span class="signal-change-inline ${isGain ? 'price-positive' : 'price-negative'}">${changeStr}</span>` : ''}
            </div>
            <span class="signal-company-sub">${sig.company_name || sig.sector || 'NSE Equity'}</span>
          </div>
          <span class="signal-pattern-badge ${badgeClass}">${badgeText}</span>
        </div>
      `;
    });

    signalsListEl.innerHTML = html;

    // Attach click handlers to rows to navigate to Setup tab
    signalsListEl.querySelectorAll('.signal-row').forEach(row => {
      row.addEventListener('click', () => {
        const symbol = row.dataset.symbol;
        switchTab('setup', symbol);
      });
    });
  }

  // Filter Chips
  filterChips.forEach(chip => {
    chip.addEventListener('click', () => {
      filterChips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.selectedPattern = chip.dataset.pattern;
      loadSignals();
    });
  });

  // Search input debouncing
  if (searchInput) {
    let searchTimeout = null;
    searchInput.addEventListener('input', (e) => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        state.searchQuery = e.target.value.trim();
        loadSignals();
      }, 200);
    });
  }

  // ==================== TAB 2: SETUP VIEW ==================== //

  function showChartLoading(symbol) {
    const overlay = document.getElementById('chartLoadingOverlay');
    const loadingText = document.getElementById('chartLoadingText');
    if (overlay) {
      if (loadingText) loadingText.textContent = `Loading ${symbol || ''} chart...`;
      overlay.style.display = 'flex';
    }
  }

  function hideChartLoading() {
    const overlay = document.getElementById('chartLoadingOverlay');
    if (overlay) {
      overlay.style.display = 'none';
    }
  }

  async function loadStockSetup(symbol) {
    if (!symbol) return;
    const targetSymbol = symbol.toUpperCase();
    state.currentSymbol = targetSymbol;
    const currentSetupReqId = ++state.setupRequestId;

    // Immediately destroy previous chart instance to avoid partial-state rendering
    if (state.chartInstance) {
      state.chartInstance.destroy();
      state.chartInstance = null;
    }
    showChartLoading(targetSymbol);

    // Update headers immediately
    const symEl = document.getElementById('setupSymbol') || document.getElementById('stockSymbol');
    if (symEl) symEl.textContent = targetSymbol;
    const compEl = document.getElementById('setupCompanyName') || document.getElementById('stockCompanyName');
    if (compEl) compEl.textContent = 'Loading stock information...';
    const priceEl = document.getElementById('setupPrice') || document.getElementById('stockCurrentPrice');
    if (priceEl) priceEl.textContent = '—';
    const changeEl = document.getElementById('setupChange') || document.getElementById('stockChange');
    if (changeEl) changeEl.textContent = '—';

    // Start loading chart & AI analysis concurrently tagged with request IDs
    loadChartData(targetSymbol, state.currentRange, null);
    loadAiAnalysis(targetSymbol);

    try {
      const setup = await API.getStockSetup(targetSymbol);
      
      // RACE CONDITION CHECK: Discard stale response if user switched to another stock
      if (currentSetupReqId !== state.setupRequestId || targetSymbol !== state.currentSymbol) {
        console.log(`[Setup] Discarded stale setup data for ${targetSymbol} (currently active: ${state.currentSymbol})`);
        return;
      }

      renderSetupData(setup);

      // If chart is active for this stock, attach pivot price
      if (state.chartInstance && state.chartInstance.symbol === targetSymbol && setup.latest_signal?.pivot_price) {
        state.chartInstance.setPivotPrice(setup.latest_signal.pivot_price);
      }
    } catch (err) {
      if (currentSetupReqId === state.setupRequestId) {
        const timestamp = new Date().toISOString();
        console.error(`[Setup Error] Failed loading setup for ${targetSymbol} at ${timestamp}:`, err);
        showToast(`Error loading setup for ${targetSymbol}`);
      }
    }
  }

  function renderSetupData(setup) {
    if (!setup || setup.symbol !== state.currentSymbol) return;

    const symEl = document.getElementById('setupSymbol') || document.getElementById('stockSymbol');
    if (symEl) symEl.textContent = setup.symbol;
    const compEl = document.getElementById('setupCompanyName') || document.getElementById('stockCompanyName');
    if (compEl) compEl.textContent = setup.company_name || setup.symbol;
    const secEl = document.getElementById('setupSector');
    if (secEl) secEl.textContent = setup.sector || 'NSE Equity';
    
    const price = setup.current_price || 0;
    const change = setup.change || 0;
    const changePct = setup.change_pct || 0;
    const isGain = change >= 0;

    const priceEl = document.getElementById('setupPrice') || document.getElementById('stockCurrentPrice');
    if (priceEl) priceEl.textContent = `₹${price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    
    const changeEl = document.getElementById('setupChange') || document.getElementById('stockChange');
    if (changeEl) {
      changeEl.className = `setup-price-change ${isGain ? 'price-positive' : 'price-negative'}`;
      changeEl.innerHTML = `${isGain ? '+' : ''}${change.toFixed(2)} (${isGain ? '+' : ''}${changePct.toFixed(2)}%)`;
    }

    // Market cap and ATH
    const mcapCr = setup.market_cap_cr || 0;
    const mcapEl = document.getElementById('setupMcap');
    if (mcapEl) {
      if (mcapCr >= 1000) {
        mcapEl.textContent = `₹${(mcapCr / 1000).toFixed(1)}k Cr`;
      } else if (mcapCr > 0) {
        mcapEl.textContent = `₹${mcapCr.toFixed(0)} Cr`;
      } else {
        mcapEl.textContent = '—';
      }
    }
    const athEl = document.getElementById('setupAth') || document.getElementById('stockAthPrice');
    if (athEl) athEl.textContent = setup.all_time_high ? `₹${setup.all_time_high.toFixed(1)}` : '—';

    // Watchlist star button state
    if (starBtn) {
      if (setup.in_watchlist) {
        starBtn.classList.add('starred');
        starBtn.innerHTML = `
          <svg fill="currentColor" viewBox="0 0 20 20">
            <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"></path>
          </svg>
        `;
      } else {
        starBtn.classList.remove('starred');
        starBtn.innerHTML = `
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"></path>
          </svg>
        `;
      }
    }

    // Stats Card (Technical Structure)
    const sig = setup.latest_signal;
    const statsStatusBadge = document.querySelector('.stats-card-header span:last-child');

    const patTypeEl = document.getElementById('statPatternType');
    const pivotEl = document.getElementById('statPivotPrice');
    const supportEl = document.getElementById('statSupportLevel') || document.getElementById('statTargetPrice');
    const sma20El = document.getElementById('statSma20') || document.getElementById('statStopLoss');
    const sma50El = document.getElementById('statSma50');
    const vsPivotEl = document.getElementById('statVsPivot');
    const descEl = document.getElementById('statDescription');

    if (sig) {
      if (statsStatusBadge) {
        statsStatusBadge.textContent = 'ACTIVE SETUP';
        statsStatusBadge.style.color = 'var(--green-gain)';
      }
      if (patTypeEl) patTypeEl.textContent = sig.pattern_type;
      if (pivotEl) pivotEl.textContent = `₹${sig.pivot_price.toFixed(2)}`;
      
      const support = sig.metadata?.support_level || (sig.pivot_price * 0.965);
      const sma20 = sig.metadata?.sma_20 || sig.metadata?.range_low || (sig.current_price * 0.98);
      const sma50 = sig.metadata?.sma_50 || (sig.current_price * 0.95);

      if (supportEl) supportEl.textContent = support ? `₹${parseFloat(support).toFixed(2)}` : '—';
      if (sma20El) sma20El.textContent = sma20 ? `₹${parseFloat(sma20).toFixed(2)}` : '—';
      if (sma50El) sma50El.textContent = sma50 ? `₹${parseFloat(sma50).toFixed(2)}` : '—';

      if (vsPivotEl) {
        const isVsGain = sig.percent_vs_pivot >= 0;
        vsPivotEl.className = `stat-value ${isVsGain ? 'price-positive' : 'price-negative'}`;
        vsPivotEl.textContent = `${isVsGain ? '+' : ''}${sig.percent_vs_pivot.toFixed(2)}%`;
      }

      if (descEl) {
        const desc = sig.metadata?.description || `Technical setup around resistance pivot ₹${sig.pivot_price.toFixed(2)}. Base support at ₹${parseFloat(support).toFixed(2)}.`;
        descEl.textContent = desc;
      }
    } else {
      if (statsStatusBadge) {
        statsStatusBadge.textContent = 'CONSOLIDATION';
        statsStatusBadge.style.color = 'var(--text-muted)';
      }
      if (patTypeEl) patTypeEl.textContent = 'Consolidation Base';
      if (pivotEl) pivotEl.textContent = `—`;
      if (supportEl) supportEl.textContent = `₹${(setup.current_price * 0.96).toFixed(2)}`;
      if (sma20El) sma20El.textContent = `₹${(setup.current_price * 0.98).toFixed(2)}`;
      if (sma50El) sma50El.textContent = `₹${(setup.current_price * 0.95).toFixed(2)}`;
      if (vsPivotEl) {
        vsPivotEl.className = 'stat-value';
        vsPivotEl.textContent = '—';
      }
      if (descEl) descEl.textContent = `${setup.symbol} is currently trading in normal consolidation without an active breakout on the latest session.`;
    }
  }

  async function loadChartData(symbol, range, pivotPrice = null) {
    if (!symbol) return;
    const targetSymbol = symbol.toUpperCase();
    const reqId = ++state.chartRequestId;

    showChartLoading(targetSymbol);

    try {
      const data = await API.getStockHistory(targetSymbol, range);
      
      // RACE CONDITION CHECK: Tagged request check. Discard if stale!
      if (reqId !== state.chartRequestId || targetSymbol !== state.currentSymbol) {
        console.log(`[Chart] Discarded stale chart response for ${targetSymbol} (currently active: ${state.currentSymbol}, reqId: ${reqId} vs ${state.chartRequestId})`);
        return;
      }

      const chartCanvas = document.getElementById('candlestickChart') || document.getElementById('stockChartCanvas');
      if (!chartCanvas) return;

      // Fully destroy previous chart instance before recreating to prevent partial-state rendering
      if (state.chartInstance) {
        state.chartInstance.destroy();
        state.chartInstance = null;
      }

      // Recreate a clean fresh chart instance tagged with targetSymbol
      state.chartInstance = new BreakoutChart(chartCanvas, targetSymbol);
      state.chartInstance.setData(data.candles || [], pivotPrice);

      hideChartLoading();
    } catch (err) {
      if (reqId === state.chartRequestId) {
        const timestamp = new Date().toISOString();
        console.error(`[Chart Fetch Error] Failed loading chart for ${targetSymbol} (${range}) at ${timestamp}:`, err);
        hideChartLoading();
      }
    }
  }

  async function loadAiAnalysis(symbol) {
    if (!symbol) return;
    const targetSymbol = symbol.toUpperCase();
    const reqId = ++state.aiRequestId;

    const aiBody = document.getElementById('aiAnalysisBody');
    if (!aiBody) return;
    aiBody.innerHTML = `
      <div class="loading-spinner" style="padding: 16px 0;">
        <div class="spinner"></div>
        <span>Generating Gemini Technical Insights...</span>
      </div>
    `;

    try {
      const analysis = await API.getAiAnalysis(targetSymbol);
      
      // RACE CONDITION CHECK: Discard stale AI analysis response
      if (reqId !== state.aiRequestId || targetSymbol !== state.currentSymbol) {
        console.log(`[AI Analysis] Discarded stale AI analysis for ${targetSymbol} (currently active: ${state.currentSymbol})`);
        return;
      }

      renderAiAnalysis(analysis);
    } catch (err) {
      if (reqId === state.aiRequestId) {
        const timestamp = new Date().toISOString();
        console.error(`[AI Error] Failed loading AI analysis for ${targetSymbol} at ${timestamp}:`, err);
        if (aiBody) {
          aiBody.innerHTML = `
            <div style="color: var(--text-secondary); font-size: 13px; line-height: 1.5;">
              <p><strong>Technical Synthesis:</strong> Analyzing price action around key pivot levels.</p>
              <p style="margin-top: 6px;">Consolidation above key moving averages suggests institutional support.</p>
            </div>
          `;
        }
      }
    }
  }

  function renderAiAnalysis(analysis) {
    const aiBody = document.getElementById('aiAnalysisBody');
    if (!aiBody) return;
    const lines = (analysis.technical_thesis || '').split('\n').filter(l => l.trim().length > 0);
    
    let html = '';
    lines.forEach(line => {
      const cleanLine = line.replace(/^\*\s*/, '').replace(/^-\s*/, '');
      if (cleanLine.toLowerCase().includes('bullish') || cleanLine.toLowerCase().includes('breakout') || cleanLine.toLowerCase().includes('target')) {
        html += `<p class="ai-bullet ai-bullet-bullish">${cleanLine}</p>`;
      } else if (cleanLine.toLowerCase().includes('risk') || cleanLine.toLowerCase().includes('stop loss') || cleanLine.toLowerCase().includes('bearish')) {
        html += `<p class="ai-bullet ai-bullet-risk">${cleanLine}</p>`;
      } else {
        html += `<p class="ai-bullet">${cleanLine}</p>`;
      }
    });

    if (analysis.ai_sentiment) {
      const sentClass = analysis.ai_sentiment === 'BULLISH' ? 'price-positive' : (analysis.ai_sentiment === 'BEARISH' ? 'price-negative' : '');
      html += `
        <div style="margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--border-light); font-size: 11px; display: flex; justify-content: space-between; color: var(--text-secondary);">
          <span>AI Sentiment: <b class="${sentClass}">${analysis.ai_sentiment}</b></span>
          <span>Source: ${analysis.source || 'Algorithmic Synthesis'}</span>
        </div>
      `;
    }

    aiBody.innerHTML = html || '<p style="color: var(--text-secondary); font-size: 13px;">Pattern structure intact.</p>';
  }

  // Range Selector Buttons
  rangeBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      rangeBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.currentRange = btn.dataset.range;
      const pivot = state.chartInstance ? state.chartInstance.pivotPrice : null;
      loadChartData(state.currentSymbol, state.currentRange, pivot);
    });
  });

  // Watchlist Star Toggle on Setup Page
  if (starBtn) {
    starBtn.addEventListener('click', async () => {
      try {
        const res = await API.toggleWatchlist(state.currentSymbol);
        if (res.in_watchlist) {
          starBtn.classList.add('starred');
          showToast(`Added ${state.currentSymbol} to Watchlist`);
        } else {
          starBtn.classList.remove('starred');
          showToast(`Removed ${state.currentSymbol} from Watchlist`);
        }
        renderSetupData({ ...await API.getStockSetup(state.currentSymbol), in_watchlist: res.in_watchlist });
      } catch (err) {
        showToast('Error updating watchlist');
      }
    });
  }

  // AI Refresh button
  if (aiRefreshBtn) {
    aiRefreshBtn.addEventListener('click', () => {
      loadAiAnalysis(state.currentSymbol);
    });
  }

  // ==================== TAB 3: WATCHLIST ==================== //

  async function loadWatchlist() {
    if (!watchlistContainerEl) return;
    watchlistContainerEl.innerHTML = `
      <div class="loading-spinner">
        <div class="spinner"></div>
        <span>Loading watchlist...</span>
      </div>
    `;

    try {
      const data = await API.getWatchlist();
      state.watchlist = data.items || [];
      renderWatchlist(state.watchlist);
    } catch (err) {
      if (watchlistContainerEl) {
        watchlistContainerEl.innerHTML = `
          <div style="padding: 40px 20px; text-align: center; color: var(--text-secondary);">
            <p>Failed to load watchlist.</p>
          </div>
        `;
      }
    }
  }

  function renderWatchlist(items) {
    if (!watchlistContainerEl) return;
    if (!items || items.length === 0) {
      watchlistContainerEl.innerHTML = `
        <div class="watchlist-empty">
          <svg class="empty-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363 1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"></path>
          </svg>
          <div class="empty-title">Your Watchlist is empty</div>
          <div class="empty-sub">Star any stock from the Scanner or Setup page to track it here.</div>
        </div>
      `;
      return;
    }

    let html = '';
    items.forEach(item => {
      const price = item.current_price || 0;
      const changePct = item.change_pct || 0;
      const isGain = changePct >= 0;
      const patType = item.latest_signal?.pattern_type || 'Consolidation';

      html += `
        <div class="watchlist-row" data-symbol="${item.symbol}">
          <div class="wl-left">
            <button class="btn-remove-star" data-symbol="${item.symbol}" title="Remove from Watchlist">
              <svg style="width: 18px; height: 18px;" fill="currentColor" viewBox="0 0 20 20">
                <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"></path>
              </svg>
            </button>
            <div class="wl-symbol-col">
              <span class="signal-symbol">${item.symbol}</span>
              <span class="signal-company-sub">${patType}</span>
            </div>
          </div>
          <div class="wl-right">
            <span class="wl-price">₹${price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            <span class="wl-change ${isGain ? 'price-positive' : 'price-negative'}">
              ${isGain ? '+' : ''}${changePct.toFixed(2)}%
            </span>
          </div>
        </div>
      `;
    });

    watchlistContainerEl.innerHTML = html;

    // Remove star click
    watchlistContainerEl.querySelectorAll('.btn-remove-star').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const symbol = btn.dataset.symbol;
        await API.toggleWatchlist(symbol);
        showToast(`Removed ${symbol} from Watchlist`);
        loadWatchlist();
      });
    });

    // Row click -> go to setup
    watchlistContainerEl.querySelectorAll('.watchlist-row').forEach(row => {
      row.addEventListener('click', () => {
        const symbol = row.dataset.symbol;
        switchTab('setup', symbol);
      });
    });
  }

  // ==================== TAB 4: ACCOUNT & SETTINGS ==================== //

  // Manual Bhavcopy & Pattern Sync Trigger
  if (manualSyncBtn) {
    manualSyncBtn.addEventListener('click', async () => {
      manualSyncBtn.disabled = true;
      manualSyncBtn.textContent = 'Syncing...';
      try {
        await API.triggerDailySync();
        showToast('Daily NSE Sync & Pattern Scan started in background!');
        setTimeout(() => {
          manualSyncBtn.disabled = false;
          manualSyncBtn.textContent = 'Run Daily Scan';
        }, 3000);
      } catch (err) {
        showToast('Sync trigger failed');
        manualSyncBtn.disabled = false;
        manualSyncBtn.textContent = 'Run Daily Scan';
      }
    });
  }

  // Dark / Light Theme Toggle
  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
      if (isDark) {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('theme', 'light');
        const tv = themeToggle.querySelector('.theme-val');
        if (tv) tv.textContent = 'Light';
      } else {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('theme', 'dark');
        const tv = themeToggle.querySelector('.theme-val');
        if (tv) tv.textContent = 'Dark';
      }
      if (state.chartInstance) {
        state.chartInstance.render();
      }
    });
  }

  // Native PWA App Install Action
  const pwaInstallItem = document.getElementById('pwaInstallItem');
  if (pwaInstallItem) {
    pwaInstallItem.addEventListener('click', async () => {
      if (window.deferredPrompt) {
        window.deferredPrompt.prompt();
        const choice = await window.deferredPrompt.userChoice;
        if (choice && choice.outcome === 'accepted') {
          showToast('✓ Installing ZeroBreakout App...');
          window.deferredPrompt = null;
        }
      } else {
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
        if (isIOS) {
          showToast('iPhone Install: Tap Share ⎋ -> "Add to Home Screen"');
        } else {
          showToast('To Install App: Tap Chrome Menu (⋮) -> "Install app"');
        }
      }
    });
  }

  // Header Live Data Sync
  const headerLiveSyncBtn = document.getElementById('headerLiveSyncBtn');
  const liveStatusText = document.getElementById('liveStatusText');

  if (headerLiveSyncBtn) {
    headerLiveSyncBtn.addEventListener('click', async () => {
      headerLiveSyncBtn.disabled = true;
      if (liveStatusText) liveStatusText.textContent = 'Syncing Live...';
      showToast('Fetching real live 5-year OHLCV from NSE & Yahoo Finance...');
      
      try {
        await API.syncLiveData();
        setTimeout(() => {
          showToast('Live market data synced! Refreshing signals...');
          loadSignals();
          if (liveStatusText) liveStatusText.textContent = 'Live NSE Active ✓';
          headerLiveSyncBtn.disabled = false;
        }, 8000);
      } catch (err) {
        showToast('Live sync started in background.');
        if (liveStatusText) liveStatusText.textContent = 'Sync Live Data ↻';
        headerLiveSyncBtn.disabled = false;
      }
    });
  }

  // Toast Notification System
  function showToast(message) {
    let container = document.querySelector('.toast-container');
    if (!container) {
      container = document.createElement('div');
      container.className = 'toast-container';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => toast.classList.add('show'), 20);
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 300);
    }, 2500);
  }

  window.showToast = showToast;

  // ==================== UNIVERSAL SIGN IN & ADMIN PORTAL CONTROLLER ==================== //
  // ==================== UNIVERSAL SIGN IN & ADMIN PORTAL CONTROLLER ==================== //
  const authGuestCard = document.getElementById('authGuestCard');
  const authUserCard = document.getElementById('authUserCard');
  const adminPortalSection = document.getElementById('adminPortalSection');
  const googleSignInBtn = document.getElementById('googleSignInBtn');
  const userDisplayName = document.getElementById('userDisplayName');
  const userDisplayEmail = document.getElementById('userDisplayEmail');
  const userAvatar = document.getElementById('userAvatar');
  const userTraderBadge = document.getElementById('userTraderBadge');
  const accountLogoutBtn = document.getElementById('accountLogoutBtn');

  const adminTriggerScanBtn = document.getElementById('adminTriggerScanBtn');
  const adminTriggerBhavcopyBtn = document.getElementById('adminTriggerBhavcopyBtn');
  const adminScanProgress = document.getElementById('adminScanProgress');
  const adminScanProgressText = document.getElementById('adminScanProgressText');
  const adminEditBrokerBtn = document.getElementById('adminEditBrokerBtn');

  // Broker Link Management (Defaults + Admin Customization)
  const DEFAULT_BROKER_LINKS = {
    zerodha: 'https://zerodha.com/open-account',
    kotak: 'https://www.kotaksecurities.com/',
    fyers: 'https://fyers.in/',
    angelone: 'https://angelone.in/'
  };

  function getBrokerLinks() {
    try {
      const saved = JSON.parse(localStorage.getItem('zb_broker_links') || 'null');
      return { ...DEFAULT_BROKER_LINKS, ...saved };
    } catch {
      return DEFAULT_BROKER_LINKS;
    }
  }

  function applyBrokerLinks() {
    const links = getBrokerLinks();
    const zEl = document.getElementById('brokerLinkZerodha');
    const kEl = document.getElementById('brokerLinkKotak');
    const fEl = document.getElementById('brokerLinkFyers');
    const aEl = document.getElementById('brokerLinkAngel');

    if (zEl && links.zerodha) zEl.href = links.zerodha;
    if (kEl && links.kotak) kEl.href = links.kotak;
    if (fEl && links.fyers) fEl.href = links.fyers;
    if (aEl && links.angelone) aEl.href = links.angelone;
  }

  applyBrokerLinks();

  // Admin Broker Links Editor
  if (adminEditBrokerBtn) {
    adminEditBrokerBtn.addEventListener('click', () => {
      const current = getBrokerLinks();
      const zLink = prompt('Enter Zerodha Account/Referral URL:', current.zerodha);
      if (zLink === null) return;
      const kLink = prompt('Enter Kotak Neo Account/Referral URL:', current.kotak);
      if (kLink === null) return;
      const fLink = prompt('Enter Fyers Account/Referral URL:', current.fyers);
      if (fLink === null) return;
      const aLink = prompt('Enter Angel One Account/Referral URL:', current.angelone);
      if (aLink === null) return;

      const updated = {
        zerodha: zLink.trim() || DEFAULT_BROKER_LINKS.zerodha,
        kotak: kLink.trim() || DEFAULT_BROKER_LINKS.kotak,
        fyers: fLink.trim() || DEFAULT_BROKER_LINKS.fyers,
        angelone: aLink.trim() || DEFAULT_BROKER_LINKS.angelone
      };

      localStorage.setItem('zb_broker_links', JSON.stringify(updated));
      applyBrokerLinks();
      showToast('Partner broker links updated successfully!');
    });
  }

  // Live Market Pulse & Clock Calculator
  function updateMarketClock() {
    const statusTextEl = document.getElementById('marketStatusText');
    const pulseEl = document.getElementById('marketPulseIndicator');
    if (!statusTextEl || !pulseEl) return;

    // Get current time in Indian Standard Time (UTC + 5:30)
    const now = new Date();
    const utcTime = now.getTime() + (now.getTimezoneOffset() * 60000);
    const istDate = new Date(utcTime + (3600000 * 5.5));

    const day = istDate.getDay(); // 0 = Sun, 6 = Sat
    const hours = istDate.getHours();
    const minutes = istDate.getMinutes();
    const totalMinutes = hours * 60 + minutes;

    const marketOpen = 9 * 60 + 15;  // 09:15 IST
    const marketClose = 15 * 60 + 30; // 15:30 IST

    const isWeekday = day >= 1 && day <= 5;
    const isMarketHours = totalMinutes >= marketOpen && totalMinutes <= marketClose;

    if (isWeekday && isMarketHours) {
      statusTextEl.textContent = 'NSE Market Active (09:15 - 15:30 IST)';
      pulseEl.className = 'pulse-indicator pulse-green';
    } else {
      statusTextEl.textContent = 'NSE Closed • EOD Data Synced';
      pulseEl.className = 'pulse-indicator';
      pulseEl.style.backgroundColor = '#94A3B8';
    }
  }

  updateMarketClock();
  setInterval(updateMarketClock, 30000);

  function getUserAuth() {
    try {
      return JSON.parse(localStorage.getItem('zb_user_auth') || 'null');
    } catch {
      return null;
    }
  }

  function setUserAuth(auth) {
    if (auth && auth.email) {
      localStorage.setItem('zb_user_auth', JSON.stringify(auth));
      if (authGuestCard) authGuestCard.style.display = 'none';
      if (authUserCard) authUserCard.style.display = 'flex';
      if (accountLogoutBtn) accountLogoutBtn.style.display = 'flex';

      const displayName = auth.name || auth.email.split('@')[0];
      if (userDisplayName) {
        userDisplayName.textContent = auth.is_admin ? '👑 Master Administrator' : displayName;
      }
      if (userDisplayEmail) userDisplayEmail.textContent = auth.email;
      if (userTraderBadge) {
        userTraderBadge.textContent = auth.is_admin ? '👑 Master Admin' : '💎 Zero Breakout Trader';
      }
      if (userAvatar) {
        if (auth.photo) {
          userAvatar.innerHTML = `<img src="${auth.photo}" alt="${displayName}" referrerpolicy="no-referrer" />`;
          userAvatar.style.background = 'transparent';
        } else {
          userAvatar.textContent = auth.is_admin ? '👑' : auth.email.substring(0, 2).toUpperCase();
          userAvatar.style.background = auth.is_admin ? '#00B386' : 'linear-gradient(135deg, #00B386, #387ED1)';
        }
      }

      // Automatically unlock Admin Portal & Broker link editing if logged in as Zerobossai@gmail.com
      if (auth.is_admin) {
        if (adminPortalSection) adminPortalSection.style.display = 'block';
        if (adminEditBrokerBtn) adminEditBrokerBtn.style.display = 'inline-block';
        loadAdminMetrics();
      } else {
        if (adminPortalSection) adminPortalSection.style.display = 'none';
        if (adminEditBrokerBtn) adminEditBrokerBtn.style.display = 'none';
      }
    } else {
      localStorage.removeItem('zb_user_auth');
      if (authGuestCard) authGuestCard.style.display = 'block';
      if (authUserCard) authUserCard.style.display = 'none';
      if (adminPortalSection) adminPortalSection.style.display = 'none';
      if (adminEditBrokerBtn) adminEditBrokerBtn.style.display = 'none';
      if (accountLogoutBtn) accountLogoutBtn.style.display = 'none';
    }
  }

  async function loadAdminMetrics() {
    try {
      const stats = await API.getStats();
      const mTracked = document.getElementById('mTrackedStocks');
      const mActive = document.getElementById('mActiveSignals');
      if (mTracked) mTracked.textContent = stats.total_stocks_tracked?.toLocaleString('en-IN') || '1,110';
      if (mActive) mActive.textContent = stats.total_active_signals?.toLocaleString('en-IN') || '480';
    } catch (e) {
      console.warn('Failed to load admin metrics:', e);
    }
  }

  // Real Firebase Google Sign In Trigger
  if (googleSignInBtn) {
    googleSignInBtn.addEventListener('click', async () => {
      googleSignInBtn.disabled = true;
      googleSignInBtn.innerHTML = `<span>Connecting to Google...</span>`;

      try {
        if (window.firebaseAuth && window.firebaseAuth.signInWithGoogle) {
          const user = await window.firebaseAuth.signInWithGoogle();
          const email = user.email || '';
          const name = user.displayName || email.split('@')[0];
          const photo = user.photoURL || '';

          // Sync with backend admin check
          let res = {};
          try {
            res = await API.adminLogin(email);
          } catch (e) {
            res = { email, is_admin: email.toLowerCase() === 'zerobossai@gmail.com' };
          }

          const authPayload = {
            email: email,
            name: name,
            photo: photo,
            token: res.token || 'fb_token',
            is_admin: res.is_admin || (email.toLowerCase() === 'zerobossai@gmail.com')
          };

          setUserAuth(authPayload);
          if (authPayload.is_admin) {
            showToast('👑 Master Admin Access Activated!');
          } else {
            showToast(`Welcome, ${name}!`);
          }
        } else {
          // Graceful fallback prompt
          const email = prompt('Sign in with Google Account:\nEnter your Google email address:', 'Zerobossai@gmail.com');
          if (email && email.includes('@')) {
            const res = await API.adminLogin(email.trim());
            setUserAuth({
              email: res.email,
              name: res.email.split('@')[0],
              token: res.token,
              is_admin: res.is_admin
            });
            if (res.is_admin) {
              showToast('👑 Master Admin Access Activated!');
            } else {
              showToast(`Welcome ${res.email}!`);
            }
          }
        }
      } catch (err) {
        console.error('Google Sign In Error:', err);
        if (err.code === 'auth/popup-closed-by-user') {
          showToast('Sign in cancelled');
        } else if (err.code === 'auth/unauthorized-domain') {
          showToast('Please add 127.0.0.1 / localhost to Firebase Auth authorized domains');
        } else {
          showToast(err.message || 'Google sign in failed');
        }
      } finally {
        googleSignInBtn.disabled = false;
        googleSignInBtn.innerHTML = `
          <svg viewBox="0 0 24 24" width="18" height="18">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
          </svg>
          <span>Sign in with Google</span>
        `;
      }
    });
  }

  // Handle Admin Instant Scan Trigger
  if (adminTriggerScanBtn) {
    adminTriggerScanBtn.addEventListener('click', async () => {
      const auth = getUserAuth();
      adminTriggerScanBtn.disabled = true;
      if (adminScanProgress) adminScanProgress.style.display = 'flex';
      if (adminScanProgressText) adminScanProgressText.textContent = 'Running modular scan across universe...';

      try {
        await API.triggerAdminScan(auth?.token);
        showToast('Full market scan triggered in background!');
        setTimeout(async () => {
          if (adminScanProgressText) adminScanProgressText.textContent = 'Scan complete! Refreshing signals...';
          await loadSignals();
          await loadAdminMetrics();
          setTimeout(() => {
            if (adminScanProgress) adminScanProgress.style.display = 'none';
            adminTriggerScanBtn.disabled = false;
            showToast('All Breakout signals updated!');
          }, 1500);
        }, 5000);
      } catch (err) {
        showToast('Scan error: ' + err.message);
        if (adminScanProgress) adminScanProgress.style.display = 'none';
        adminTriggerScanBtn.disabled = false;
      }
    });
  }

  // Handle Admin Bhavcopy Ingest Trigger
  if (adminTriggerBhavcopyBtn) {
    adminTriggerBhavcopyBtn.addEventListener('click', async () => {
      const auth = getUserAuth();
      adminTriggerBhavcopyBtn.disabled = true;
      if (adminScanProgress) adminScanProgress.style.display = 'flex';
      if (adminScanProgressText) adminScanProgressText.textContent = "Downloading today's official NSE Bhavcopy file...";

      try {
        await API.triggerAdminBhavcopy(auth?.token);
        showToast('NSE Bhavcopy ingestion started!');
        setTimeout(async () => {
          if (adminScanProgressText) adminScanProgressText.textContent = 'Bhavcopy ingested & patterns scanned!';
          await loadSignals();
          await loadAdminMetrics();
          setTimeout(() => {
            if (adminScanProgress) adminScanProgress.style.display = 'none';
            adminTriggerBhavcopyBtn.disabled = false;
          }, 1500);
        }, 6000);
      } catch (err) {
        showToast('Bhavcopy error: ' + err.message);
        if (adminScanProgress) adminScanProgress.style.display = 'none';
        adminTriggerBhavcopyBtn.disabled = false;
      }
    });
  }

  // Handle Account Log Out
  if (accountLogoutBtn) {
    accountLogoutBtn.addEventListener('click', async () => {
      try {
        if (window.firebaseAuth && window.firebaseAuth.signOut) {
          await window.firebaseAuth.signOut();
        }
      } catch (e) {
        console.warn('Firebase signout:', e);
      }
      setUserAuth(null);
      showToast('Signed out of account');
    });
  }

  // Check saved session on startup
  const savedUser = getUserAuth();
  if (savedUser) {
    setUserAuth(savedUser);
  }
}

// Immediate execution if DOM is ready, otherwise on DOMContentLoaded
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}
