import { useEffect } from 'react';
import { Routes, Route, useLocation } from 'react-router-dom';
import Nav from './components/Nav.jsx';
import Footer from './components/Footer.jsx';
import { ToastProvider } from './components/ui/Toast.jsx';
import Home from './pages/Home.jsx';
import Quote from './pages/Quote.jsx';
import Estimate from './pages/Estimate.jsx';
import NotFound from './pages/NotFound.jsx';
import Console from './console/Console.jsx';
import Login from './pages/Login.jsx';
import ForgotPassword from './pages/ForgotPassword.jsx';
import ResetPassword from './pages/ResetPassword.jsx';
import RequireRole from './components/RequireRole.jsx';
import { AuthProvider } from './auth.jsx';

const TITLES = { '/': 'Rooftop solar', '/estimate': 'Savings estimate', '/quote': 'Get a quote', '/console': 'Console', '/login': 'Sign in', '/forgot-password': 'Forgot password', '/reset-password': 'New password' };

export default function App() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
    document.title = `${TITLES[pathname] || 'Not found'} · SunPower`;
  }, [pathname]);

  return (
    <AuthProvider>
    <ToastProvider>
      <Nav />
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/quote" element={<Quote />} />
          <Route path="/estimate" element={<Estimate />} />
          <Route path="/console" element={<RequireRole roles={['director']}><Console /></RequireRole>} />
          <Route path="/login" element={<Login />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <Footer />
    </ToastProvider>
    </AuthProvider>
  );
}
