import { useState } from "react";
import { request, setTokens } from "../api.js";
import { useAuth } from "../auth.jsx";
import { useToast } from "../components/toast.jsx";
import { formatDate } from "../components/ui.jsx";

const ROLE_LABEL = { customer: "Customer", administrator: "Administrator", inventory_manager: "Inventory manager" };

export default function Account() {
  const { user, setUser } = useAuth();
  const toast = useToast();

  const [name, setName] = useState(user.full_name);
  const [nameError, setNameError] = useState("");
  const [savingName, setSavingName] = useState(false);

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [passErrors, setPassErrors] = useState({});
  const [savingPass, setSavingPass] = useState(false);

  async function saveName(e) {
    e.preventDefault();
    if (name.trim().length < 2) {
      setNameError("Enter your full name (at least 2 characters).");
      return;
    }
    setNameError("");
    setSavingName(true);
    try {
      const updated = await request("/auth/me", { method: "PATCH", body: { full_name: name.trim() } });
      setUser(updated);
      toast.success("Your name was updated.");
    } catch (err) {
      setNameError(err.message);
    } finally {
      setSavingName(false);
    }
  }

  async function savePassword(e) {
    e.preventDefault();
    const errs = {};
    if (!current) errs.current = "Enter your current password.";
    if (next.length < 8) errs.next = "Use at least 8 characters.";
    else if (next.length > 72) errs.next = "Use at most 72 characters.";
    else if (next === current) errs.next = "The new password must be different from the current one.";
    if (confirm !== next) errs.confirm = "The passwords do not match.";
    setPassErrors(errs);
    if (Object.keys(errs).length) return;

    setSavingPass(true);
    try {
      const tokens = await request("/auth/change-password", {
        method: "POST",
        body: { current_password: current, new_password: next },
      });
      setTokens({ access_token: tokens.access_token, refresh_token: tokens.refresh_token });
      toast.success("Your password was changed. Other devices were signed out.");
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setPassErrors({ current: err.status === 400 ? err.message : "", form: err.status === 400 ? "" : err.message });
    } finally {
      setSavingPass(false);
    }
  }

  return (
    <div className="narrow" style={{ maxWidth: 520 }}>
      <h1>My account</h1>

      <div className="card">
        <div className="summary-row"><span className="muted">Email</span><span>{user.email}</span></div>
        <div className="summary-row"><span className="muted">Account type</span><span>{ROLE_LABEL[user.role] || user.role}</span></div>
        <div className="summary-row"><span className="muted">Member since</span><span>{formatDate(user.created_at)}</span></div>
      </div>

      <form className="card" onSubmit={saveName} noValidate>
        <h2 style={{ marginTop: 0 }}>Your name</h2>
        <label htmlFor="name">Full name</label>
        <input id="name" value={name} maxLength={150} onChange={(e) => setName(e.target.value)} />
        {nameError && <div className="field-error">{nameError}</div>}
        <button className="btn btn-primary btn-block" disabled={savingName || name.trim() === user.full_name}>
          {savingName ? "Saving..." : "Save name"}
        </button>
      </form>

      <form className="card" onSubmit={savePassword} noValidate>
        <h2 style={{ marginTop: 0 }}>Change password</h2>
        {passErrors.form && <div className="alert alert-error" role="alert">{passErrors.form}</div>}

        <label htmlFor="current">Current password</label>
        <input id="current" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
        {passErrors.current && <div className="field-error">{passErrors.current}</div>}

        <label htmlFor="next">New password</label>
        <input id="next" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
        {passErrors.next && <div className="field-error">{passErrors.next}</div>}

        <label htmlFor="confirm">Confirm new password</label>
        <input id="confirm" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        {passErrors.confirm && <div className="field-error">{passErrors.confirm}</div>}

        <button className="btn btn-primary btn-block" disabled={savingPass}>
          {savingPass ? "Changing..." : "Change password"}
        </button>
      </form>
    </div>
  );
}