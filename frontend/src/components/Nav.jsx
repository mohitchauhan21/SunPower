import { NavLink, Link, useNavigate, useLocation } from 'react-router-dom';
import { ROLE_LABELS, useAuth } from '../auth.jsx';
import GooeyNav from './reactbits/GooeyNav.jsx';
import BubbleMenu from './reactbits/BubbleMenu.jsx';
import Logo from './Logo.jsx';

export const NAV_ITEMS = [
  { label: 'Solar', path: '/' },
  { label: 'Savings', path: '/estimate' },
  { label: 'Quote', path: '/quote' }
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
  const { pathname } = useLocation();
  const signedIn = !!me?.authenticated;
  const items = [...NAV_ITEMS, ...(ROLE_ITEMS[me?.role] || [])];
  const out = async () => { await signOut(); navigate('/'); };
  const mine = me?.role === 'customer' ? '/account?tab=profile' : '/app/me';

  const activeIndex = items.findIndex((i) =>
    i.path === '/' ? pathname === '/' : pathname.startsWith(i.path)
  );

  const mobileItems = [...items, ...(signedIn
    ? [{ label: 'Sign out', path: '/logout' }]
    : [{ label: 'Sign in', path: '/login' }, { label: 'Get started', path: '/estimate' }])];
  return (
    <>
      <header className="nav">
        <div className="wrap nav__inner">
          <Link to="/" aria-label="SunPower home"><Logo /></Link>
          <GooeyNav
            items={items.map((i) => ({ label: i.label }))}
            activeIndex={activeIndex >= 0 ? activeIndex : 0}
            onChange={(index) => {
              if (items[index]) navigate(items[index].path);
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
                <Link to={mine} className="nav__me" title={`${me.login} · ${ROLE_LABELS[me.role] || ''}`}>
                  <span className="nav__avatar" aria-hidden="true">{(me.name || '?').trim()[0]}</span>
                  <span>{me.name?.split(' ')[0]}</span>
                </Link>
                <button type="button" className="btn btn--secondary btn--sm" onClick={out}>Sign out</button>
              </>
            ) : (
              <>
                <Link to="/login" className="btn btn--secondary btn--sm">Sign in</Link>
                <Link to="/estimate" className="btn btn--primary btn--sm">Get started</Link>
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
