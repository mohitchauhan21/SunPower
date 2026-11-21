import { useEffect, useRef, useState } from 'react';
import { api } from '../api.js';
import { useAuth } from '../auth.jsx';

const GIS_SRC = 'https://accounts.google.com/gsi/client';
let gisLoading = null;

/** Loads Google's sign-in library once. */
function loadGis() {
  if (window.google?.accounts?.id) return Promise.resolve();
  gisLoading = gisLoading || new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = GIS_SRC;
    s.async = true;
    s.defer = true;
    s.onload = () => resolve();
    s.onerror = () => { gisLoading = null; reject(new Error('Google sign-in could not load.')); };
    document.head.appendChild(s);
  });
  return gisLoading;
}

/* Google's own "Sign in with Google" button (needs only the public Client ID).
   Google gives us a signed ID token; the server checks it with Google before signing anyone in.
   portal: 'customer' | 'team' (the door chosen on the sign-in page; the role still decides access). */
export default function GoogleButton({ mode = 'signin', portal, onError }) {
  const { refresh } = useAuth();
  const box = useRef(null);
  const portalRef = useRef(portal);
  const [state, setState] = useState('loading'); // loading | ready | off | failed
  const [busy, setBusy] = useState(false);
  portalRef.current = portal;

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const list = await api.providers();
        const google = (list || []).find((p) => p.id === 'google');
        if (!google?.enabled || !google.client_id) { if (alive) setState('off'); return; }
        await loadGis();
        if (!alive || !box.current) return;
        window.google.accounts.id.initialize({
          client_id: google.client_id,
          ux_mode: 'popup',
          callback: async ({ credential }) => {
            setBusy(true);
            try {
              const r = await api.googleToken(credential, portalRef.current);
              if (!r?.ok) throw new Error(r?.error || 'Google sign-in didn’t complete.');
              await refresh();   // the page then moves to the person's own screen
            } catch (err) {
              onError?.(err.message);
            } finally {
              setBusy(false);
            }
          }
        });
        window.google.accounts.id.renderButton(box.current, {
          type: 'standard', theme: 'outline', size: 'large', shape: 'pill', logo_alignment: 'center',
          text: mode === 'signup' ? 'signup_with' : 'continue_with',
          width: Math.min(box.current.offsetWidth || 360, 400)
        });
        setState('ready');
      } catch {
        if (alive) setState('failed');
      }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  if (state === 'off') return null;   // not set up: show only email sign-in
  return (
    <>
      <div className="google-box" aria-busy={state === 'loading' || busy}>
        <div ref={box} className="google-box__btn" />
        {state === 'loading' && <span className="form-hint">Loading Google sign-in…</span>}
        {state === 'failed' && <span className="form-hint">Google sign-in isn’t reachable right now. Please use your email.</span>}
        {busy && <span className="form-hint">Signing you in…</span>}
      </div>
      <div className="auth__or"><span>or</span></div>
    </>
  );
}
