import { useState } from "react";
import { request } from "../../api.js";
import { useToast } from "../../components/toast.jsx";
import { Modal } from "../../components/ui.jsx";

export default function ProductForm({ product, categories, onClose, onSaved }) {
  const toast = useToast();
  const [name, setName] = useState(product?.name || "");
  const [description, setDescription] = useState(product?.description || "");
  const [category, setCategory] = useState(product?.category || "");
  const [brand, setBrand] = useState(product?.brand || "");
  const [price, setPrice] = useState(product ? String(product.price) : "");
  const [imageUrl, setImageUrl] = useState(product?.image_url || "");
  const [specs, setSpecs] = useState(() => {
    const entries = Object.entries(product?.specifications || {});
    return entries.length ? entries.map(([key, value]) => ({ key, value })) : [{ key: "", value: "" }];
  });
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);

  function setSpec(index, field, value) {
    setSpecs((list) => list.map((s, i) => (i === index ? { ...s, [field]: value } : s)));
  }

  async function submit(e) {
    e.preventDefault();
    const next = {};
    if (name.trim().length < 2) next.name = "Enter the product name (at least 2 characters).";
    if (!description.trim()) next.description = "Enter a description.";
    if (category.trim().length < 2) next.category = "Enter a category (at least 2 characters).";
    if (!brand.trim()) next.brand = "Enter the brand.";
    const p = Number(price);
    if (price === "" || !(p > 0)) next.price = "Enter a price above 0.";
    else if (p > 10000000) next.price = "The price is too high.";
    if (imageUrl.trim() && !/^https?:\/\//i.test(imageUrl.trim())) next.image_url = "The image address must start with http:// or https://";
    const keys = specs.map((s) => s.key.trim()).filter(Boolean);
    if (new Set(keys.map((k) => k.toLowerCase())).size !== keys.length) next.specs = "Each specification name can be used once.";
    if (specs.some((s) => s.key.trim() && !s.value.trim())) next.specs = "Give every specification a value.";
    setErrors(next);
    if (Object.keys(next).length) return;

    const body = {
      name: name.trim(),
      description: description.trim(),
      category: category.trim(),
      brand: brand.trim(),
      price: p,
      image_url: imageUrl.trim() || null,
      specifications: Object.fromEntries(specs.filter((s) => s.key.trim()).map((s) => [s.key.trim(), s.value.trim()])),
    };

    setBusy(true);
    try {
      const saved = await request(product ? `/products/${product.id}` : "/products", {
        method: product ? "PUT" : "POST",
        body,
      });
      toast.success(product ? "Product updated." : "Product created. Add its stock on the Inventory page.");
      onSaved(saved);
    } catch (err) {
      const mapped = {};
      ["name", "description", "category", "brand", "price", "image_url"].forEach((f) => {
        const m = err.fieldError ? err.fieldError(f) : null;
        if (m) mapped[f] = m;
      });
      setErrors(Object.keys(mapped).length ? mapped : { form: err.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={product ? "Edit product" : "New product"} onClose={busy ? () => {} : onClose} wide>
      <form onSubmit={submit} noValidate>
        {errors.form && <div className="alert alert-error" role="alert">{errors.form}</div>}
        <div className="form-grid">
          <div className="full">
            <label htmlFor="p-name">Name</label>
            <input id="p-name" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
            {errors.name && <div className="field-error">{errors.name}</div>}
          </div>
          <div>
            <label htmlFor="p-category">Category</label>
            <input id="p-category" list="category-list" value={category} maxLength={100} onChange={(e) => setCategory(e.target.value)} />
            <datalist id="category-list">
              {categories.map((c) => <option key={c} value={c} />)}
            </datalist>
            {errors.category && <div className="field-error">{errors.category}</div>}
          </div>
          <div>
            <label htmlFor="p-brand">Brand</label>
            <input id="p-brand" value={brand} maxLength={100} onChange={(e) => setBrand(e.target.value)} />
            {errors.brand && <div className="field-error">{errors.brand}</div>}
          </div>
          <div>
            <label htmlFor="p-price">Price (INR)</label>
            <input id="p-price" type="number" min="0" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} />
            {errors.price && <div className="field-error">{errors.price}</div>}
          </div>
          <div>
            <label htmlFor="p-image">Image address (optional)</label>
            <input id="p-image" value={imageUrl} maxLength={500} placeholder="https://..." onChange={(e) => setImageUrl(e.target.value)} />
            {errors.image_url && <div className="field-error">{errors.image_url}</div>}
          </div>
          <div className="full">
            <label htmlFor="p-desc">Description</label>
            <textarea id="p-desc" rows={3} value={description} maxLength={5000} onChange={(e) => setDescription(e.target.value)} />
            {errors.description && <div className="field-error">{errors.description}</div>}
          </div>
          <div className="full">
            <label>Specifications</label>
            {specs.map((s, i) => (
              <div className="spec-row" key={i}>
                <input placeholder="Name (e.g. Color)" aria-label="Specification name" value={s.key} onChange={(e) => setSpec(i, "key", e.target.value)} />
                <input placeholder="Value (e.g. Black)" aria-label="Specification value" value={s.value} onChange={(e) => setSpec(i, "value", e.target.value)} />
                <button type="button" className="btn btn-secondary btn-small" onClick={() => setSpecs((l) => l.filter((_, idx) => idx !== i))} aria-label="Remove specification">×</button>
              </div>
            ))}
            <button type="button" className="btn btn-secondary btn-small" onClick={() => setSpecs((l) => [...l, { key: "", value: "" }])}>
              Add specification
            </button>
            {errors.specs && <div className="field-error">{errors.specs}</div>}
          </div>
        </div>
        <div className="row-end">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn btn-primary" disabled={busy}>{busy ? "Saving..." : "Save product"}</button>
        </div>
      </form>
    </Modal>
  );
}