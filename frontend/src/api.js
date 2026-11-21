// Talks to the SunPower business engine (Odoo, /api + /web) and the AI service (/ai)
// through the dev-server proxy, so the browser only ever sees one origin.
async function rpc(url, params = {}) {
  const res = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params })
  });
  if (!res.ok) throw new Error(`Server error (${res.status})`);
  const data = await res.json();
  if (data.error) throw new Error(data.error.data?.message || data.error.message || 'Request failed');
  return data.result;
}

export const DB = 'sunpower';

export const api = {
  submitEnquiry: (values) => rpc('/api/sunpower/enquiry', values),
  estimate: (values) => rpc('/api/sunpower/estimate', values),
  login: (login, password) => rpc('/web/session/authenticate', { db: DB, login, password }),
  session: () => rpc('/web/session/get_session_info'),
  logout: () => rpc('/web/session/destroy'),
  me: () => rpc('/api/sunpower/me'),
  providers: () => rpc('/api/sunpower/auth/providers'),
  requestReset: (email) => rpc('/api/sunpower/auth/reset', { email }),
  checkReset: (token) => rpc('/api/sunpower/auth/reset/check', { token }),
  confirmReset: (token, password) => rpc('/api/sunpower/auth/reset/confirm', { token, password }),
  dashboard: (period) =>
    rpc('/web/dataset/call_kw/solar.dashboard/get_data', {
      model: 'solar.dashboard', method: 'get_data', args: [period], kwargs: {}
    }),

  /** Reads an electricity bill with the AI service. Resolves to the parsed body or throws. */
  async parseBill(file) {
    const body = new FormData();
    body.append('file', file);
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 65000);
    try {
      const res = await fetch('/ai/bill/parse', { method: 'POST', body, signal: ctrl.signal });
      const data = await res.json().catch(() => ({}));
      if (data.ok !== true) throw new Error(data.error?.message || 'The bill could not be read');
      return data;
    } finally {
      clearTimeout(timer);
    }
  }
};

export const inr = (v) => '₹' + new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(v || 0);
export const num = (v) => new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(v || 0);
