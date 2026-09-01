import { useId } from "react";

const inputCls =
  "w-full rounded border border-cream-muted bg-cream-base px-3 py-2.5 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-forest-light focus:outline-none focus:ring-2 focus:ring-forest-pale transition-colors";

type FormData = {
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  preferredContact: string;
  careerJourney: string;
};

type Props = {
  isOpen: boolean;
  onClose: () => void;
  isSuccess: boolean;
  onDismissSuccess: () => void;
  formData: FormData;
  onChange: (field: keyof FormData, value: string) => void;
  isSubmitting: boolean;
  error: string;
  onSubmit: () => void;
};

export default function EarlyAccessModal({
  isOpen,
  onClose,
  isSuccess,
  onDismissSuccess,
  formData,
  onChange,
  isSubmitting,
  error,
  onSubmit,
}: Props) {
  const firstNameId = useId();
  const lastNameId = useId();
  const emailId = useId();
  const phoneId = useId();
  const contactId = useId();
  const journeyId = useId();

  return (
    <>
      {/* Early Access Modal */}
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto px-4 py-6 sm:py-10">
          <div
            className="absolute inset-0 bg-ink-primary/60 backdrop-blur-sm"
            onClick={onClose}
            aria-hidden="true"
          />
          <div className="relative w-full max-w-2xl max-h-[calc(100vh-3rem)] overflow-y-auto rounded-xl border border-cream-muted bg-cream-base p-8 shadow-2xl animate-fade-in">
            <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">
                  Request early access
                </p>
                <h3 className="font-display text-2xl font-semibold text-ink-primary">
                  Tell us how you want to connect
                </h3>
                <p className="mt-2 text-sm text-ink-secondary leading-relaxed">
                  We'll keep it personal. Share your journey and how you'd like to hear from us.
                </p>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="shrink-0 h-8 w-8 flex items-center justify-center rounded border border-cream-muted text-ink-secondary hover:border-forest-pale hover:text-forest-mid transition-colors"
                aria-label="Close modal"
              >
                ✕
              </button>
            </div>

            <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); onSubmit(); }}>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <label htmlFor={firstNameId} className="text-sm font-medium text-ink-primary">First name</label>
                  <input
                    id={firstNameId}
                    type="text"
                    placeholder="Your first name"
                    autoComplete="given-name"
                    value={formData.firstName}
                    onChange={(e) => onChange("firstName", e.target.value)}
                    className={inputCls}
                  />
                </div>
                <div className="space-y-1.5">
                  <label htmlFor={lastNameId} className="text-sm font-medium text-ink-primary">Last name</label>
                  <input
                    id={lastNameId}
                    type="text"
                    placeholder="Your last name"
                    autoComplete="family-name"
                    value={formData.lastName}
                    onChange={(e) => onChange("lastName", e.target.value)}
                    className={inputCls}
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <label htmlFor={emailId} className="text-sm font-medium text-ink-primary">Email</label>
                  <input
                    id={emailId}
                    type="email"
                    placeholder="you@example.com"
                    autoComplete="email"
                    value={formData.email}
                    onChange={(e) => onChange("email", e.target.value)}
                    className={inputCls}
                  />
                </div>
                <div className="space-y-1.5">
                  <label htmlFor={phoneId} className="text-sm font-medium text-ink-primary">Phone</label>
                  <input
                    id={phoneId}
                    type="tel"
                    placeholder="(555) 555-5555"
                    autoComplete="tel"
                    value={formData.phone}
                    onChange={(e) => onChange("phone", e.target.value)}
                    className={inputCls}
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label htmlFor={contactId} className="text-sm font-medium text-ink-primary">
                  Preferred contact method
                </label>
                <div className="grid gap-3 sm:grid-cols-3">
                  {[
                    { value: "email", label: "Email" },
                    { value: "text", label: "Text" },
                    { value: "call", label: "Call" },
                  ].map((option) => (
                    <label
                      key={option.value}
                      className="flex cursor-pointer items-center gap-2 rounded border border-cream-muted bg-white px-3 py-2.5 text-sm text-ink-primary hover:border-forest-pale transition-colors"
                    >
                      <input
                        id={option.value === "email" ? contactId : undefined}
                        type="radio"
                        name="preferred-contact"
                        value={option.value}
                        checked={formData.preferredContact === option.value}
                        onChange={(e) => onChange("preferredContact", e.target.value)}
                        className="h-4 w-4 border-cream-muted text-forest-mid focus:ring-forest-pale"
                      />
                      {option.label}
                    </label>
                  ))}
                </div>
              </div>

              <div className="space-y-1.5">
                <label htmlFor={journeyId} className="text-sm font-medium text-ink-primary">
                  Career journey and what you want next
                </label>
                <textarea
                  id={journeyId}
                  placeholder="Share your path so far, and the kinds of roles or environments you're hoping to find."
                  value={formData.careerJourney}
                  onChange={(e) => onChange("careerJourney", e.target.value)}
                  rows={4}
                  className={inputCls}
                />
              </div>

              {error && (
                <p className="rounded bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">{error}</p>
              )}

              <div className="flex flex-wrap items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-5 py-2.5 text-sm font-semibold text-ink-secondary border border-cream-muted rounded hover:border-forest-pale transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="bg-forest-dark text-white font-semibold text-sm px-6 py-2.5 rounded hover:bg-forest-mid transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-forest-light focus-visible:ring-offset-2 disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {isSubmitting ? "Sending..." : "Send request"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Success overlay */}
      {isSuccess && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
          <div
            className="absolute inset-0 bg-ink-primary/60 backdrop-blur-sm"
            onClick={onDismissSuccess}
            aria-hidden="true"
          />
          <div className="relative z-10 w-full max-w-md rounded-2xl bg-white p-10 text-center shadow-2xl">
            <div className="mb-4 flex items-center justify-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-forest-pale">
                <svg className="h-8 w-8 text-forest-dark" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
            </div>
            <h2 className="mb-2 text-2xl font-bold text-ink-primary">Request received!</h2>
            <p className="mb-6 text-ink-secondary">
              Thanks for your interest in Solverah. We'll be in touch soon.
            </p>
            <button
              onClick={onDismissSuccess}
              className="rounded-lg bg-forest-dark px-8 py-3 font-semibold text-white hover:bg-forest-mid transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </>
  );
}
