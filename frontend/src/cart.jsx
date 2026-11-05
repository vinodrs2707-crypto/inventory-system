import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { request } from "./api.js";
import { useAuth } from "./auth.jsx";

const CartContext = createContext({ count: 0, refresh: () => {}, setCount: () => {} });

export function CartProvider({ children }) {
  const { user } = useAuth();
  const [count, setCount] = useState(0);

  const refresh = useCallback(() => {
    if (!user) {
      setCount(0);
      return Promise.resolve();
    }
    return request("/cart")
      .then((cart) => setCount(cart.item_count))
      .catch(() => {});
  }, [user]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const value = useMemo(() => ({ count, refresh, setCount }), [count, refresh]);
  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart() {
  return useContext(CartContext);
}