import { Link, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import Catalog from "./pages/Catalog.jsx";
import Login from "./pages/Login.jsx";
import ProductDetail from "./pages/ProductDetail.jsx";
import Register from "./pages/Register.jsx";

function NotFound() {
  return (
    <div className="center-box">
      <h1>Page not found</h1>
      <Link to="/">Back to the shop</Link>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Catalog />} />
        <Route path="/products/:id" element={<ProductDetail />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}