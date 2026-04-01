import { FormEvent, useId, useState } from "react";
import { X } from "lucide-react";
import { API_BASE } from "../utils/api";
import { useAuth } from "../contexts/useAuth";

type Step = "prompt" | "form" | "success";

type Props = {
  open: boolean;
  hasIntakeSubmission: boolean;
  onClose: () => void;
  onSuccess: () => void;
};

const inputCls =
  "w-full rounded-lg border border-cream-muted bg-cream-base px-3.5 py-2.5 text-sm text-ink-primary placeholder:text-ink-tertiary focus:outline-none focus:ring-2 focus:ring-forest-pale focus:border-forest-light transition-colors";

export default function IntakePromptModal({ open, hasIntakeSubmission, onClose, onSuccess }: Props) {
  const { fetchWithAuth, user } = useAuth();

  const [step, setStep] = useState<Step>("prompt");
  const [formData, setFormData] = useState({
    firstName: user?.name?.split(" ")[0] ?? "",
    lastName: user?.name?.split(" ").slice(1).join(" ") ?? "",
    state: "",
    phone: "",
    linkedinUrl: "",
    portfolioUrl: "",
  });
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [selectedFileName, setSelectedFileName] = useState("");
  const [privacyConsent, setPrivacyConsent] = useState(false);
  const [infoOptIn, setInfoOptIn] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const firstNameId = useId();
  const lastNameId = useId();
  const stateId = useId();
  const phoneId = useId();
  const linkedinId = useId();
  const portfolioId = useId();
  const resumeId = useId();
  const privacyConsentId = useId();
  const infoOptInId = useId();

  const handleChange = (field: keyof typeof formData, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError("");

    const firstName = formData.firstName.trim();
    const lastName = formData.lastName.trim();
    const state = formData.state.trim();

    if (!firstName || !lastName) { setError("Please enter your name."); return; }
    if (!state) { setError("Please enter your state / region."); return; }
    if (!resumeFile) { setError("Please attach your resume to continue."); return; }
    if (!privacyConsent) { setError("Please agree to the privacy notice to continue."); return; }

    setSubmitting(true);
    try {
      // Step 1: get presigned upload URL
      const presignRes = await fetch(`${API_BASE}/intake/presign`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mime: resumeFile.type, size: resumeFile.size }),
      });
      const presignData = await presignRes.json().catch(() => ({}));
      if (!presignRes.ok) throw new Error(presignData?.error || "Unable to start upload.");

      const { submission_id, object_key, upload_url } = presignData as {
        submission_id: string;
        object_key: string;
        upload_url: string;
      };

      // Step 2: upload resume directly to S3
      const putRes = await fetch(upload_url, {
        method: "PUT",
        headers: { "Content-Type": resumeFile.type },
        body: resumeFile,
      });
      if (!putRes.ok) throw new Error("Resume upload failed. Please try again.");

      // Step 3: finalize and link to account
      await fetchWithAuth("/intake/link-account", {
        method: "POST",
        body: JSON.stringify({
          submission_id,
          object_key,
          mime: resumeFile.type,
          size: resumeFile.size,
          first_name: firstName,
          last_name: lastName,
          state,
          phone: formData.phone.trim() || null,
          linkedin_url: formData.linkedinUrl.trim() || null,
          portfolio_url: formData.portfolioUrl.trim() || null,
          privacy_consent: privacyConsent,
          info_opt_in: infoOptIn,
        }),
      });

      setStep("success");
    } catch (err: any) {
      setError(err?.message || "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      <div className="absolute inset-0 bg-ink-primary/50" onClick={onClose} />

      <div className="relative z-10 w-full max-w-lg bg-white rounded-2xl shadow-2xl overflow-hidden max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-start justify-between px-6 pt-6 pb-4 shrink-0">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-1">
              Profile Autofill
            </p>
            <h2 className="font-display text-xl font-bold text-ink-primary">
              {step === "success"
                ? "You're all set!"
                : step === "form"
                ? "Join the Solverah signal"
                : hasIntakeSubmission
                ? "Your profile needs attention"
                : "Boost your profile instantly"}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="ml-4 p-1.5 rounded-lg text-ink-tertiary hover:text-ink-primary hover:bg-cream-subtle transition-colors shrink-0"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto px-6 pb-6 flex-1">
          {step === "prompt" && hasIntakeSubmission && (
            <div className="space-y-5">
              <p className="text-sm text-ink-secondary leading-relaxed">
                Your profile is still incomplete. Head to your profile page to fill in the remaining details and improve your job matches.
              </p>
              <div className="rounded-xl border border-cream-muted bg-cream-base p-4 space-y-2 text-sm text-ink-secondary">
                <p className="font-medium text-ink-primary">Sections to complete:</p>
                <ul className="list-disc list-inside space-y-1 text-xs">
                  <li>Work experience and job history</li>
                  <li>Education details</li>
                  <li>Skills and expertise</li>
                  <li>Professional summary</li>
                </ul>
              </div>
              <div className="flex flex-col sm:flex-row gap-3">
                <button
                  type="button"
                  onClick={() => setStep("form")}
                  className="flex-1 bg-forest-dark text-white text-sm font-semibold px-5 py-2.5 rounded-lg hover:bg-forest-mid transition-colors"
                >
                  Get started →
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  className="flex-1 border border-cream-muted text-ink-secondary text-sm font-medium px-5 py-2.5 rounded-lg hover:bg-cream-subtle transition-colors"
                >
                  Maybe later
                </button>
              </div>
            </div>
          )}

          {step === "prompt" && !hasIntakeSubmission && (
            <div className="space-y-5">
              <p className="text-sm text-ink-secondary leading-relaxed">
                Fill out the Solverah Signal form and we'll automatically populate your profile with your resume, experience, and contact details — no manual entry needed.
              </p>
              <div className="rounded-xl border border-cream-muted bg-cream-base p-4 space-y-2 text-sm text-ink-secondary">
                <p className="font-medium text-ink-primary">What gets filled in:</p>
                <ul className="list-disc list-inside space-y-1 text-xs">
                  <li>Name, location, and contact info</li>
                  <li>Work experience parsed from your resume</li>
                  <li>Education and skills</li>
                  <li>LinkedIn and portfolio links</li>
                </ul>
              </div>
              <div className="flex flex-col sm:flex-row gap-3">
                <button
                  type="button"
                  onClick={() => setStep("form")}
                  className="flex-1 bg-forest-dark text-white text-sm font-semibold px-5 py-2.5 rounded-lg hover:bg-forest-mid transition-colors"
                >
                  Get started →
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  className="flex-1 border border-cream-muted text-ink-secondary text-sm font-medium px-5 py-2.5 rounded-lg hover:bg-cream-subtle transition-colors"
                >
                  Maybe later
                </button>
              </div>
            </div>
          )}

          {step === "form" && (
            <form className="space-y-4" onSubmit={handleSubmit}>
              <p className="text-sm text-ink-secondary leading-relaxed -mt-1">
                Private intake for thoughtful collaborators. Resumes upload to secure storage; we store only what you choose to share.
              </p>

              {/* Name */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <label htmlFor={firstNameId} className="text-sm font-medium text-ink-primary">First name</label>
                  <input
                    id={firstNameId}
                    type="text"
                    placeholder="Your first name"
                    autoComplete="given-name"
                    value={formData.firstName}
                    onChange={(e) => handleChange("firstName", e.target.value)}
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
                    onChange={(e) => handleChange("lastName", e.target.value)}
                    required
                    className={inputCls}
                  />
                </div>
              </div>

              {/* State + Phone */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <label htmlFor={stateId} className="text-sm font-medium text-ink-primary">State / region</label>
                  <input
                    id={stateId}
                    type="text"
                    placeholder="Where are you based?"
                    autoComplete="address-level1"
                    value={formData.state}
                    onChange={(e) => handleChange("state", e.target.value)}
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
                    onChange={(e) => handleChange("phone", e.target.value)}
                    className={inputCls}
                  />
                </div>
              </div>

              {/* LinkedIn + Portfolio */}
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
                    onChange={(e) => handleChange("linkedinUrl", e.target.value)}
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
                    onChange={(e) => handleChange("portfolioUrl", e.target.value)}
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
                      <p className="text-xs text-ink-tertiary mt-0.5">We read for context, not to score you. Your file stays private.</p>
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

              {/* Privacy consent */}
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
                <span>I consent to Solverah securely storing my resume and contact information for early access review.</span>
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

              {error && (
                <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2.5">
                  {error}
                </p>
              )}

              <div className="flex flex-col sm:flex-row gap-3 pt-1">
                <button
                  type="submit"
                  disabled={submitting}
                  className="flex-1 bg-forest-dark text-white text-sm font-semibold px-5 py-2.5 rounded-lg hover:bg-forest-mid transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {submitting ? "Submitting…" : "Submit & autofill profile"}
                </button>
                <button
                  type="button"
                  onClick={() => setStep("prompt")}
                  disabled={submitting}
                  className="flex-1 border border-cream-muted text-ink-secondary text-sm font-medium px-5 py-2.5 rounded-lg hover:bg-cream-subtle transition-colors disabled:opacity-60"
                >
                  Back
                </button>
              </div>
            </form>
          )}

          {step === "success" && (
            <div className="space-y-5 text-center py-4">
              <div className="mx-auto w-12 h-12 rounded-full bg-forest-pale flex items-center justify-center">
                <svg className="w-6 h-6 text-forest-mid" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <div>
                <p className="font-semibold text-ink-primary mb-1">Profile autofill complete!</p>
                <p className="text-sm text-ink-secondary">
                  Your resume has been processed and your profile has been updated with the extracted information.
                </p>
              </div>
              <button
                type="button"
                onClick={onSuccess}
                className="w-full bg-forest-dark text-white text-sm font-semibold px-5 py-2.5 rounded-lg hover:bg-forest-mid transition-colors"
              >
                View my profile →
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
