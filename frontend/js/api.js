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

  async login(payload) {
    const resp = await fetch(`${this.baseUrl}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || 'Authentication failed');
    }
    return data;
  },

  async adminLogin(email, password, id_token) {
    return this.login({ email, password, id_token });
  },

  async checkAuthStatus(token) {
    const resp = await fetch(`${this.baseUrl}/api/auth/status?token=${encodeURIComponent(token || '')}`);
    if (!resp.ok) return { is_admin: false };
    return await resp.json();
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
  },

  async getPushPublicKey() {
    const resp = await fetch(`${this.baseUrl}/api/push/public-key`);
    if (!resp.ok) throw new Error('Failed to fetch push public key');
    return await resp.json();
  },

  async subscribePush(subscription, userId = null) {
    const resp = await fetch(`${this.baseUrl}/api/push/subscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        endpoint: subscription.endpoint,
        keys: {
          p256dh: btoa(String.fromCharCode.apply(null, new Uint8Array(subscription.getKey('p256dh')))),
          auth: btoa(String.fromCharCode.apply(null, new Uint8Array(subscription.getKey('auth'))))
        },
        userId: userId
      })
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || 'Push subscription failed');
    return data;
  },

  async unsubscribePush(endpoint) {
    const resp = await fetch(`${this.baseUrl}/api/push/unsubscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint })
    });
    return await resp.json();
  },

  async sendTestPush() {
    const resp = await fetch(`${this.baseUrl}/api/push/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: '⚡ ZeroBreakout Alert',
        body: 'Push notifications are successfully active on your device!'
      })
    });
    return await resp.json();
  }
};

window.API = API;

