import { useState } from "react";
import { Link } from "react-router-dom";
import { Stars, formatPrice } from "./ui.jsx";

export default function ProductCard({ product }) {
  const [imageFailed, setImageFailed] = useState(false);
  const showImage = product.image_url && !imageFailed;

  let stock;
  if (!product.in_stock) stock = <span className="badge badge-danger">Out of stock</span>;
  else if (product.stock_quantity <= 5) stock = <span className="badge badge-warn">Only {product.stock_quantity} left</span>;
  else stock = <span className="badge badge-ok">In stock</span>;

  return (
    <Link to={`/products/${product.id}`} className="card product-card">
      <div className="product-image">
        {showImage ? (
          <img src={product.image_url} alt={product.name} loading="lazy" onError={() => setImageFailed(true)} />
        ) : (
          <span className="placeholder" aria-hidden="true">
            {product.name.slice(0, 1).toUpperCase()}
          </span>
        )}
      </div>
      <div className="product-body">
        <div className="small muted">
          {product.brand} · {product.category}
        </div>
        <h3 className="product-title">{product.name}</h3>
        <Stars value={product.rating_average} count={product.rating_count} />
        <div className="price">{formatPrice(product.price)}</div>
        {stock}
      </div>
    </Link>
  );
}