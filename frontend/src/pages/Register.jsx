import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { useToast } from "../components/toast.jsx";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Register() {
  const { register } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    const next = {};
    if (fullName.trim().length < 2) next.fullName = "Enter your full name (at least 2 characters).";
    if (!EMAIL.test(email.trim())) next.email = "Enter a valid email address.";
    if (password.length < 8) next.password = "Use at least 8 characters.";
    else if (password.length > 72) next.password = "Use at most 72 characters.";
    if (confirm !== password) next.confirm = "The passwords do not match.";
    setErrors(next);
    setFormError("");
    if (Object.keys(next).length) return;

    setBusy(true);
    try {
      await register(fullName.trim(), email.trim().toLowerCase(), password);
      toast.success("Welcome to ShopHub! Your account is ready.");
      navigate("/", { replace: true });
    } catch (err) {
      // show the server's message under the right field when it names one
      const emailMsg = err.fieldError && (err.fieldError("email"));
      const passMsg = err.fieldError && err.fieldError("password");
      const nameMsg = err.fieldError && err.fieldError("full_name");
      if (emailMsg || passMsg || nameMsg) {
        setErrors({ email: emailMsg, password: passMsg, fullName: nameMsg });
      } else if (err.status === 409) {
        setErrors({ email: err.message });
      } else {
        setFormError(err.message);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="narrow">
      <h1>Create your account</h1>
      <form className="card" onSubmit={submit} noValidate>
        {formError && <div className="alert alert-error" role="alert">{formError}</div>}

        <label htmlFor="name">Full name</label>
        <input id="name" autoComplete="name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
        {errors.fullName && <div className="field-error">{errors.fullName}</div>}

        <label htmlFor="email">Email</label>
        <input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        {errors.email && <div className="field-error">{errors.email}</div>}

        <label htmlFor="password">Password</label>
        <input id="password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        {errors.password && <div className="field-error">{errors.password}</div>}

        <label htmlFor="confirm">Confirm password</label>
        <input id="confirm" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        {errors.confirm && <div className="field-error">{errors.confirm}</div>}

        <button className="btn btn-primary btn-block" disabled={busy}>
          {busy ? "Creating account..." : "Create account"}
        </button>
      </form>
      <p className="muted">
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </div>
  );
}