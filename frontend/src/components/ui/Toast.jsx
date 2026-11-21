import { createContext, useCallback, useContext, useState } from 'react';

/* Toast stack that fans out on hover (Arc UI "Toast stack" pattern). */
const ToastContext = createContext(() => {});
export const useToast = () => useContext(ToastContext);

let seq = 0;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const [open, setOpen] = useState(false);

  const dismiss = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const toast = useCallback((message, type = 'success') => {
    const id = ++seq;
    setToasts((t) => [...t.slice(-3), { id, message, type }]);
    setTimeout(() => dismiss(id), 6000);
  }, [dismiss]);

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div className="toasts" aria-live="polite" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
        {toasts.map((t, i) => {
          const depth = toasts.length - 1 - i;
          const transform = open
            ? `translateY(${-depth * 64}px)`
            : `translateY(${-depth * 10}px) scale(${1 - depth * 0.05})`;
          return (
            <div
              key={t.id}
              className={`toast toast--${t.type}`}
              role={t.type === 'error' ? 'alert' : 'status'}
              style={{ transform, opacity: depth > 2 ? 0 : 1, zIndex: i }}
            >
              <span className="toast__dot" />
              <span>{t.message}</span>
              <button className="toast__close" aria-label="Dismiss" onClick={() => dismiss(t.id)}>×</button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
