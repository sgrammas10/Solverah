import { useNavigate } from "react-router-dom";
import { AccountStep, AccountAction } from "../../hooks/useIntakeForm";

const inputCls =
  "w-full rounded border border-cream-muted bg-cream-base px-3 py-2.5 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-forest-light focus:outline-none focus:ring-2 focus:ring-forest-pale transition-colors";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  submissionEmail: string;
  step: AccountStep;
  setStep: (s: AccountStep) => void;
  action: AccountAction;
  signInEmail: string;
  setSignInEmail: (s: string) => void;
  signInPassword: string;
  setSignInPassword: (s: string) => void;
  accountPassword: string;
  setAccountPassword: (s: string) => void;
  accountConfirm: string;
  setAccountConfirm: (s: string) => void;
  error: string;
  setError: (s: string) => void;
  isCreatingAccount: boolean;
  isSigningIn: boolean;
  onCreateAccount: () => void;
  onSignInExisting: () => void;
};

export default function AccountModal({
  isOpen,
  onClose,
  submissionEmail,
  step,
  setStep,
  action,
  signInEmail,
  setSignInEmail,
  signInPassword,
  setSignInPassword,
  accountPassword,
  setAccountPassword,
  accountConfirm,
  setAccountConfirm,
  error,
  setError,
  isCreatingAccount,
  isSigningIn,
  onCreateAccount,
  onSignInExisting,
}: Props) {
  const navigate = useNavigate();

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto px-4 py-6 sm:py-10">
      <div
        className="absolute inset-0 bg-ink-primary/60 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="relative w-full max-w-lg max-h-[calc(100vh-3rem)] overflow-y-auto rounded-xl border border-cream-muted bg-cream-base p-8 shadow-2xl animate-fade-in">
        <button
          type="button"
          aria-label="Close"
          onClick={onClose}
          className="absolute right-4 top-4 h-8 w-8 flex items-center justify-center rounded border border-cream-muted text-ink-secondary hover:border-forest-pale hover:text-forest-mid transition-colors"
        >
          ✕
        </button>

        <div className="pr-10">
          <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">Next step</p>
          <h3 className="font-display text-2xl font-semibold text-ink-primary">Save your profile?</h3>
          <p className="mt-2 text-sm text-ink-secondary leading-relaxed">
            Create an account and we'll auto-fill your profile using your resume. You can edit anything later.
          </p>
        </div>

        {step === "prompt" && (
          <div className="mt-6 space-y-4">
            <div className="rounded border border-cream-muted bg-white p-4 text-sm text-ink-secondary leading-relaxed">
              We'll populate your personal info, work experience, skills, and education using the resume you shared.
            </div>
            <div className="flex flex-wrap items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => { setStep("signin"); setError(""); setSignInEmail(submissionEmail); setSignInPassword(""); }}
                className="px-5 py-2.5 text-sm font-semibold text-forest-mid border border-forest-pale rounded hover:bg-forest-pale transition-colors"
              >
                Sign in
              </button>
              <button
                type="button"
                onClick={() => setStep("form")}
                className="bg-forest-dark text-white font-semibold text-sm px-6 py-2.5 rounded hover:bg-forest-mid transition-colors"
              >
                Create account
              </button>
            </div>
          </div>
        )}

        {step === "form" && (
          <div className="mt-6 space-y-4">
            <div className="grid gap-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-ink-primary">Create a password</label>
                <input
                  type="password"
                  value={accountPassword}
                  onChange={(e) => setAccountPassword(e.target.value)}
                  className={inputCls}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-ink-primary">Confirm password</label>
                <input
                  type="password"
                  value={accountConfirm}
                  onChange={(e) => setAccountConfirm(e.target.value)}
                  className={inputCls}
                />
              </div>
            </div>
            {error && (
              <p className="rounded bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">{error}</p>
            )}
            <div className="flex flex-wrap items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => setStep("prompt")}
                className="px-5 py-2.5 text-sm font-semibold text-ink-secondary border border-cream-muted rounded hover:border-forest-pale transition-colors"
              >
                Back
              </button>
              <button
                type="button"
                disabled={isCreatingAccount}
                onClick={onCreateAccount}
                className="bg-forest-dark text-white font-semibold text-sm px-6 py-2.5 rounded hover:bg-forest-mid transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isCreatingAccount ? "Creating…" : "Create account"}
              </button>
            </div>
          </div>
        )}

        {step === "signin" && (
          <div className="mt-6 space-y-4">
            <div className="grid gap-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-ink-primary">Email</label>
                <input
                  type="email"
                  value={signInEmail}
                  onChange={(e) => setSignInEmail(e.target.value)}
                  className={inputCls}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-ink-primary">Password</label>
                <input
                  type="password"
                  value={signInPassword}
                  onChange={(e) => setSignInPassword(e.target.value)}
                  className={inputCls}
                />
              </div>
            </div>
            {error && (
              <p className="rounded bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">{error}</p>
            )}
            <div className="flex flex-wrap items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => setStep("prompt")}
                className="px-5 py-2.5 text-sm font-semibold text-ink-secondary border border-cream-muted rounded hover:border-forest-pale transition-colors"
              >
                Back
              </button>
              <button
                type="button"
                disabled={isSigningIn}
                onClick={onSignInExisting}
                className="bg-forest-dark text-white font-semibold text-sm px-6 py-2.5 rounded hover:bg-forest-mid transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isSigningIn ? "Signing in…" : "Sign in"}
              </button>
            </div>
          </div>
        )}

        {step === "success" && (
          <div className="mt-6 space-y-4">
            <div className="rounded bg-forest-pale border border-forest-pale px-4 py-3 text-sm text-forest-dark font-medium">
              {action === "signin"
                ? "Signed in! Your profile has been updated from your intake submission."
                : "Account created! Your profile has been filled in from your resume."}
            </div>
            <div className="flex flex-wrap items-center justify-end gap-3">
              {action === "signin" ? (
                <button
                  type="button"
                  onClick={onClose}
                  className="bg-forest-dark text-white font-semibold text-sm px-6 py-2.5 rounded hover:bg-forest-mid transition-colors"
                >
                  Continue
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => navigate("/login")}
                  className="bg-forest-dark text-white font-semibold text-sm px-6 py-2.5 rounded hover:bg-forest-mid transition-colors"
                >
                  Continue to login
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
