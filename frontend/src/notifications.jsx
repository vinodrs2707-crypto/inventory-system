import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { request } from "./api.js";
import { useAuth } from "./auth.jsx";

const NotificationsContext = createContext({ unread: 0, refresh: () => {} });

export function NotificationsProvider({ children }) {
  const { user } = useAuth();
  const [unread, setUnread] = useState(0);

  const refresh = useCallback(() => {
    if (!user) {
      setUnread(0);
      return Promise.resolve();
    }
    return request("/notifications", { params: { page_size: 1 } })
      .then((d) => setUnread(d.unread_count))
      .catch(() => {});
  }, [user]);

  useEffect(() => {
    refresh();
    if (!user) return undefined;
    // check for new notifications every 30 seconds, but not while the tab is hidden
    const timer = setInterval(() => {
      if (!document.hidden) refresh();
    }, 30000);
    return () => clearInterval(timer);
  }, [refresh, user]);

  const value = useMemo(() => ({ unread, refresh }), [unread, refresh]);
  return <NotificationsContext.Provider value={value}>{children}</NotificationsContext.Provider>;
}

export function useNotifications() {
  return useContext(NotificationsContext);
}