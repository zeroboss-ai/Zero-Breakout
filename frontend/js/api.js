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
    if (!resp.ok) {
      let errText = 'Failed to fetch push public key';
      try { const d = await resp.json(); errText = d.detail || errText; } catch(e) {}
      throw new Error(errText);
    }
    return await resp.json();
  },

  async subscribePush(subscription, userId = null) {
    const subJson = (typeof subscription.toJSON === 'function') ? subscription.toJSON() : subscription;
    
    // Extract base64 keys safely
    let p256dh = subJson.keys?.p256dh || '';
    let auth = subJson.keys?.auth || '';
    
    if (!p256dh && subscription.getKey) {
      const rawP256 = subscription.getKey('p256dh');
      if (rawP256) p256dh = btoa(String.fromCharCode.apply(null, new Uint8Array(rawP256)));
    }
    if (!auth && subscription.getKey) {
      const rawAuth = subscription.getKey('auth');
      if (rawAuth) auth = btoa(String.fromCharCode.apply(null, new Uint8Array(rawAuth)));
    }

    const payload = {
      endpoint: subscription.endpoint || subJson.endpoint,
      keys: {
        p256dh: p256dh,
        auth: auth
      },
      userId: userId
    };

    const resp = await fetch(`${this.baseUrl}/api/push/subscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    let data;
    try {
      data = await resp.json();
    } catch (e) {
      throw new Error('Server returned invalid response');
    }
    if (!resp.ok) throw new Error(data.detail || data.message || 'Push subscription failed');
    return data;
  },

  async unsubscribePush(endpoint) {
    const resp = await fetch(`${this.baseUrl}/api/push/unsubscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint })
    });
    try { return await resp.json(); } catch(e) { return { status: 'ok' }; }
  },

  async sendTestPush() {
    try {
      const resp = await fetch(`${this.baseUrl}/api/push/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: '⚡ ZeroBreakout Alert',
          body: 'Push notifications are successfully active on your device!'
        })
      });
      let data = {};
      try {
        data = await resp.json();
      } catch (e) {
        data = { status: resp.ok ? 'success' : 'error' };
      }
      return data;
    } catch (err) {
      return { status: 'notice', message: err.message };
    }
  }
};

window.API = API;

