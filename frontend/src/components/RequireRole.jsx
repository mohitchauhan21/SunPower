import { Link, Navigate, useLocation } from 'react-router-dom';
import { useAuth, ROLE_LABELS } from '../auth.jsx';

const AREA = { director: 'directors', customer: 'customers' };

/** Shows children only to users with one of `roles`; visitors go to /login. */
export default function RequireRole({ roles, children }) {
  const { me } = useAuth();
  const location = useLocation();

  if (me === undefined) return <p className="empty" style={{ padding: '160px 0' }}>Loading…</p>;
  if (!me.authenticated) {
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  }
  if (!roles.includes(me.role)) {
    const home = me.home || '/';
    return (
      <section className="wrap login">
        <span className="eyebrow">{ROLE_LABELS[me.role] || 'Signed in'}</span>
        <h1 className="headline">This area is for {roles.map((r) => AREA[r] || r).join(' and ')}.</h1>
        <p className="lead">You’re signed in as {me.name}. Your work lives on your own screen.</p>
        {home.startsWith('/')
          ? <Link className="btn btn--primary" to={home}>Go to my screen</Link>
          : <a className="btn btn--primary" href={home}>Go to my screen</a>}
      </section>
    );
  }
  return children;
}
