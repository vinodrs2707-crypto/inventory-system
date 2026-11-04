import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";

export default function Layout() {
  const { user, logout } = useAuth();
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
                <span className="muted">Hi, {user.full_name.split(" ")[0]}</span>
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