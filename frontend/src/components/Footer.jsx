import { Link } from 'react-router-dom';
import Logo from './Logo.jsx';
import { ENGINE } from '../config.js';

export default function Footer() {
  return (
    <footer className="footer">
      <div className="wrap">
        <div className="footer__grid">
          <div>
            <Logo />
            <p style={{ marginTop: 12, maxWidth: 320, lineHeight: 1.5 }}>
              Rooftop solar for homes and small businesses in Ahmedabad. Surveyed, installed and serviced by our own crew.
            </p>
          </div>
          <div>
            <h4>Explore</h4>
            <Link to="/estimate">Savings estimate</Link>
            <Link to="/quote">Get a quote</Link>
          </div>
          <div>
            <h4>Customers</h4>
            <Link to="/account">My account</Link>
            <Link to="/signup">Create an account</Link>
            <Link to="/account?tab=service">Report a problem</Link>
          </div>
          <div>
            <h4>Team</h4>
            <Link to="/login">Staff sign-in</Link>
            <a href={`${ENGINE}/technician`}>Crew app</a>
          </div>
          <div>
            <h4>Contact</h4>
            <a href="tel:+917940005000">+91 79 4000 5000</a>
            <a href="mailto:hello@sunpower.example">hello@sunpower.example</a>
            <span>12 Solar Park Road, SG Highway, Ahmedabad 380054</span>
          </div>
        </div>
        <div className="footer__legal">
          <span>Copyright © {new Date().getFullYear()} SunPower Solutions. All rights reserved.</span>
          <span>Estimates are indicative. Final prices are fixed after the site survey.</span>
        </div>
      </div>
    </footer>
  );
}
