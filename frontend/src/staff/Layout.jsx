import { NavLink, Navigate, Outlet, useLocation } from 'react-router-dom';
import { ROLE_LABELS, useAuth } from '../auth.jsx';
import './staff.css';

const ICONS = {
  dashboard: 'M3 12l9-8 9 8M5 10v10h5v-6h4v6h5V10',
  leads: 'M4 6h16M4 12h10M4 18h7',
  surveys: 'M3 11l9-7 9 7M6 10v9h12v-9',
  orders: 'M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h5',
  deliveries: 'M3 7h11v9H3zM14 10h4l3 3v3h-7M7 19a2 2 0 100-4 2 2 0 000 4zM17 19a2 2 0 100-4 2 2 0 000 4z',
  stock: 'M4 7l8-4 8 4v10l-8 4-8-4zM4 7l8 4 8-4M12 11v10',
  jobs: 'M14.7 6.3a4 4 0 00-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 005.4-5.4l-2.5 2.5-2.5-2.5z',
  tickets: 'M12 8v4l3 2M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
  warranties: 'M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z',
  customers: 'M16 11a4 4 0 10-8 0 4 4 0 008 0zM4 21a8 8 0 0116 0',
  subsidies: 'M4 10h16M6 10v8M10 10v8M14 10v8M18 10v8M3 20h18M12 3l9 5H3z',
  reports: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  settings: 'M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z'
};

const STAFF = ['director', 'sales', 'warehouse', 'technician', 'support'];

export default function StaffLayout() {
  const { me } = useAuth();
  const location = useLocation();
  if (me === undefined) return <p className="empty" style={{ padding: '160px 0' }}>Loading…</p>;
  if (!me.authenticated) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  if (!STAFF.includes(me.role)) return <Navigate to={me.home || '/'} replace />;
  return (
    <div className="ws">
      <aside className="ws-side" aria-label="Workspace">
        <div className="ws-who">
          <strong>{me.name}</strong>
          <span className="muted small">{ROLE_LABELS[me.role]}</span>
        </div>
        <nav className="ws-nav">
          {(me.modules || []).map((m) => (
            <NavLink key={m.key} to={m.path} end={m.path === '/app'} className={({ isActive }) => `ws-nav__link${isActive ? ' is-active' : ''}`}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={ICONS[m.key] || ICONS.dashboard} /></svg>
              <span>{m.label}</span>
              {m.level === 'r' && <span className="ws-nav__ro" title="Read only">view</span>}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="ws-main">
        <Outlet />
      </div>
    </div>
  );
}
