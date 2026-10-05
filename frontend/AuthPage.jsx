import React, { useState } from "react";
import "./AuthPage.css";
import { requireSupabase } from "./services/supabaseClient.js";

const initialValues = {
  name: "",
  email: "",
  password: "",
  confirmPassword: "",
};

function validate(values, mode) {
  const errors = {};

  if (mode === "signup" && !values.name.trim()) {
    errors.name = "Name is required.";
  }

  if (!values.email.trim()) {
    errors.email = "Email is required.";
  } else if (!/^\S+@\S+\.\S+$/.test(values.email)) {
    errors.email = "Enter a valid email address.";
  }

  if (!values.password) {
    errors.password = "Password is required.";
  }

  if (mode === "signup" && values.password !== values.confirmPassword) {
    errors.confirmPassword = "Passwords do not match.";
  }

  return errors;
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    try {
      await requireSupabase().auth.resetPasswordForEmail(email.trim(), {
        redirectTo: `${window.location.origin}/reset-password`,
      });
      // Deliberately generic: this does not disclose whether an account exists.
      setSubmitted(true);
    } catch {
      setSubmitted(true);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-panel" aria-labelledby="reset-title">
        <a className="auth-brand" href="/" aria-label="QueMe home">
          <span className="auth-brand-mark" aria-hidden="true" />
          <span>QueMe</span>
        </a>
        <div className="auth-heading">
          <p className="auth-eyebrow">Account recovery</p>
          <h1 id="reset-title">Reset your password.</h1>
          <p>Enter your email and we will send a password reset link.</p>
        </div>
        <form className="auth-form" onSubmit={handleSubmit}>
          <div className="auth-field">
            <label htmlFor="reset-email">Email address</label>
            <input
              id="reset-email"
              type="email"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                setSubmitted(false);
              }}
              placeholder="you@example.com"
              autoComplete="email"
              required
            />
          </div>
          <button className="btn btn-primary auth-submit" type="submit">Send reset link</button>
          {submitted && <p className="auth-success" role="status">Reset link request is ready to connect.</p>}
        </form>
        <p className="auth-switch"><a href="/login">Back to log in</a></p>
      </section>
      <aside className="auth-aside" aria-label="QueMe benefit">
        <div className="auth-aside-copy">
          <span className="auth-aside-kicker">Your prep room</span>
          <h2>Keep your progress close.</h2>
          <p>Your sessions, feedback, and reports are waiting when you return.</p>
        </div>
        <div className="auth-aside-mark" aria-hidden="true">Q</div>
      </aside>
    </main>
  );
}

export function ResetPasswordPage() {
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    try {
      const { error } = await requireSupabase().auth.updateUser({ password });
      setMessage(error ? error.message : "Password updated. You can now continue.");
    } catch (error) {
      setMessage(error.message || "Password reset is not configured.");
    }
  }

  return <main className="auth-page"><section className="auth-panel"><div className="auth-heading"><p className="auth-eyebrow">Account recovery</p><h1>Choose a new password.</h1></div><form className="auth-form" onSubmit={handleSubmit}><div className="auth-field"><label htmlFor="new-password">New password</label><input id="new-password" type="password" minLength="8" required value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" /></div><button className="btn btn-primary auth-submit" type="submit">Update password</button>{message && <p className="auth-success" role="status">{message}</p>}</form></section></main>;
}

export default function AuthPage({ mode = "login", onLogin }) {
  const isSignup = mode === "signup";
  const [values, setValues] = useState(initialValues);
  const [errors, setErrors] = useState({});
  const [submitted, setSubmitted] = useState(false);
  const [googleStarted, setGoogleStarted] = useState(false);
  const [formError, setFormError] = useState("");

  function handleChange(event) {
    const { name, value } = event.target;
    setValues((currentValues) => ({ ...currentValues, [name]: value }));
    setErrors((currentErrors) => ({ ...currentErrors, [name]: "" }));
    setSubmitted(false);
    setFormError("");
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const nextErrors = validate(values, mode);
    setErrors(nextErrors);
    setFormError("");

    if (Object.keys(nextErrors).length > 0) {
      return;
    }

    try {
      const client = requireSupabase();
      if (mode === "login") {
        const { data, error } = await client.auth.signInWithPassword({ email: values.email.trim(), password: values.password });
        if (error) throw error;
        const result = await onLogin?.(data.session);
        if (!result?.success) throw new Error(result?.message || "This account is not active.");
      } else {
        const { error } = await client.auth.signUp({
          email: values.email.trim(), password: values.password,
          options: { data: { full_name: values.name.trim() }, emailRedirectTo: `${window.location.origin}/auth/callback` },
        });
        if (error) throw error;
        setSubmitted(true);
      }
    } catch (error) {
      setFormError(error.message || "Authentication could not be completed.");
    }
  }

  async function handleGoogleContinue() {
    try {
      const { error } = await requireSupabase().auth.signInWithOAuth({ provider: "google", options: { redirectTo: `${window.location.origin}/auth/callback` } });
      if (error) throw error;
      setGoogleStarted(true);
    } catch (error) {
      setFormError(error.message || "Google sign-in is not configured.");
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-panel" aria-labelledby="auth-title">
        <a className="auth-brand" href="/" aria-label="QueMe home">
          <span className="auth-brand-mark" aria-hidden="true" />
          <span>QueMe</span>
        </a>

        <div className="auth-heading">
          <p className="auth-eyebrow">Interview preparation, focused</p>
          <h1 id="auth-title">{isSignup ? "Create your account." : "Welcome back."}</h1>
          <p>
            {isSignup
              ? "Build your interview confidence one session at a time."
              : "Pick up where your interview preparation left off."}
          </p>
        </div>

        <button className="auth-google" type="button" onClick={handleGoogleContinue}>
          <span className="google-mark" aria-hidden="true">G</span>
          Continue with Google
        </button>
        <div className="auth-divider"><span>or</span></div>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          {isSignup && (
            <div className="auth-field">
              <label htmlFor="name">Name</label>
              <input
                id="name"
                name="name"
                type="text"
                value={values.name}
                onChange={handleChange}
                autoComplete="name"
                aria-invalid={Boolean(errors.name)}
                aria-describedby={errors.name ? "name-error" : undefined}
              />
              {errors.name && <span id="name-error" className="auth-error">{errors.name}</span>}
            </div>
          )}

          <div className="auth-field">
            <label htmlFor="email">Email or username</label>
            <input
              id="email"
              name="email"
              type="email"
              value={values.email}
              onChange={handleChange}
              autoComplete="email"
              aria-invalid={Boolean(errors.email)}
              aria-describedby={errors.email ? "email-error" : undefined}
            />
            {errors.email && <span id="email-error" className="auth-error">{errors.email}</span>}
          </div>

          <div className="auth-field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              value={values.password}
              onChange={handleChange}
              autoComplete={isSignup ? "new-password" : "current-password"}
              aria-invalid={Boolean(errors.password)}
              aria-describedby={errors.password ? "password-error" : undefined}
            />
            {errors.password && <span id="password-error" className="auth-error">{errors.password}</span>}
          </div>

          {isSignup && (
            <div className="auth-field">
              <label htmlFor="confirmPassword">Confirm password</label>
              <input
                id="confirmPassword"
                name="confirmPassword"
                type="password"
                value={values.confirmPassword}
                onChange={handleChange}
                autoComplete="new-password"
                aria-invalid={Boolean(errors.confirmPassword)}
                aria-describedby={errors.confirmPassword ? "confirm-password-error" : undefined}
              />
              {errors.confirmPassword && (
                <span id="confirm-password-error" className="auth-error">{errors.confirmPassword}</span>
              )}
            </div>
          )}

          {!isSignup && (
            <a className="auth-forgot" href="/forgot-password">
              Forgot Password?
            </a>
          )}

          <button className="btn btn-primary auth-submit" type="submit">
            {isSignup ? "Create account" : "Log in"}
          </button>

          {formError && <p className="auth-error" role="alert">{formError}</p>}

          {submitted && !formError && (
            <p className="auth-success" role="status">
              {isSignup ? "Check your email to confirm your account. An administrator must then activate it." : "Login successful."}
            </p>
          )}
        </form>

        {googleStarted && (
          <p className="auth-success" role="status">Google sign-in is ready to connect.</p>
        )}

        {isSignup && (
          <p className="auth-switch">
            Already have an account? <a href="/login">Log in</a>
          </p>
        )}
      </section>

      <aside className="auth-aside" aria-label="QueMe benefit">
        <div className="auth-aside-copy">
          <span className="auth-aside-kicker">Your prep room</span>
          <h2>Make every answer sharper.</h2>
          <p>Track your progress, revisit thoughtful feedback, and walk into your next interview ready.</p>
        </div>
        <div className="auth-aside-mark" aria-hidden="true">Q</div>
      </aside>
    </main>
  );
}
