import { Link, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import Account from "./pages/Account.jsx";
import Cart from "./pages/Cart.jsx";
import Catalog from "./pages/Catalog.jsx";
import Checkout from "./pages/Checkout.jsx";
import Login from "./pages/Login.jsx";
import Notifications from "./pages/Notifications.jsx";
import OrderConfirmation from "./pages/OrderConfirmation.jsx";
import OrderDetail from "./pages/OrderDetail.jsx";
import Orders from "./pages/Orders.jsx";
import ProductDetail from "./pages/ProductDetail.jsx";
import Register from "./pages/Register.jsx";
import ReturnDetail from "./pages/ReturnDetail.jsx";
import ReturnNew from "./pages/ReturnNew.jsx";
import Returns from "./pages/Returns.jsx";
import Wishlist from "./pages/Wishlist.jsx";

function NotFound() {
  return (
    <div className="center-box">
      <h1>Page not found</h1>
      <Link to="/">Back to the shop</Link>
    </div>
  );
}

function Private({ children }) {
  return <ProtectedRoute>{children}</ProtectedRoute>;
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Catalog />} />
        <Route path="/products/:id" element={<ProductDetail />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/cart" element={<Private><Cart /></Private>} />
        <Route path="/wishlist" element={<Private><Wishlist /></Private>} />
        <Route path="/checkout" element={<Private><Checkout /></Private>} />
        <Route path="/orders" element={<Private><Orders /></Private>} />
        <Route path="/orders/:id" element={<Private><OrderDetail /></Private>} />
        <Route path="/orders/:id/confirmation" element={<Private><OrderConfirmation /></Private>} />
        <Route path="/returns" element={<Private><Returns /></Private>} />
        <Route path="/returns/new" element={<Private><ReturnNew /></Private>} />
        <Route path="/returns/:id" element={<Private><ReturnDetail /></Private>} />
        <Route path="/notifications" element={<Private><Notifications /></Private>} />
        <Route path="/account" element={<Private><Account /></Private>} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}