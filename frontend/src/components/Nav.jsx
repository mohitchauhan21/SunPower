import { NavLink, Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth.jsx';
import BubbleMenu from './reactbits/BubbleMenu.jsx';
import Logo from './Logo.jsx';

export const NAV_ITEMS = [
  { label: 'Solar', path: '/' },
  { label: 'Savings', path: '/estimate' },
  { label: 'Quote', path: '/quote' }
];
// Only directors see the Console link (the page itself is also role-guarded)
const DIRECTOR_ITEMS = [{ label: 'Console', path: '/console' }];

export default function Nav() {
  const { me, signOut } = useAuth();
  const navigate = useNavigate();
  const items = me?.role === 'director' ? [...NAV_ITEMS, ...DIRECTOR_ITEMS] : NAV_ITEMS;
  const out = async () => { await signOut(); navigate('/'); };
  const mobileItems = [...items, me?.authenticated ? { label: 'Sign out', path: '/login' } : { label: 'Sign in', path: '/login' }];
  return (
    <>
      <header className="nav">
        <div className="wrap nav__inner">
          <Link to="/" aria-label="SunPower home"><Logo /></Link>
          <nav className="nav__links" aria-label="Main">
            {items.map((i) => (
              <NavLink key={i.path} to={i.path} end className={({ isActive }) => `nav__link${isActive ? ' is-active' : ''}`}>
                {i.label}
              </NavLink>
            ))}
            <a className="nav__link" href="http://localhost:8069/my/solar">My Solar</a>
          </nav>
          <div className="nav__actions">
            {me?.authenticated ? (
              <>
                {me.role !== 'director' && me.home && !me.home.startsWith('/') && <a className="nav__link" href={me.home}>My screen</a>}
                <span className="nav__user" title={me.login}>{me.name?.split(' ')[0]}</span>
                <button type="button" className="nav__link nav__btn" onClick={out}>Sign out</button>
              </>
            ) : (
              <Link to="/login" className="nav__link">Sign in</Link>
            )}
            <Link to="/quote" className="btn btn--primary btn--sm">Free survey</Link>
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
