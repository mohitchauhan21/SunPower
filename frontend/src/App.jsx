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
import Overview from './staff/Overview.jsx';
import { Customer, Customers, Enquiries, Enquiry, Order, Orders, Subsidies, Subsidy, Survey, Surveys } from './staff/Sales.jsx';
import { Deliveries, Delivery, Job, Jobs, Stock, Ticket, Tickets, Warranties } from './staff/Ops.jsx';
import { Reports, Settings } from './staff/Admin.jsx';

const TITLES = {
  '/': 'Rooftop solar', '/estimate': 'Savings estimate', '/quote': 'Get a quote', '/login': 'Sign in',
  '/forgot-password': 'Forgot password', '/reset-password': 'New password', '/signup': 'Create account', '/account': 'My account',
  '/app': 'Workspace', '/app/enquiries': 'Enquiries', '/app/surveys': 'Surveys', '/app/orders': 'Quotes & orders',
  '/app/dispatch': 'Dispatch', '/app/stock': 'Stock', '/app/jobs': 'Installations', '/app/service': 'Service',
  '/app/warranties': 'Warranties', '/app/customers': 'Customers', '/app/subsidy': 'Subsidy', '/app/reports': 'Reports',
  '/app/settings': 'Settings'
};

export default function App() {
  const { pathname } = useLocation();
  const inApp = pathname.startsWith('/app');
  useEffect(() => {
    window.scrollTo(0, 0);
    const key = Object.keys(TITLES).filter((k) => pathname === k || (k !== '/' && pathname.startsWith(k + '/'))).pop() || pathname;
    const title = pathname.startsWith('/account/quote') ? 'Your quotation' : TITLES[key] || 'Not found';
    document.title = `${title} · SunPower`;
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
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            <Route path="/logout" element={<Logout />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/account" element={<RequireRole roles={['customer']}><Account /></RequireRole>} />
            <Route path="/account/quote/:id" element={<RequireRole roles={['customer']}><QuoteReview /></RequireRole>} />
            <Route path="/console" element={<Navigate to="/app" replace />} />
            <Route path="/app" element={<StaffLayout />}>
              <Route index element={<Overview />} />
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
        </main>
        {!inApp && <Footer />}
      </ToastProvider>
    </AuthProvider>
  );
}
