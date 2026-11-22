import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.jsx';
import './styles.css';
import './polish.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);

// Preloader (index.html): once the app has started, let the logo animation finish, then fade it out.
const intro = document.getElementById('intro');
if (intro) {
  if (document.documentElement.classList.contains('no-intro')) {
    intro.remove();
  } else {
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const wait = Math.max(0, (reduced ? 500 : 1900) - (Date.now() - (window.__introStart || 0)));
    setTimeout(() => {
      intro.classList.add('intro--out');
      setTimeout(() => { intro.remove(); window.dispatchEvent(new Event('sp:intro-done')); }, 600);   // the welcome tour waits for this
    }, wait);
  }
}
