// Talks to the SunPower back end (FastAPI, /api and /print) and the AI service
// (/ai) through the dev-server proxy, so the browser only ever sees one origin.
// Every state-changing call carries X-SunPower: 1 (the server's CSRF guard).

async function call(method, url, body, isForm = false) {
  let res;
  try {
    res = await fetch(url, {
      method,
      credentials: 'same-origin',
      headers: isForm ? { 'X-SunPower': '1' } : { 'X-SunPower': '1', 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body)
    });
  } catch {
    throw new Error('We can’t reach SunPower right now. Check your connection and try again.');
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = typeof data?.detail === 'string' ? data.detail : null;
    const err = new Error(detail || (res.status >= 500
      ? 'We can’t reach SunPower right now. Please try again in a minute.'
      : `Something went wrong (${res.status}). Please try again.`));
    err.status = res.status;
    throw err;
  }
  return data;
}

const qs = (params = {}) => {
  const s = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v !== undefined && v !== null)).toString();
  return s ? `?${s}` : '';
};

export const get = (url, params) => call('GET', url + qs(params));
export const post = (url, body = {}) => call('POST', url, body);
export const patch = (url, body = {}) => call('PATCH', url, body);
export const put = (url, body = {}) => call('PUT', url, body);
export const upload = (url, form) => call('POST', url, form, true);

/** Calls that return {ok:false,error} turn into thrown errors. */
async function ok(promise) {
  const r = await promise;
  if (r && r.ok === false) {
    const err = new Error(r.error || 'Please try again.');
    err.field = r.field;
    throw err;
  }
  return r;
}

export const api = {
  // public
  submitEnquiry: (values) => post('/api/sunpower/enquiry', values),
  estimate: (values) => post('/api/sunpower/estimate', values),
  // auth
  me: () => get('/api/auth/me'),
  login: (login, password) => ok(post('/api/auth/login', { login, password })),
  logout: () => post('/api/auth/logout'),
  providers: () => get('/api/auth/providers'),
  signup: (values) => post('/api/auth/signup', values),
  requestReset: (email) => post('/api/auth/reset', { email }),
  checkReset: (token) => post('/api/auth/reset/check', { token }),
  confirmReset: (values) => post('/api/auth/reset/confirm', values),
  recover: (values) => post('/api/auth/recover', values),
  setRecoveryCode: (password, code) => post('/api/auth/recovery-code', { password, code }),
  onboarded: () => post('/api/auth/onboarded'),
  today: () => get('/api/staff/today'),
  // My Account (customers)
  myOverview: () => get('/api/my/overview'),
  myQuote: (id) => get(`/api/my/quote/${id}`),
  acceptQuote: (id, name) => post(`/api/my/quote/${id}/accept`, { name }),
  payOrder: (order_id, kind) => post('/api/my/order/pay', { order_id, kind }),
  confirmTestPayment: (payment_id, card) => post('/api/my/payment/test/confirm', { payment_id, card }),
  verifyRazorpay: (values) => post('/api/my/payment/razorpay/verify', values),
  myComplaint: (values) => post('/api/my/complaint', values),
  confirmFix: (ticket_id) => post('/api/my/ticket/confirm', { ticket_id }),
  reopenTicket: (ticket_id, note) => post('/api/my/ticket/reopen', { ticket_id, note }),
  myProfile: (values) => post('/api/my/profile', values),
  myPassword: (old, next, confirm) => post('/api/my/password', { old, new: next, confirm }),
  // staff
  dashboard: (period) => get('/api/staff/dashboard', { period }),
  summary: () => get('/api/staff/summary'),

  /** Reads an electricity bill with the AI service. Resolves to the parsed body or throws. */
  parseBill: (file) => aiUpload('/ai/bill/parse', file),
  parseLead: (text) => ai('/ai/lead/parse', (() => { const f = new FormData(); f.append('text', text); return f; })()),
  diagnose: (values) => ai('/ai/fault/diagnose', JSON.stringify(values), { 'Content-Type': 'application/json' }),
  checkPhoto: (file) => aiUpload('/ai/photo/check', file)
};

async function ai(url, body, headers = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 65000);
  try {
    const res = await fetch(url, { method: 'POST', body, headers, signal: ctrl.signal });
    const data = await res.json().catch(() => ({}));
    if (data.ok !== true) throw new Error(data.error?.message || 'The AI assistant couldn’t help with this one. Please fill it in by hand.');
    return data;
  } catch (err) {
    throw new Error(err.name === 'AbortError' || /fetch/i.test(err.message)
      ? 'The AI assistant isn’t available right now. Please fill it in by hand.' : err.message);
  } finally {
    clearTimeout(timer);
  }
}

function aiUpload(url, file) {
  const body = new FormData();
  body.append('file', file);
  return ai(url, body);
}

export const inr = (v) => '₹' + new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(v || 0);
export const num = (v) => new Intl.NumberFormat('en-IN', { maximumFractionDigits: 1 }).format(v || 0);
/** Appointment times (survey visits, installation slots) are stored as local time. */
export const fmtLocal = (v, withTime = true) => {
  if (!v) return '';
  const d = new Date(String(v).replace(' ', 'T'));
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toLocaleString('en-IN', withTime
    ? { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }
    : { day: 'numeric', month: 'short', year: 'numeric' });
};
export const fmtDate = (v, withTime = false) => {
  if (!v) return '';
  const s = String(v);
  // Server times are UTC ("YYYY-MM-DD HH:MM:SS"); plain dates are local days.
  const d = s.length > 10 ? new Date(s.replace(' ', 'T') + 'Z') : new Date(s + 'T00:00:00');
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleDateString('en-IN', withTime
    ? { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }
    : { day: 'numeric', month: 'short', year: 'numeric' });
};
