import { useCallback, useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { request } from "../api.js";
import { useAuth } from "../auth.jsx";
import { useToast } from "./toast.jsx";
import { ConfirmDialog, EmptyState, ErrorBox, Pagination, Spinner, Stars, formatDate } from "./ui.jsx";

const PAGE_SIZE = 5;

function StarInput({ value, onChange }) {
  return (
    <div className="star-input" role="radiogroup" aria-label="Rating">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          type="button"
          key={n}
          className={n <= value ? "on" : ""}
          onClick={() => onChange(n)}
          aria-label={`${n} star${n > 1 ? "s" : ""}`}
        >
          ★
        </button>
      ))}
    </div>
  );
}

function ReviewForm({ initial, busy, onSubmit, onCancel }) {
  const [rating, setRating] = useState(initial?.rating || 0);
  const [title, setTitle] = useState(initial?.title || "");
  const [comment, setComment] = useState(initial?.comment || "");
  const [errors, setErrors] = useState({});

  function submit(e) {
    e.preventDefault();
    const next = {};
    if (!rating) next.rating = "Please choose a rating.";
    if (comment.trim().length < 10) next.comment = "Please write at least 10 characters.";
    setErrors(next);
    if (Object.keys(next).length) return;
    onSubmit({ rating, title: title.trim() || null, comment: comment.trim() });
  }

  return (
    <form className="card review-form" onSubmit={submit} noValidate>
      <label>Your rating</label>
      <StarInput value={rating} onChange={setRating} />
      {errors.rating && <div className="field-error">{errors.rating}</div>}

      <label htmlFor="review-title">Title (optional)</label>
      <input id="review-title" value={title} maxLength={150} onChange={(e) => setTitle(e.target.value)} />

      <label htmlFor="review-comment">Your review</label>
      <textarea id="review-comment" rows={4} value={comment} maxLength={2000} onChange={(e) => setComment(e.target.value)} />
      {errors.comment && <div className="field-error">{errors.comment}</div>}

      <div className="row-end">
        <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? "Saving..." : initial ? "Save changes" : "Publish review"}
        </button>
      </div>
    </form>
  );
}

export default function Reviews({ productId, onSummary }) {
  const { user } = useAuth();
  const toast = useToast();
  const location = useLocation();

  const [sort, setSort] = useState("newest");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [mine, setMine] = useState(null);
  const [mode, setMode] = useState(null); // null, "new" or "edit"
  const [busy, setBusy] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    return request(`/products/${productId}/reviews`, { params: { sort, page, page_size: PAGE_SIZE } })
      .then((d) => {
        setData(d);
        if (onSummary) onSummary(d.summary);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, [productId, sort, page]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadMine = useCallback(() => {
    if (!user) {
      setMine(null);
      return;
    }
    request("/reviews/my-reviews")
      .then((list) => setMine(list.find((r) => r.product_id === Number(productId)) || null))
      .catch(() => setMine(null));
  }, [productId, user]);

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    loadMine();
  }, [loadMine]);

  async function save(values) {
    setBusy(true);
    try {
      if (mode === "edit") {
        await request(`/reviews/${mine.id}`, { method: "PUT", body: values });
        toast.success("Your review was updated.");
      } else {
        await request("/reviews", { method: "POST", body: { product_id: Number(productId), ...values } });
        toast.success("Thank you! Your review was published.");
      }
      setMode(null);
      setPage(1);
      await Promise.all([load(), loadMine()]);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await request(`/reviews/${mine.id}`, { method: "DELETE" });
      toast.success("Your review was deleted.");
      setConfirmOpen(false);
      setPage(1);
      await Promise.all([load(), loadMine()]);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  const summary = data?.summary;

  return (
    <section className="reviews">
      <h2>Ratings and reviews</h2>

      {summary && summary.count > 0 && (
        <div className="card review-summary">
          <div className="big-rating">
            <div className="big-number">{summary.average.toFixed(1)}</div>
            <Stars value={summary.average} />
            <div className="small muted">{summary.count} review{summary.count > 1 ? "s" : ""}</div>
          </div>
          <div className="bars">
            {[5, 4, 3, 2, 1].map((star) => {
              const n = summary.distribution[String(star)] || 0;
              const pct = summary.count ? (n / summary.count) * 100 : 0;
              return (
                <div className="bar-row" key={star}>
                  <span>{star}★</span>
                  <div className="bar">
                    <div className="bar-fill" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="small muted">{n}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* write, edit or sign in */}
      {!user && (
        <p>
          <Link to="/login" state={{ from: location }}>Sign in</Link> to write a review. Only customers who received the product can review it.
        </p>
      )}
      {user && mode && <ReviewForm initial={mode === "edit" ? mine : null} busy={busy} onSubmit={save} onCancel={() => setMode(null)} />}
      {user && !mode && mine && (
        <div className="card">
          <div className="row-between">
            <strong>Your review</strong>
            <div>
              <button className="btn btn-secondary btn-small" onClick={() => setMode("edit")}>Edit</button>{" "}
              <button className="btn btn-danger btn-small" onClick={() => setConfirmOpen(true)}>Delete</button>
            </div>
          </div>
          {mine.status === "hidden" && (
            <div className="alert alert-warn">A moderator has hidden your review{mine.moderation_note ? `: ${mine.moderation_note}` : "."}</div>
          )}
          <Stars value={mine.rating} />
          {mine.title && <div><strong>{mine.title}</strong></div>}
          <p>{mine.comment}</p>
        </div>
      )}
      {user && !mode && !mine && (
        <button className="btn btn-primary" onClick={() => setMode("new")}>Write a review</button>
      )}

      <div className="row-between" style={{ marginTop: 16 }}>
        <h3>All reviews</h3>
        <select value={sort} onChange={(e) => { setSort(e.target.value); setPage(1); }} aria-label="Sort reviews">
          <option value="newest">Newest first</option>
          <option value="highest">Highest rated</option>
          <option value="lowest">Lowest rated</option>
        </select>
      </div>

      {loading && !data && <Spinner label="Loading reviews..." />}
      <ErrorBox error={error} onRetry={load} />
      {data && data.items.length === 0 && <EmptyState title="No reviews yet">Be the first to share your experience.</EmptyState>}
      {data &&
        data.items.map((r) => (
          <article className="card review" key={r.id}>
            <div className="row-between">
              <Stars value={r.rating} />
              <span className="small muted">{formatDate(r.created_at)}</span>
            </div>
            {r.title && <strong>{r.title}</strong>}
            <p>{r.comment}</p>
            <div className="small muted">
              {r.reviewer_name} <span className="badge badge-ok">Verified purchase</span> {r.is_mine && <span className="badge">Your review</span>}
            </div>
          </article>
        ))}
      {data && <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={setPage} />}

      <ConfirmDialog
        open={confirmOpen}
        title="Delete your review?"
        message="This cannot be undone."
        confirmLabel="Delete"
        danger
        busy={busy}
        onConfirm={remove}
        onCancel={() => setConfirmOpen(false)}
      />
    </section>
  );
}