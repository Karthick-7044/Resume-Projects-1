import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';

const RouterCtx = createContext({ path: '/', navigate: () => {} });
const norm = (p) => (p.length > 1 ? p.replace(/\/+$/, '') : p) || '/';

export function Router({ children }) {
  const [path, setPath] = useState(norm(window.location.pathname));
  useEffect(() => {
    const onPop = () => setPath(norm(window.location.pathname));
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
  const navigate = useCallback((to) => {
    const next = norm(to);
    if (next === norm(window.location.pathname)) { window.scrollTo({ top: 0, behavior: 'smooth' }); return; }
    window.history.pushState({}, '', next);
    setPath(next);
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, []);
  return <RouterCtx.Provider value={{ path, navigate }}>{children}</RouterCtx.Provider>;
}

export const useRouter = () => useContext(RouterCtx);

export function Link({ to, onClick, children, ...rest }) {
  const { navigate } = useRouter();
  return (
    <a href={to} {...rest} onClick={(e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
      e.preventDefault();
      onClick?.(e);
      navigate(to);
    }}>{children}</a>
  );
}
