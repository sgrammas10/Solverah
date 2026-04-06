import { FormEvent, useId } from "react";
import { API_BASE } from "../../utils/api";

const inputCls =
  "w-full rounded border border-cream-muted bg-cream-base px-3 py-2.5 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-forest-light focus:outline-none focus:ring-2 focus:ring-forest-pale transition-colors";

type FormData = {
  firstName: string;
  lastName: string;
  email: string;
  state: string;
  phone: string;
  linkedinUrl: string;
  portfolioUrl: string;
};

type Props = {
  formData: FormData;
  onInputChange: (field: keyof FormData, value: string) => void;
  privacyConsent: boolean;
  setPrivacyConsent: (v: boolean) => void;
  infoOptIn: boolean;
  setInfoOptIn: (v: boolean) => void;
  resumeFile: File | null;
  setResumeFile: (f: File | null) => void;
  selectedFileName: string;
  setSelectedFileName: (s: string) => void;
  submissionStatus: "idle" | "submitting" | "success" | "error";
  errorMessage: string;
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
};

export default function IntakeForm({
  formData,
  onInputChange,
  privacyConsent,
  setPrivacyConsent,
  infoOptIn,
  setInfoOptIn,
  resumeFile,
  setResumeFile,
  selectedFileName,
  setSelectedFileName,
  submissionStatus,
  errorMessage,
  onSubmit,
}: Props) {
  const firstNameId = useId();
  const lastNameId = useId();
  const emailId = useId();
  const stateId = useId();
  const phoneId = useId();
  const linkedinId = useId();
  const portfolioId = useId();
  const resumeId = useId();
  const privacyConsentId = useId();
  const infoOptInId = useId();

  return (
    <div id="waitlist" className="animate-fade-up-slower opacity-0">
      <div className="border border-cream-muted rounded-xl bg-white p-8">
        <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">
          Early Access
        </p>
        <h2 className="font-display text-[1.75rem] font-semibold text-ink-primary leading-snug mb-2">
          Join the Solverah signal
        </h2>
        <p className="text-sm text-ink-secondary leading-relaxed mb-6">
          Private intake for thoughtful collaborators. Resumes upload to secure storage; we store only what you choose to share.
        </p>

        <form className="space-y-5" onSubmit={onSubmit}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label htmlFor={firstNameId} className="text-sm font-medium text-ink-primary">First name</label>
              <input
                id={firstNameId}
                type="text"
                placeholder="Your first name"
                autoComplete="given-name"
                value={formData.firstName}
                onChange={(e) => onInputChange("firstName", e.target.value)}
                required
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
                onChange={(e) => onInputChange("lastName", e.target.value)}
                required
                className={inputCls}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label htmlFor={emailId} className="text-sm font-medium text-ink-primary">Email</label>
            <input
              id={emailId}
              type="email"
              placeholder="you@example.com"
              autoComplete="email"
              value={formData.email}
              onChange={(e) => onInputChange("email", e.target.value)}
              required
              className={inputCls}
            />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label htmlFor={stateId} className="text-sm font-medium text-ink-primary">State / region</label>
              <input
                id={stateId}
                type="text"
                placeholder="Where are you based?"
                autoComplete="address-level1"
                value={formData.state}
                onChange={(e) => onInputChange("state", e.target.value)}
                required
                className={inputCls}
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor={phoneId} className="text-sm font-medium text-ink-primary">
                Phone <span className="text-ink-tertiary font-normal">(optional)</span>
              </label>
              <input
                id={phoneId}
                type="tel"
                placeholder="(555) 555-5555"
                autoComplete="tel"
                value={formData.phone}
                onChange={(e) => onInputChange("phone", e.target.value)}
                className={inputCls}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label htmlFor={linkedinId} className="text-sm font-medium text-ink-primary">
                LinkedIn <span className="text-ink-tertiary font-normal">(optional)</span>
              </label>
              <input
                id={linkedinId}
                type="url"
                placeholder="linkedin.com/in/you"
                value={formData.linkedinUrl}
                onChange={(e) => onInputChange("linkedinUrl", e.target.value)}
                className={inputCls}
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor={portfolioId} className="text-sm font-medium text-ink-primary">
                Portfolio <span className="text-ink-tertiary font-normal">(optional)</span>
              </label>
              <input
                id={portfolioId}
                type="url"
                placeholder="your-site.com"
                value={formData.portfolioUrl}
                onChange={(e) => onInputChange("portfolioUrl", e.target.value)}
                className={inputCls}
              />
            </div>
          </div>

          {/* Resume upload */}
          <div className="space-y-1.5">
            <label htmlFor={resumeId} className="text-sm font-medium text-ink-primary">
              Resume <span className="text-forest-light text-xs">(PDF or DOCX — required)</span>
            </label>
            <div className="rounded border border-dashed border-cream-muted bg-cream-base p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm font-medium text-ink-primary">Upload your resume</p>
                  <p className="text-xs text-ink-tertiary mt-0.5">
                    We read for context, not to score you. Your file stays private.
                  </p>
                  {selectedFileName && (
                    <div className="mt-1.5 flex items-center gap-2">
                      <p className="text-xs text-forest-mid font-medium">{selectedFileName}</p>
                      <button
                        type="button"
                        aria-label="Remove file"
                        className="ml-1 rounded-full bg-red-100 hover:bg-red-200 text-red-600 px-2 py-0.5 text-xs font-bold focus:outline-none focus:ring-2 focus:ring-red-400"
                        onClick={() => { setResumeFile(null); setSelectedFileName(""); }}
                      >
                        ×
                      </button>
                    </div>
                  )}
                </div>
                <label className="inline-flex cursor-pointer items-center justify-center gap-2 bg-forest-dark text-white text-sm font-semibold px-4 py-2 rounded hover:bg-forest-mid transition-colors shrink-0">
                  Choose file
                  <input
                    id={resumeId}
                    type="file"
                    accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    className="hidden"
                    required
                    onChange={(e) => {
                      const f = e.target.files?.[0] ?? null;
                      setResumeFile(f);
                      setSelectedFileName(f?.name ?? "");
                    }}
                  />
                </label>
              </div>
            </div>
          </div>

          {/* Consent checkboxes */}
          <label
            htmlFor={privacyConsentId}
            className="flex items-start gap-3 rounded border border-cream-muted bg-cream-base px-4 py-3 text-xs text-ink-secondary cursor-pointer hover:border-forest-pale transition-colors"
          >
            <input
              id={privacyConsentId}
              type="checkbox"
              checked={privacyConsent}
              onChange={(e) => setPrivacyConsent(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-cream-muted text-forest-mid focus:ring-forest-pale"
            />
            <span>
              I consent to Solverah securely storing my resume and contact information for early access review.
            </span>
          </label>

          <label
            htmlFor={infoOptInId}
            className="flex items-start gap-3 rounded border border-cream-muted bg-cream-base px-4 py-3 text-xs text-ink-secondary cursor-pointer hover:border-forest-pale transition-colors"
          >
            <input
              id={infoOptInId}
              type="checkbox"
              checked={infoOptIn}
              onChange={(e) => setInfoOptIn(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-cream-muted text-forest-mid focus:ring-forest-pale"
            />
            <span>I want more information about how Solverah can help me.</span>
          </label>

          <button
            type="submit"
            disabled={submissionStatus === "submitting"}
            className="w-full bg-forest-dark text-white font-semibold text-base py-3.5 rounded hover:bg-forest-mid transition-colors disabled:opacity-60 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-forest-light focus-visible:ring-offset-2"
          >
            {submissionStatus === "submitting" ? "Submitting…" : "Begin setting up my account"}
          </button>

          {submissionStatus === "success" && (
            <p className="rounded bg-forest-pale px-3 py-2 text-sm text-forest-dark font-medium">
              Thanks — your submission was received.
            </p>
          )}
          {submissionStatus === "error" && (
            <p className="rounded bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
              {errorMessage || "We couldn't save this right now. Please try again in a moment."}
            </p>
          )}

          {!API_BASE && (
            <p className="text-[11px] text-ink-tertiary">
              Dev note: set <span className="font-semibold">VITE_API_URL</span> to enable submissions.
            </p>
          )}
        </form>
      </div>
    </div>
  );
}
