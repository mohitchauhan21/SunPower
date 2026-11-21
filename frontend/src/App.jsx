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

const TITLES = { '/': 'Rooftop solar', '/estimate': 'Savings estimate', '/quote': 'Get a quote', '/console': 'Console' };

export default function App() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
    document.title = `${TITLES[pathname] || 'Not found'} · SunPower`;
  }, [pathname]);

  return (
    <ToastProvider>
      <Nav />
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/quote" element={<Quote />} />
          <Route path="/estimate" element={<Estimate />} />
          <Route path="/console" element={<Console />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <Footer />
    </ToastProvider>
  );
}
