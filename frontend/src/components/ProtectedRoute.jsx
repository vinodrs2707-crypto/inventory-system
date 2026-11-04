import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { Spinner } from "./ui.jsx";

export default function ProtectedRoute({ roles, children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Spinner />;
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  if (roles && !roles.includes(user.role)) {
    return (
      <div className="center-box">
        <h3>You do not have access to this page</h3>
      </div>
    );
  }
  return children;
}