import { Link, NavLink, Navigate, Outlet, useLocation } from 'react-router-dom';
import { ROLE_LABELS, useAuth } from '../auth.jsx';
import './staff.css';

// At most five groups. Each group holds the modules (pages) that belong together;
// people only see the groups and pages their role may open (me.modules, from the server).
export const GROUPS = [
  { key: 'today', label: 'Today', icon: 'M12 3v2M12 19v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M3 12h2M19 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4M12 8a4 4 0 100 8 4 4 0 000-8z', modules: ['dashboard'] },
  { key: 'sales', label: 'Sales', icon: 'M4 6h16M4 12h10M4 18h7', modules: ['leads', 'surveys', 'orders', 'customers', 'subsidies'] },
  { key: 'ops', label: 'Operations', icon: 'M14.7 6.3a4 4 0 00-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 005.4-5.4l-2.5 2.5-2.5-2.5z', modules: ['jobs', 'deliveries', 'stock'] },
  { key: 'service', label: 'Service', icon: 'M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z', modules: ['tickets', 'warranties'] },
  { key: 'business', label: 'Business', icon: 'M4 20V10M10 20V4M16 20v-7M22 20H2', modules: ['insights', 'reports', 'settings'] }
];

const STAFF = ['director', 'sales', 'warehouse', 'technician', 'support'];

/** The groups (with their visible pages) for this person. */
export function useGroups() {
  const { me } = useAuth();
  const mods = me?.modules || [];
  return GROUPS.map((g) => ({ ...g, pages: g.modules.map((k) => mods.find((m) => m.key === k)).filter(Boolean) }))
    .filter((g) => g.pages.length);
}

const inPage = (pathname, path) => (path === '/app' ? pathname === '/app' : pathname === path || pathname.startsWith(path + '/'));

export default function StaffLayout() {
  const { me } = useAuth();
  const location = useLocation();
  const groups = useGroups();
  if (me === undefined) return <p className="empty" style={{ padding: '160px 0' }}>Loading…</p>;
  if (!me.authenticated) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  if (!STAFF.includes(me.role)) return <Navigate to={me.home || '/'} replace />;
  const active = groups.find((g) => g.pages.some((p) => inPage(location.pathname, p.path)));
  return (
    <div className="ws">
      <aside className="ws-side" aria-label="Workspace">
        <div className="ws-who">
          <strong>{me.name}</strong>
          <span className="muted small">{ROLE_LABELS[me.role]}</span>
        </div>
        <nav className="ws-nav">
          {groups.map((g) => {
            const label = g.pages.length === 1 && g.key !== 'today' ? g.pages[0].label : g.label;
            return (
              <Link key={g.key} to={g.pages[0].path} className={`ws-nav__link${active?.key === g.key ? ' is-active' : ''}`} aria-current={active?.key === g.key ? 'page' : undefined}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={g.icon} /></svg>
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>
        <NavLink to="/app/me" className={({ isActive }) => `ws-nav__link ws-nav__me${isActive ? ' is-active' : ''}`}>
          <span className="nav__avatar" aria-hidden="true">{(me.name || '?')[0]}</span><span>My account</span>
        </NavLink>
      </aside>
      <div className="ws-main">
        {active && active.pages.length > 1 && (
          <nav className="ws-tabs" aria-label={active.label}>
            {active.pages.map((p) => (
              <Link key={p.key} to={p.path} className={`ws-tab${inPage(location.pathname, p.path) ? ' is-active' : ''}`}>
                {p.label}{p.level === 'r' && <span className="ws-tab__ro">view</span>}
              </Link>
            ))}
          </nav>
        )}
        <div className="ws-page" key={location.pathname}>
          <Outlet />
        </div>
      </div>
    </div>
  );
}
