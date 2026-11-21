import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth.jsx';

/** /logout: end the session, then go home (used by the mobile menu). */
export default function Logout() {
  const { signOut } = useAuth();
  const navigate = useNavigate();
  useEffect(() => { signOut().then(() => navigate('/', { replace: true })); }, [signOut, navigate]);
  return <p className="empty" style={{ padding: '160px 0' }}>Signing out…</p>;
}
