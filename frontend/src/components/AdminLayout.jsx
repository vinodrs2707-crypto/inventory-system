import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth.jsx";

const LINKS = [
  { to: "/admin", label: "Dashboard", roles: ["administrator", "inventory_manager"], end: true },
  { to: "/admin/products", label: "Products", roles: ["administrator"] },
  { to: "/admin/inventory", label: "Inventory", roles: ["administrator", "inventory_manager"] },
  { to: "/admin/orders", label: "Orders", roles: ["administrator", "inventory_manager"] },
];

export default function AdminLayout() {
  const { user } = useAuth();
  return (
    <div className="admin">
      <nav className="sidebar" aria-label="Admin">
        {LINKS.filter((l) => l.roles.includes(user.role)).map((l) => (
          <NavLink key={l.to} to={l.to} end={l.end}>
            {l.label}
          </NavLink>
        ))}
      </nav>
      <section>
        <Outlet />
      </section>
    </div>
  );
}