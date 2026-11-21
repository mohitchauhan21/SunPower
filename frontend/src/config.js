// Address of the SunPower back office (staff screens, crew app, quote PDFs).
// Set VITE_ENGINE_URL in frontend/.env for a deployed server.
export const ENGINE = (import.meta.env.VITE_ENGINE_URL || 'http://localhost:8069').replace(/\/$/, '');
