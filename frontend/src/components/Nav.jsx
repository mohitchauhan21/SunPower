import { NavLink, Link } from 'react-router-dom';
import BubbleMenu from './reactbits/BubbleMenu.jsx';
import Logo from './Logo.jsx';

export const NAV_ITEMS = [
  { label: 'Solar', path: '/' },
  { label: 'Savings', path: '/estimate' },
  { label: 'Quote', path: '/quote' },
  { label: 'Console', path: '/console' }
];

export default function Nav() {
  return (
    <>
      <header className="nav">
        <div className="wrap nav__inner">
          <Link to="/" aria-label="SunPower home"><Logo /></Link>
          <nav className="nav__links" aria-label="Main">
            {NAV_ITEMS.map((i) => (
              <NavLink key={i.path} to={i.path} end className={({ isActive }) => `nav__link${isActive ? ' is-active' : ''}`}>
                {i.label}
              </NavLink>
            ))}
            <a className="nav__link" href="http://localhost:8069/my/solar">My Solar</a>
          </nav>
          <Link to="/quote" className="btn btn--primary btn--sm">Free survey</Link>
        </div>
      </header>

      <div className="mobile-nav">
        <BubbleMenu
          logo={<Logo size={20} />}
          useFixedPosition
          menuBg="#ffffff"
          menuContentColor="#1d1d1f"
          items={NAV_ITEMS.map((i, n) => ({
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
