import { useEffect } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import Nav from './components/Nav.jsx';
import Footer from './components/Footer.jsx';
import { ToastProvider } from './components/ui/Toast.jsx';
import Home from './pages/Home.jsx';
import Quote from './pages/Quote.jsx';
import Estimate from './pages/Estimate.jsx';
import NotFound from './pages/NotFound.jsx';
import Login from './pages/Login.jsx';
import ForgotPassword from './pages/ForgotPassword.jsx';
import ResetPassword from './pages/ResetPassword.jsx';
import Signup from './pages/Signup.jsx';
import Account from './pages/Account.jsx';
import QuoteReview from './pages/QuoteReview.jsx';
import Logout from './pages/Logout.jsx';
import RequireRole from './components/RequireRole.jsx';
import { AuthProvider } from './auth.jsx';
import StaffLayout from './staff/Layout.jsx';
import Today, { Insights, StaffMe } from './staff/Overview.jsx';
import Onboarding from './components/Onboarding.jsx';
import ErrorBoundary from './components/ErrorBoundary.jsx';
import { Customer, Customers, Enquiries, Enquiry, Order, Orders, Subsidies, Subsidy, Survey, Surveys } from './staff/Sales.jsx';
import { Deliveries, Delivery, Job, Jobs, Stock, Ticket, Tickets, Warranties } from './staff/Ops.jsx';
import { Reports, Settings } from './staff/Admin.jsx';

const TITLES = {
  '/': 'Rooftop solar', '/estimate': 'Savings estimate', '/book-survey': 'Book a survey', '/login': 'Sign in',
  '/forgot-password': 'Forgot password', '/reset-password': 'New password', '/signup': 'Create account', '/account': 'My account',
  '/app': 'Today', '/app/insights': 'Insights', '/app/me': 'My account', '/app/enquiries': 'Enquiries', '/app/surveys': 'Surveys', '/app/orders': 'Quotes & orders',
  '/app/dispatch': 'Dispatch', '/app/stock': 'Stock', '/app/jobs': 'Installations', '/app/service': 'Service',
  '/app/warranties': 'Warranties', '/app/customers': 'Customers', '/app/subsidy': 'Subsidy', '/app/reports': 'Reports',
  '/app/settings': 'Settings'
};

export default function App() {
  const { pathname, hash } = useLocation();
  const inApp = pathname.startsWith('/app');
  // Navbar links like /#packages jump to that section (also when already on the page).
  useEffect(() => {
    if (!hash) return undefined;
    // Animated sections above (stacking cards, reveals) change the page height while it lays out,
    // so jump, then re-check the position a few times until the section stays put.
    let tries = 0;
    let timer;
    const go = () => {
      const el = document.getElementById(hash.slice(1));
      if (el) {
        const offset = el.getBoundingClientRect().top - 72;   // leave room for the navbar
        if (Math.abs(offset) > 4) window.scrollTo(0, window.scrollY + offset);
        if (tries++ < 8) timer = setTimeout(go, 150);
      } else if (tries++ < 20) {
        timer = setTimeout(go, 50);   // the page may still be rendering
      }
    };
    go();
    return () => clearTimeout(timer);
  }, [pathname, hash]);
  useEffect(() => {
    if (!window.location.hash) window.scrollTo(0, 0);
    const key = Object.keys(TITLES).filter((k) => pathname === k || (k !== '/' && pathname.startsWith(k + '/'))).pop() || pathname;
    const title = pathname.startsWith('/account/quote') ? 'Your quotation' : TITLES[key] || 'Not found';
    document.title = `${title} · SunPower`;
  }, [pathname]);

  return (
    <AuthProvider>
      <ToastProvider>
        <Nav />
        <main>
          <ErrorBoundary resetKey={pathname}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/book-survey" element={<Quote />} />
            <Route path="/quote" element={<Navigate to="/book-survey" replace />} />
            <Route path="/estimate" element={<Estimate />} />
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            <Route path="/logout" element={<Logout />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/account" element={<RequireRole roles={['customer']}><Account /></RequireRole>} />
            <Route path="/account/quote/:id" element={<RequireRole roles={['customer']}><QuoteReview /></RequireRole>} />
            <Route path="/console" element={<Navigate to="/app" replace />} />
            <Route path="/app" element={<StaffLayout />}>
              <Route index element={<Today />} />
              <Route path="insights" element={<Insights />} />
              <Route path="me" element={<StaffMe />} />
              <Route path="enquiries" element={<Enquiries />} />
              <Route path="enquiries/:id" element={<Enquiry />} />
              <Route path="surveys" element={<Surveys />} />
              <Route path="surveys/:id" element={<Survey />} />
              <Route path="orders" element={<Orders />} />
              <Route path="orders/:id" element={<Order />} />
              <Route path="dispatch" element={<Deliveries />} />
              <Route path="dispatch/:id" element={<Delivery />} />
              <Route path="stock" element={<Stock />} />
              <Route path="jobs" element={<Jobs />} />
              <Route path="jobs/:id" element={<Job />} />
              <Route path="service" element={<Tickets />} />
              <Route path="service/:id" element={<Ticket />} />
              <Route path="warranties" element={<Warranties />} />
              <Route path="customers" element={<Customers />} />
              <Route path="customers/:id" element={<Customer />} />
              <Route path="subsidy" element={<Subsidies />} />
              <Route path="subsidy/:id" element={<Subsidy />} />
              <Route path="reports" element={<Reports />} />
              <Route path="settings" element={<Settings />} />
            </Route>
            <Route path="*" element={<NotFound />} />
          </Routes>
          </ErrorBoundary>
        </main>
        {!inApp && <Footer />}
        <Onboarding />
      </ToastProvider>
    </AuthProvider>
  );
}
