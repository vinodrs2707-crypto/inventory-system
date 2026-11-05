import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { useCart } from "../cart.jsx";
import { useNotifications } from "../notifications.jsx";

export default function Layout() {
  const { user, logout } = useAuth();
  const { count } = useCart();
  const { unread } = useNotifications();
  const navigate = useNavigate();

  function signOut() {
    logout();
    navigate("/");
  }

  return (
    <>
      <header className="header">
        <div className="header-inner">
          <Link to="/" className="brand">
            ShopHub
          </Link>
          <nav className="nav" aria-label="Main">
            <NavLink to="/" end>
              Shop
            </NavLink>
            {user ? (
              <>
                <NavLink to="/wishlist">Wishlist</NavLink>
                <NavLink to="/cart">
                  Cart{count > 0 && <span className="count">{count}</span>}
                </NavLink>
                <NavLink to="/orders">Orders</NavLink>
                <NavLink to="/returns">Returns</NavLink>
                <NavLink to="/notifications">
                  Notifications{unread > 0 && <span className="count">{unread}</span>}
                </NavLink>
                <NavLink to="/account">{user.full_name.split(" ")[0]}</NavLink>
                <button className="btn btn-secondary btn-small" onClick={signOut}>
                  Sign out
                </button>
              </>
            ) : (
              <>
                <NavLink to="/login">Sign in</NavLink>
                <NavLink to="/register">Create account</NavLink>
              </>
            )}
          </nav>
        </div>
      </header>
      <main className="container">
        <Outlet />
      </main>
      <footer className="footer">ShopHub, a demo store</footer>
    </>
  );
}