import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { request } from "../api.js";
import { useAuth } from "../auth.jsx";
import ProductCard from "../components/ProductCard.jsx";
import { EmptyState, ErrorBox, Pagination, Spinner } from "../components/ui.jsx";

const SORTS = {
  newest: { label: "Newest", sort_by: "newest", order: "desc" },
  price_asc: { label: "Price: low to high", sort_by: "price", order: "asc" },
  price_desc: { label: "Price: high to low", sort_by: "price", order: "desc" },
  name: { label: "Name: A to Z", sort_by: "name", order: "asc" },
  rating: { label: "Top rated", sort_by: "rating", order: "desc" },
};
const PAGE_SIZE = 12;

export default function Catalog() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();

  const search = params.get("search") || "";
  const category = params.get("category") || "";
  const minPriceParam = params.get("min_price") || "";
  const maxPriceParam = params.get("max_price") || "";
  const minRating = params.get("min_rating") || "";
  const inStock = params.get("in_stock") === "true";
  const sortKey = SORTS[params.get("sort")] ? params.get("sort") : "newest";
  const page = Math.max(1, parseInt(params.get("page") || "1", 10) || 1);

  const [searchText, setSearchText] = useState(search);
  const [minPrice, setMinPrice] = useState(minPriceParam);
  const [maxPrice, setMaxPrice] = useState(maxPriceParam);
  const [priceError, setPriceError] = useState("");
  const [categories, setCategories] = useState([]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [recent, setRecent] = useState([]);
  const [reloadKey, setReloadKey] = useState(0);

  // the filters live in the web address, so the back button and page refresh keep them
  function updateParams(changes) {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([key, value]) => {
      if (value === "" || value === null || value === undefined || value === false) next.delete(key);
      else next.set(key, String(value));
    });
    if (!("page" in changes)) next.delete("page");
    setParams(next);
  }

  // search as you type, after a short pause
  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchText.trim() !== search) updateParams({ search: searchText.trim() });
    }, 400);
    return () => clearTimeout(timer);
  }, [searchText]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    request("/categories", { auth: false })
      .then(setCategories)
      .catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    if (!user) {
      setRecent([]);
      return;
    }
    request("/products/recently-viewed")
      .then(setRecent)
      .catch(() => setRecent([]));
  }, [user]);

  const paramsKey = params.toString();
  useEffect(() => {
    const controller = new AbortController();
    const sort = SORTS[sortKey];
    setLoading(true);
    setError(null);
    request("/products", {
      auth: false,
      signal: controller.signal,
      params: {
        search,
        category,
        min_price: minPriceParam,
        max_price: maxPriceParam,
        min_rating: minRating,
        in_stock: inStock ? "true" : "",
        sort_by: sort.sort_by,
        order: sort.order,
        page,
        page_size: PAGE_SIZE,
      },
    })
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [paramsKey, reloadKey]); // eslint-disable-line react-hooks/exhaustive-deps

  function applyPrice(e) {
    e.preventDefault();
    if (minPrice && maxPrice && Number(minPrice) > Number(maxPrice)) {
      setPriceError("The minimum price cannot be more than the maximum.");
      return;
    }
    if ((minPrice && Number(minPrice) < 0) || (maxPrice && Number(maxPrice) < 0)) {
      setPriceError("Prices cannot be negative.");
      return;
    }
    setPriceError("");
    updateParams({ min_price: minPrice, max_price: maxPrice });
  }

  function clearAll() {
    setSearchText("");
    setMinPrice("");
    setMaxPrice("");
    setPriceError("");
    setParams(new URLSearchParams());
  }

  const filtersActive = search || category || minPriceParam || maxPriceParam || minRating || inStock;

  return (
    <div>
      <h1>Shop</h1>

      {recent.length > 0 && !filtersActive && (
        <section>
          <h2 className="h2-small">Recently viewed</h2>
          <div className="recent-row">
            {recent.slice(0, 6).map((p) => (
              <ProductCard key={p.id} product={p} />
            ))}
          </div>
        </section>
      )}

      <div className="catalog">
        <aside className="filters card">
          <label htmlFor="search">Search</label>
          <input
            id="search"
            type="search"
            placeholder="Search products"
            maxLength={100}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />

          <label htmlFor="category">Category</label>
          <select id="category" value={category} onChange={(e) => updateParams({ category: e.target.value })}>
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>

          <form onSubmit={applyPrice}>
            <label>Price (INR)</label>
            <div className="price-inputs">
              <input type="number" min="0" placeholder="Min" value={minPrice} onChange={(e) => setMinPrice(e.target.value)} aria-label="Minimum price" />
              <input type="number" min="0" placeholder="Max" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)} aria-label="Maximum price" />
            </div>
            {priceError && <div className="field-error">{priceError}</div>}
            <button className="btn btn-secondary btn-small">Apply price</button>
          </form>

          <label htmlFor="rating">Minimum rating</label>
          <select id="rating" value={minRating} onChange={(e) => updateParams({ min_rating: e.target.value })}>
            <option value="">Any rating</option>
            <option value="4">4 stars and up</option>
            <option value="3">3 stars and up</option>
            <option value="2">2 stars and up</option>
          </select>

          <label className="check">
            <input type="checkbox" checked={inStock} onChange={(e) => updateParams({ in_stock: e.target.checked })} />
            In stock only
          </label>

          {filtersActive && (
            <button className="btn btn-secondary btn-small" onClick={clearAll}>
              Clear all filters
            </button>
          )}
        </aside>

        <section className="results">
          <div className="row-between">
            <span className="muted">{data ? `${data.total} product${data.total === 1 ? "" : "s"}` : ""}</span>
            <select value={sortKey} onChange={(e) => updateParams({ sort: e.target.value })} aria-label="Sort products">
              {Object.entries(SORTS).map(([key, s]) => (
                <option key={key} value={key}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>

          {loading && !data && <Spinner label="Loading products..." />}
          <ErrorBox error={error} onRetry={() => setReloadKey((k) => k + 1)} />

          {data && !error && data.items.length === 0 && (
            <EmptyState title="No products found">
              {filtersActive ? "Try changing or clearing your filters." : "Please check back soon."}
            </EmptyState>
          )}

          {data && data.items.length > 0 && (
            <div className={`grid ${loading ? "dim" : ""}`}>
              {data.items.map((p) => (
                <ProductCard key={p.id} product={p} />
              ))}
            </div>
          )}

          {data && (
            <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={(p) => updateParams({ page: p })} />
          )}
        </section>
      </div>
    </div>
  );
}