import { NavLink, Link, useNavigate, useLocation } from 'react-router-dom';
import { ROLE_LABELS, useAuth } from '../auth.jsx';
import GooeyNav from './reactbits/GooeyNav.jsx';
import BubbleMenu from './reactbits/BubbleMenu.jsx';
import Logo from './Logo.jsx';

// Home = top of the home page; Process = its "How it works" section; Savings = the savings estimator.
export const NAV_ITEMS = [
  { label: 'Home', path: '/' },
  { label: 'Process', path: '/#how-it-works' },
  { label: 'Savings', path: '/estimate' }
];
// Role links (the pages themselves are also role-guarded)
const STAFF_ITEMS = [{ label: 'Workspace', path: '/app' }];
const ROLE_ITEMS = {
  director: STAFF_ITEMS, sales: STAFF_ITEMS, warehouse: STAFF_ITEMS, technician: STAFF_ITEMS, support: STAFF_ITEMS,
  customer: [{ label: 'My account', path: '/account' }]
};

export default function Nav() {
  const { me, signOut } = useAuth();
  const navigate = useNavigate();
  const { pathname, hash } = useLocation();
  const signedIn = !!me?.authenticated;
  const items = [...NAV_ITEMS, ...(ROLE_ITEMS[me?.role] || [])];
  const out = async () => { await signOut(); navigate('/'); };
  const mine = me?.role === 'customer' ? '/account?tab=profile' : '/app/me';

  // Highlight the section link you came from on the home page, or the page you're on.
  const activeIndex = items.findIndex((i) => {
    const [p, h] = i.path.split('#');
    if (h) return pathname === '/' && hash === `#${h}`;
    return p === '/' ? pathname === '/' && !hash : pathname.startsWith(p);   // '/' would otherwise match every page
  });

  const mobileItems = [...items, ...(signedIn
    ? [{ label: 'Sign out', path: '/logout' }]
    : [{ label: 'Sign in', path: '/login' }])];
  if (!signedIn || me?.role === 'customer') mobileItems.splice(items.length, 0, { label: 'Book a survey', path: '/book-survey' });
  return (
    <>
      <header className="nav">
        <div className="wrap nav__inner">
          <Link to="/" aria-label="SunPower home"><Logo /></Link>
          <GooeyNav
            items={items.map((i) => ({ label: i.label }))}
            activeIndex={activeIndex >= 0 ? activeIndex : -1}
            onChange={(index) => {
              const item = items[index];
              if (!item) return;
              const [p, h] = item.path.split('#');
              navigate(item.path);
              // Already on that page (the URL doesn't change): move there ourselves.
              if (pathname === p && !h) window.scrollTo({ top: 0, behavior: 'smooth' });
              else if (pathname === p && hash === `#${h}`) {
                const el = document.getElementById(h);
                if (el) window.scrollTo({ top: window.scrollY + el.getBoundingClientRect().top - 72, behavior: 'smooth' });
              }
            }}
            theme="light"
            size="sm"
            color="#000000"
            activeTextColor="#ffffff"
            particleCount={12}
          />
          <div className="nav__actions">
            {signedIn ? (
              <>
                {me.role === 'customer' && <Link to="/book-survey" className="btn btn--primary btn--sm">Book a survey</Link>}
                <Link to={mine} className="nav__me" title={`${me.login} · ${ROLE_LABELS[me.role] || ''}`}>
                  <span className="nav__avatar" aria-hidden="true">{(me.name || '?').trim()[0]}</span>
                  <span>{me.name?.split(' ')[0]}</span>
                </Link>
                <button type="button" className="btn btn--secondary btn--sm" onClick={out}>Sign out</button>
              </>
            ) : (
              <>
                <Link to="/login" className="btn btn--secondary btn--sm">Sign in</Link>
                <Link to="/book-survey" className="btn btn--primary btn--sm">Book a survey</Link>
              </>
            )}
          </div>
        </div>
      </header>

      <div className="mobile-nav">
        <BubbleMenu
          logo={<Logo size={20} />}
          useFixedPosition
          menuBg="#ffffff"
          menuContentColor="#1d1d1f"
          items={mobileItems.map((i, n) => ({
            label: i.label.toLowerCase(),
            href: i.path,
            ariaLabel: i.label,
            rotation: n % 2 ? 4 : -4,
            hoverStyles: { bgColor: '#F5A623', textColor: '#1d1d1f' }
          }))}
        />
      </div>
    </>
  );
}
