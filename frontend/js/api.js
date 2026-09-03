/**
 * ZeroBreakout API Client
 * Clean REST Client for pattern scanning, price history, watchlist, and Gemini AI.
 */

const API = {
  baseUrl: window.location.origin,

  async getSignals(pattern = 'all', search = '') {
    const params = new URLSearchParams();
    if (pattern && pattern !== 'all') params.append('pattern', pattern);
    if (search && search.trim()) params.append('search', search.trim());
    
    const resp = await fetch(`${this.baseUrl}/api/signals?${params.toString()}`);
    if (!resp.ok) throw new Error('Failed to fetch signals');
    return await resp.json();
  },

  async getStockSetup(symbol) {
    const resp = await fetch(`${this.baseUrl}/api/stocks/${symbol.toUpperCase()}/setup`);
    if (!resp.ok) throw new Error(`Failed to load setup for ${symbol}`);
    return await resp.json();
  },

  async getStockHistory(symbol, range = '1Y') {
    const resp = await fetch(`${this.baseUrl}/api/stocks/${symbol.toUpperCase()}/history?range=${range}`);
    if (!resp.ok) throw new Error(`Failed to load chart data for ${symbol}`);
    return await resp.json();
  },

  async getAiAnalysis(symbol) {
    const resp = await fetch(`${this.baseUrl}/api/stocks/${symbol.toUpperCase()}/ai-analysis`);
    if (!resp.ok) throw new Error('Failed to fetch AI analysis');
    return await resp.json();
  },

  async getWatchlist() {
    const resp = await fetch(`${this.baseUrl}/api/watchlist`);
    if (!resp.ok) throw new Error('Failed to fetch watchlist');
    return await resp.json();
  },

  async toggleWatchlist(symbol) {
    const resp = await fetch(`${this.baseUrl}/api/watchlist/${symbol.toUpperCase()}`, {
      method: 'POST'
    });
    if (!resp.ok) throw new Error('Failed to update watchlist');
    return await resp.json();
  },

  async triggerDailySync() {
    const resp = await fetch(`${this.baseUrl}/api/sync/run`, {
      method: 'POST'
    });
    if (!resp.ok) throw new Error('Failed to trigger daily scan');
    return await resp.json();
  },

  async syncLiveData() {
    const resp = await fetch(`${this.baseUrl}/api/sync/live`, {
      method: 'POST'
    });
    if (!resp.ok) throw new Error('Failed to trigger live data sync');
    return await resp.json();
  },

  async getStats() {
    const resp = await fetch(`${this.baseUrl}/api/stats`);
    if (!resp.ok) throw new Error('Failed to fetch scanner stats');
    return await resp.json();
  },

  async adminLogin(email) {
    const resp = await fetch(`${this.baseUrl}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email })
    });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || 'Login failed');
    }
    return data;
  },

  async triggerAdminScan(token) {
    const resp = await fetch(`${this.baseUrl}/api/admin/scan?token=${encodeURIComponent(token || '')}`, {
      method: 'POST'
    });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || 'Scan trigger failed');
    }
    return data;
  },

  async triggerAdminBhavcopy(token) {
    const resp = await fetch(`${this.baseUrl}/api/admin/bhavcopy?token=${encodeURIComponent(token || '')}`, {
      method: 'POST'
    });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || 'Bhavcopy trigger failed');
    }
    return data;
  }
};

window.API = API;
