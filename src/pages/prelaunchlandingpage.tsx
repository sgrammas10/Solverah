import React, { FormEvent, useEffect, useId, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { API_BASE } from "../utils/api";
import HeroNetworkAnimation from "../components/HeroNetworkAnimation";

type SubmissionStatus = "idle" | "submitting" | "success" | "error";

const ALLOWED_MIME = new Set<string>([
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

function PrelaunchLandingPage() {
  const [formData, setFormData] = useState({
    firstName: "",
    lastName: "",
    email: "",
    state: "",
    phone: "",
    linkedinUrl: "",
    portfolioUrl: "",
  });
  const [privacyConsent, setPrivacyConsent] = useState(false);
  const [infoOptIn, setInfoOptIn] = useState(false);

  const [isEarlyAccessOpen, setIsEarlyAccessOpen] = useState(false);
  const [earlyAccessData, setEarlyAccessData] = useState({
    firstName: "",
    lastName: "",
    email: "",
    phone: "",
    preferredContact: "email",
    careerJourney: "",
  });

  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [selectedFileName, setSelectedFileName] = useState<string>("");
  const [submissionStatus, setSubmissionStatus] = useState<SubmissionStatus>("idle");
  const [errorMessage, setErrorMessage] = useState("");

  const [submissionId, setSubmissionId] = useState<string | null>(null);
  const [submissionEmail, setSubmissionEmail] = useState("");
  const [accountModalOpen, setAccountModalOpen] = useState(false);
  const [accountStep, setAccountStep] = useState<"prompt" | "form" | "signin" | "success">("prompt");
  const [accountAction, setAccountAction] = useState<"create" | "signin">("create");
  const [signInEmail, setSignInEmail] = useState("");
  const [signInPassword, setSignInPassword] = useState("");
  const [accountPassword, setAccountPassword] = useState("");
  const [accountConfirm, setAccountConfirm] = useState("");
  const [accountError, setAccountError] = useState("");
  const [isCreatingAccount, setIsCreatingAccount] = useState(false);
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const navigate = useNavigate();

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
  const earlyFirstNameId = useId();
  const earlyLastNameId = useId();
  const earlyEmailId = useId();
  const earlyPhoneId = useId();
  const earlyContactId = useId();
  const earlyJourneyId = useId();

  const handleInputChange = (field: keyof typeof formData, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleEarlyAccessChange = (field: keyof typeof earlyAccessData, value: string) => {
    setEarlyAccessData((prev) => ({ ...prev, [field]: value }));
  };

  const faqs = useMemo(
    () => [
      {
        q: "What is Authentic Intelligence?",
        a: "Authentic Intelligence is Solverah's approach to generating insights that respect human complexity. It uses structured frameworks, rules-based logic, and automated analysis to surface patterns about how people work and where environments support or create friction.",
      },
      {
        q: "Is this the same as artificial intelligence?",
        a: "It may use automated systems and AI-supported techniques, but it isn't designed to replace human judgment. It supports reflection and understanding — not decisions.",
      },
      {
        q: "What information does it use?",
        a: "Only what you choose to provide — responses, career background, and optional uploads. It may also use contextual information about roles or environments to generate insights.",
      },
      {
        q: "Does it make career or employment decisions?",
        a: "No. Solverah does not make hiring, promotion, compensation, or career decisions. Insights are advisory and interpretive. Final decisions remain with you or your organization.",
      },
      {
        q: "Are the insights personalized?",
        a: "Yes — they reflect the factors you provide and how they interact. But personalization is not prediction. Insights describe patterns and possibilities, not outcomes.",
      },
      {
        q: "Why focus on conditions instead of labels?",
        a: "Because environments matter. Solverah emphasizes conditions, fit, and context so insights stay humane, flexible, and useful across situations.",
      },
    ],
    [],
  );

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 60);
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    if (!isEarlyAccessOpen && !accountModalOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (isEarlyAccessOpen) setIsEarlyAccessOpen(false);
      if (accountModalOpen) setAccountModalOpen(false);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [accountModalOpen, isEarlyAccessOpen]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmissionStatus("submitting");
    setErrorMessage("");

    try {
      const firstName = formData.firstName.trim();
      const lastName = formData.lastName.trim();
      const email = formData.email.trim();
      const state = formData.state.trim();
      const linkedinUrl = formData.linkedinUrl.trim();

      if (!firstName || !lastName) throw new Error("Please enter your name.");
      if (!email) throw new Error("Please enter your email.");
      if (!state) throw new Error("Please enter your state / region.");
      if (!privacyConsent) throw new Error("Please agree to the privacy notice to continue.");

      const hasResume = !!resumeFile;
      if (!hasResume) throw new Error("Please attach your resume to continue.");

      if (linkedinUrl.length > 0) {
        try {
          new URL(linkedinUrl);
        } catch {
          throw new Error("Please enter a valid LinkedIn URL.");
        }
      }

      let submission_id: string | null = null;
      let object_key: string | null = null;
      let mime: string | null = null;
      let size: number | null = null;

      if (resumeFile) {
        const presignRes = await fetch(`${API_BASE}/intake/presign`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mime: resumeFile.type, size: resumeFile.size }),
        });

        const presignData = await presignRes.json().catch(() => ({}));
        if (!presignRes.ok) throw new Error(presignData?.error || "Unable to start upload.");

        ({ submission_id, object_key } = presignData as { submission_id: string; object_key: string });
        setSubmissionId(submission_id);
        const { upload_url } = presignData as { upload_url: string };

        if (!submission_id || !object_key || !upload_url) {
          throw new Error("Upload initialization failed. Please try again.");
        }

        const putRes = await fetch(upload_url, {
          method: "PUT",
          headers: { "Content-Type": resumeFile.type },
          body: resumeFile,
        });
        if (!putRes.ok) throw new Error("Upload failed. Please try again.");

        mime = resumeFile.type;
        size = resumeFile.size;
      }

      const finalizePayload = {
        submission_id,
        object_key,
        mime,
        size,
        first_name: firstName,
        last_name: lastName,
        email,
        state,
        phone: formData.phone.trim() || null,
        linkedin_url: linkedinUrl || null,
        portfolio_url: formData.portfolioUrl.trim() || null,
        privacy_consent: privacyConsent,
        info_opt_in: infoOptIn,
      };

      const finalizeRes = await fetch(`${API_BASE}/intake/finalize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(finalizePayload),
      });

      const finalizeData = await finalizeRes.json().catch(() => ({}));
      if (!finalizeRes.ok) throw new Error(finalizeData?.error || "Unable to submit right now.");

      setSubmissionStatus("success");
      setAccountModalOpen(true);
      setAccountStep("prompt");
      setAccountAction("create");
      setAccountError("");
      setSubmissionEmail(email);
      setSignInEmail(email);
      setSignInPassword("");
      setAccountPassword("");
      setAccountConfirm("");
      setFormData({ firstName: "", lastName: "", email: "", state: "", phone: "", linkedinUrl: "", portfolioUrl: "" });
      setPrivacyConsent(false);
      setInfoOptIn(false);
      setResumeFile(null);
      setSelectedFileName("");
    } catch (error) {
      setSubmissionStatus("error");
      setErrorMessage(error instanceof Error ? error.message : "Unable to submit right now. Please try again.");
    }
  };

  const handleCreateAccount = async () => {
    if (!submissionId) {
      setAccountError("We couldn't find your submission ID. Please resubmit the form.");
      return;
    }
    if (!accountPassword || accountPassword.length < 8) {
      setAccountError("Please choose a password with at least 8 characters.");
      return;
    }
    if (accountPassword !== accountConfirm) {
      setAccountError("Passwords do not match.");
      return;
    }

    setIsCreatingAccount(true);
    setAccountAction("create");
    setAccountError("");

    try {
      const response = await fetch(`${API_BASE}/intake/create-account`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ submission_id: submissionId, password: accountPassword, role: "job-seeker" }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data?.error || "Unable to create account right now.");
      setAccountStep("success");
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : "Unable to create account right now.");
    } finally {
      setIsCreatingAccount(false);
    }
  };

  const handleSignInExisting = async () => {
    if (!submissionId) {
      setAccountError("We couldn't find your submission ID. Please resubmit the form.");
      return;
    }
    if (!signInEmail.trim()) {
      setAccountError("Please enter the email used on your submission.");
      return;
    }
    if (!signInPassword) {
      setAccountError("Please enter your password.");
      return;
    }

    setIsSigningIn(true);
    setAccountAction("signin");
    setAccountError("");

    try {
      const response = await fetch(`${API_BASE}/intake/sign-in`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ submission_id: submissionId, email: signInEmail.trim(), password: signInPassword }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data?.error || "Unable to sign in right now.");
      setAccountStep("success");
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : "Unable to sign in right now.");
    } finally {
      setIsSigningIn(false);
    }
  };

  // Shared input class
  const inputCls =
    "w-full rounded border border-cream-muted bg-cream-base px-3 py-2.5 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-forest-light focus:outline-none focus:ring-2 focus:ring-forest-pale transition-colors";


  return (
    <div className="min-h-screen bg-cream-base font-sans text-ink-primary">
      {/* Skip to main */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-[100] focus:bg-forest-dark focus:text-white focus:px-4 focus:py-2 focus:rounded"
      >
        Skip to main content
      </a>

      {/* ─── NAVIGATION ─── */}
      <header
        className="sticky top-0 z-50 transition-all duration-300"
        style={{
          backgroundColor: scrolled ? "rgba(250,247,242,0.92)" : "transparent",
          backdropFilter: scrolled ? "blur(12px)" : "none",
          borderBottom: scrolled ? "1px solid #D4CFC8" : "1px solid transparent",
        }}
      >
        <div className="mx-auto max-w-7xl px-6 h-16 flex items-center justify-between">
          {/* Logo */}
          <a href="/" className="font-display text-2xl font-bold text-forest-dark tracking-tight">
            Solverah
          </a>

          {/* Desktop Nav */}
          <nav className="hidden md:flex items-center gap-8" aria-label="Primary navigation">
            {[
              { label: "How it works", href: "#features" },
              { label: "About", href: "#about" },
              { label: "FAQ", href: "#faq" },
            ].map(({ label, href }) => (
              <a
                key={label}
                href={href}
                className="text-[15px] font-medium text-ink-primary tracking-[0.02em] relative after:absolute after:bottom-0 after:left-0 after:h-[2px] after:w-0 after:bg-forest-light after:transition-all after:duration-300 hover:after:w-full hover:text-forest-mid transition-colors"
              >
                {label}
              </a>
            ))}
          </nav>

          {/* Desktop CTAs */}
          <div className="hidden md:flex items-center gap-3">
            <a
              href="/login"
              className="text-[15px] font-medium text-ink-primary px-4 py-2 rounded hover:text-forest-mid transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-forest-light focus-visible:ring-offset-2"
            >
              Sign In
            </a>
            <a
              href="/register"
              className="bg-forest-dark text-white font-semibold text-[15px] px-6 py-2.5 rounded hover:bg-forest-mid transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-forest-light focus-visible:ring-offset-2"
            >
              Get Started
            </a>
          </div>

          {/* Mobile hamburger */}
          <button
            type="button"
            aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
            onClick={() => setMobileMenuOpen((v) => !v)}
            className="md:hidden flex flex-col gap-1.5 p-2"
          >
            <span className={`block h-0.5 w-6 bg-ink-primary transition-transform duration-200 ${mobileMenuOpen ? "translate-y-2 rotate-45" : ""}`} />
            <span className={`block h-0.5 w-6 bg-ink-primary transition-opacity duration-200 ${mobileMenuOpen ? "opacity-0" : ""}`} />
            <span className={`block h-0.5 w-6 bg-ink-primary transition-transform duration-200 ${mobileMenuOpen ? "-translate-y-2 -rotate-45" : ""}`} />
          </button>
        </div>

        {/* Mobile menu */}
        {mobileMenuOpen && (
          <div className="md:hidden bg-cream-base border-t border-cream-muted px-6 py-6 space-y-4 animate-fade-in">
            {[
              { label: "How it works", href: "#features" },
              { label: "About", href: "#about" },
              { label: "FAQ", href: "#faq" },
            ].map(({ label, href }) => (
              <a
                key={label}
                href={href}
                onClick={() => setMobileMenuOpen(false)}
                className="block text-base font-medium text-ink-primary hover:text-forest-mid transition-colors"
              >
                {label}
              </a>
            ))}
            <a
              href="/login"
              className="block text-base font-medium text-ink-primary hover:text-forest-mid transition-colors"
            >
              Sign In
            </a>
            <a
              href="/register"
              onClick={() => setMobileMenuOpen(false)}
              className="block w-full bg-forest-dark text-white font-semibold text-sm px-6 py-3 rounded hover:bg-forest-mid transition-colors text-center"
            >
              Get Started
            </a>
          </div>
        )}
      </header>

      <main id="main">
        {/* ─── HERO ─── */}
        <section className="bg-cream-base" style={{ minHeight: "88vh", paddingTop: "80px", paddingBottom: "80px" }}>
          <div className="mx-auto max-w-7xl px-6">
            <div className="grid grid-cols-1 gap-12 lg:grid-cols-[55fr_45fr] lg:gap-16 items-center">

              {/* LEFT — Copy */}
              <div className="space-y-8">
                <span className="inline-block text-xs font-semibold uppercase tracking-[0.08em] bg-forest-pale text-forest-mid px-3 py-1 rounded animate-fade-up opacity-0">
                  AI-Native Career Platform
                </span>
                <h1 className="font-display text-[clamp(2.5rem,5vw,4.5rem)] font-bold leading-[1.1] text-ink-primary max-w-[640px] animate-fade-up-slow opacity-0">
                  Modern careers deserve more than keywords.
                </h1>
                <p className="text-[clamp(1rem,2vw,1.25rem)] leading-relaxed text-ink-secondary max-w-[520px] animate-fade-up-slower opacity-0">
                  Solverah blends structured frameworks with Authentic Intelligence to understand how you actually work — and where you're built to thrive.
                </p>
                <div className="flex flex-wrap gap-3 animate-fade-up-slower opacity-0">
                  {[
                    "Early preview",
                    "Human-led evaluation",
                  ].map((badge) => (
                    <span
                      key={badge}
                      className="text-sm text-ink-secondary border border-cream-muted rounded-full px-4 py-1.5"
                    >
                      {badge}
                    </span>
                  ))}
                </div>
                <div className="flex flex-wrap items-center gap-4 animate-fade-up-slower opacity-0">
                  <button
                    type="button"
                    onClick={() => setIsEarlyAccessOpen(true)}
                    className="bg-forest-dark text-white font-semibold text-base px-7 py-3.5 rounded hover:bg-forest-mid transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-forest-light focus-visible:ring-offset-2"
                  >
                    Request early access
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate("/quiz-preview")}
                    className="border-2 border-forest-dark text-forest-dark font-semibold text-base px-7 py-3.5 rounded hover:bg-forest-pale transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-forest-light focus-visible:ring-offset-2"
                  >
                    Preview what you'll unlock
                  </button>
                  <a
                    href="#features"
                    className="text-sm font-semibold text-forest-mid hover:underline underline-offset-4 transition-colors"
                  >
                    See how it works
                  </a>
                </div>
              </div>

              {/* RIGHT — Intake Form */}
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

                  <form className="space-y-5" onSubmit={handleSubmit}>
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                      <div className="space-y-1.5">
                        <label htmlFor={firstNameId} className="text-sm font-medium text-ink-primary">
                          First name
                        </label>
                        <input
                          id={firstNameId}
                          type="text"
                          placeholder="Your first name"
                          autoComplete="given-name"
                          value={formData.firstName}
                          onChange={(e) => handleInputChange("firstName", e.target.value)}
                          required
                          className={inputCls}
                        />
                      </div>
                      <div className="space-y-1.5">
                        <label htmlFor={lastNameId} className="text-sm font-medium text-ink-primary">
                          Last name
                        </label>
                        <input
                          id={lastNameId}
                          type="text"
                          placeholder="Your last name"
                          autoComplete="family-name"
                          value={formData.lastName}
                          onChange={(e) => handleInputChange("lastName", e.target.value)}
                          required
                          className={inputCls}
                        />
                      </div>
                    </div>

                    <div className="space-y-1.5">
                      <label htmlFor={emailId} className="text-sm font-medium text-ink-primary">
                        Email
                      </label>
                      <input
                        id={emailId}
                        type="email"
                        placeholder="you@example.com"
                        autoComplete="email"
                        value={formData.email}
                        onChange={(e) => handleInputChange("email", e.target.value)}
                        required
                        className={inputCls}
                      />
                    </div>

                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                      <div className="space-y-1.5">
                        <label htmlFor={stateId} className="text-sm font-medium text-ink-primary">
                          State / region
                        </label>
                        <input
                          id={stateId}
                          type="text"
                          placeholder="Where are you based?"
                          autoComplete="address-level1"
                          value={formData.state}
                          onChange={(e) => handleInputChange("state", e.target.value)}
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
                          onChange={(e) => handleInputChange("phone", e.target.value)}
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
                          onChange={(e) => handleInputChange("linkedinUrl", e.target.value)}
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
                          onChange={(e) => handleInputChange("portfolioUrl", e.target.value)}
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
                                <p className="text-xs text-forest-mid font-medium">
                                  {selectedFileName}
                                </p>
                                <button
                                  type="button"
                                  aria-label="Remove file"
                                  className="ml-1 rounded-full bg-red-100 hover:bg-red-200 text-red-600 px-2 py-0.5 text-xs font-bold focus:outline-none focus:ring-2 focus:ring-red-400"
                                  onClick={() => {
                                    setResumeFile(null);
                                    setSelectedFileName("");
                                  }}
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
            </div>
          </div>
        </section>

        {/* ─── STATS BAR ─── */}
        <section className="bg-cream-subtle border-y border-cream-muted">
          <div className="mx-auto max-w-7xl px-6 py-12">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-8 sm:gap-0 sm:divide-x sm:divide-cream-muted">
              {[
                { stat: "Human-Led", label: "Every submission reviewed by a person, not an algorithm" },
                { stat: "Context-First", label: "We read your full picture, not just your last title" },
                { stat: "Private by Default", label: "Your data is yours — shared only with your consent" },
              ].map(({ stat, label }) => (
                <div key={stat} className="flex flex-col items-center text-center sm:px-8">
                  <span className="font-display text-3xl font-bold text-forest-dark mb-2">{stat}</span>
                  <span className="text-sm text-ink-secondary leading-relaxed max-w-[200px]">{label}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── FEATURES (BENTO) ─── */}
        <section id="features" className="relative overflow-hidden bg-cream-base py-24 px-6">
          <HeroNetworkAnimation theme="light" />
          <div className="relative z-10 mx-auto max-w-7xl">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-3">
              What We Offer
            </p>
            <h2 className="font-display text-[clamp(2rem,4vw,2.75rem)] font-bold text-ink-primary mb-12 max-w-[480px] leading-snug">
              Built around how people actually grow.
            </h2>

            {/* Bento grid */}
            <div className="grid grid-cols-1 md:grid-cols-6 gap-4 auto-rows-auto">
              {/* Card A — large hero, spans col 1-4, row 1-3 */}
              <div
                className="md:col-span-4 md:row-span-2 border border-cream-muted rounded-xl bg-white p-8 flex flex-col justify-between group hover:border-forest-light transition-colors"
                style={{ minHeight: "320px" }}
              >
                <div>
                  <span className="inline-block text-[11px] font-semibold uppercase tracking-[0.08em] bg-forest-pale text-forest-mid px-2.5 py-1 rounded mb-5">
                    Core Experience
                  </span>
                  <h3 className="font-display text-[1.75rem] font-semibold text-ink-primary leading-snug mb-3 max-w-[420px]">
                    Matching built around how you actually work
                  </h3>
                  <p className="text-base text-ink-secondary leading-relaxed max-w-[420px]">
                    Solverah reads beyond job titles and buzzwords to understand your work style, values, and the environments where you genuinely thrive. Your story has more signal than your keyword count.
                  </p>
                </div>
                 <a href="#how-it-works" className="mt-8 flex items-center gap-2 text-sm font-semibold text-forest-mid hover:underline underline-offset-4">
                  <span>Learn how it works</span>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="transition-transform group-hover:translate-x-1" aria-hidden="true">
                    <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </a>

              </div>

              {/* Card B — medium top-right */}
              <div className="md:col-span-2 border border-cream-muted rounded-xl bg-white p-6 group hover:border-forest-light transition-colors">
                <span className="inline-block text-[11px] font-semibold uppercase tracking-[0.08em] bg-forest-pale text-forest-mid px-2.5 py-1 rounded mb-4">
                  AI-Native
                </span>
                <h3 className="font-display text-[1.25rem] font-semibold text-ink-primary leading-snug mb-2">
                  Authentic Intelligence
                </h3>
                <p className="text-sm text-ink-secondary leading-relaxed">
                  Structured frameworks, not black-box scores. Insights that describe patterns and possibilities — not predictions about your worth.
                </p>
              </div>

              {/* Card C — small bottom-right */}
              <div className="md:col-span-1 border border-cream-muted rounded-xl bg-forest-pale p-5 group hover:border-forest-light transition-colors">
                <span className="inline-block text-[11px] font-semibold uppercase tracking-[0.08em] text-forest-mid mb-3">
                  Privacy
                </span>
                <h3 className="font-display text-[1.1rem] font-semibold text-ink-primary leading-snug mb-2">
                  Private by default
                </h3>
                <p className="text-xs text-ink-secondary leading-relaxed">
                  You control what's shared. We store only what you choose to provide.
                </p>
              </div>

              {/* Card D — small accent */}
              <div className="md:col-span-1 border border-cream-muted rounded-xl bg-forest-dark p-5 group">
                <span className="inline-block text-[11px] font-semibold uppercase tracking-[0.08em] text-forest-pale mb-3">
                  Philosophy
                </span>
                <h3 className="font-display text-[1.1rem] font-semibold text-white leading-snug mb-2">
                  Context before automation
                </h3>
                <p className="text-xs text-forest-pale leading-relaxed">
                  Human review pairs with every insight we generate.
                </p>
              </div>

              {/* Card E — medium, spans col 5-6 bottom */}
              <div className="md:col-span-2 border border-cream-muted rounded-xl bg-white p-6 group hover:border-forest-light transition-colors">
                <span className="inline-block text-[11px] font-semibold uppercase tracking-[0.08em] bg-forest-pale text-forest-mid px-2.5 py-1 rounded mb-4">
                  Approach
                </span>
                <h3 className="font-display text-[1.25rem] font-semibold text-ink-primary leading-snug mb-2">
                  Conditions over labels
                </h3>
                <p className="text-sm text-ink-secondary leading-relaxed">
                  Environments shape outcomes. We look at fit, context, and conditions — not just your last job title.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ─── HOW IT WORKS ─── */}
        <section id="how-it-works" className="bg-cream-subtle border-t border-cream-muted py-24 px-6">
          <div className="mx-auto max-w-7xl">
            <div className="text-center max-w-[600px] mx-auto mb-16 space-y-4">
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light">
                The Process
              </p>
              <h2 className="font-display text-[clamp(2rem,4vw,2.75rem)] font-bold text-ink-primary leading-snug">
                From your story to actionable insight.
              </h2>
              <p className="text-base text-ink-secondary leading-relaxed">
                Solverah doesn't score you against a template. It reads the full picture of how you work — and surfaces what that actually means for where you'll thrive.
              </p>
            </div>

            {/* Steps */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-16">
              {[
                {
                  step: "01",
                  title: "You share your context",
                  body: "Your resume, background, and optionally your LinkedIn or portfolio. We ask only for what's useful — nothing extraneous.",
                  accent: "bg-forest-pale",
                },
                {
                  step: "02",
                  title: "Structured frameworks map your signal",
                  body: "Our system applies a layered set of frameworks to translate unstructured career history into meaningful, comparable dimensions. The logic is rules-based and reproducible.",
                  accent: "bg-forest-pale",
                },
                {
                  step: "03",
                  title: "Patterns are identified, not invented",
                  body: "We surface what the information already suggests — about your work style, environment preferences, and the conditions where your contributions tend to compound.",
                  accent: "bg-forest-pale",
                },
                {
                  step: "04",
                  title: "A human reviews before anything reaches you",
                  body: "Every insight set is reviewed by a person before delivery. Automated analysis is a starting point — editorial judgment is the finish line.",
                  accent: "bg-forest-dark",
                },
              ].map(({ step, title, body, accent }) => (
                <div key={step} className="relative rounded-xl border border-cream-muted bg-white p-6 hover:border-forest-light transition-colors flex flex-col gap-4">
                  <span className={`inline-flex items-center justify-center w-9 h-9 rounded-full ${accent} font-display text-sm font-bold ${accent === "bg-forest-dark" ? "text-white" : "text-forest-mid"} shrink-0`}>
                    {step}
                  </span>
                  <div>
                    <h3 className="font-display text-[1.05rem] font-semibold text-ink-primary leading-snug mb-2">{title}</h3>
                    <p className="text-sm text-ink-secondary leading-relaxed">{body}</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Principle callouts */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {[
                {
                  label: "What we look at",
                  content: "Work history, scope of responsibility, environment signals, and the conditions that appear when people do their best work — not personality labels or trait scores.",
                },
                {
                  label: "What we don't do",
                  content: "We don't assign you a type, a tier, or a numeric score. We don't compare you to a benchmark or rank you against other candidates. Insights describe — they don't decide.",
                },
                {
                  label: "Why this matters",
                  content: "Most career tools optimize for searchability. Solverah optimizes for understanding. The difference is whether the system works for you — or for whoever is searching a database.",
                },
              ].map(({ label, content }) => (
                <div key={label} className="rounded-xl border border-cream-muted bg-white p-6">
                  <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-3">{label}</p>
                  <p className="text-sm text-ink-secondary leading-relaxed">{content}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── ABOUT ─── */}
        <section id="about" className="bg-cream-subtle border-t border-cream-muted py-24 px-6">
          <div className="mx-auto max-w-7xl">
            <div className="grid gap-12 lg:grid-cols-2 lg:gap-20 items-start">
              <div className="space-y-5">
                <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light">
                  Why Solverah
                </p>
                <h2 className="font-display text-[clamp(2rem,4vw,2.75rem)] font-bold text-ink-primary leading-snug">
                  Career intelligence that stays human.
                </h2>
                <p className="text-base text-ink-secondary leading-relaxed max-w-[540px]">
                  Solverah reads beyond job titles and buzzwords to understand how you work, what you value, and where you thrive. Authentic Intelligence keeps judgment with humans while giving structure to discovery.
                </p>
                <div className="grid gap-3 sm:grid-cols-2 pt-2">
                  {[
                    { title: "Context before automation", body: "Thoughtful patterns and editorial clarity — not speed-optimized sorting." },
                    { title: "Signals over scores", body: "What makes you effective matters more than a numeric ranking." },
                    { title: "Careful by design", body: "Built to support reflection and understanding, not replace it." },
                    { title: "Private by default", body: "Responsible handling of every detail you choose to share." },
                  ].map(({ title, body }) => (
                    <div key={title} className="rounded-lg border border-cream-muted bg-white p-4 hover:border-forest-pale transition-colors">
                      <p className="text-sm font-semibold text-ink-primary mb-1">{title}</p>
                      <p className="text-sm text-ink-secondary leading-relaxed">{body}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-cream-muted bg-white p-8 space-y-5">
                <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light">
                  Prelaunch status
                </p>
                <h3 className="font-display text-[1.5rem] font-semibold text-ink-primary">
                  Early intake is live
                </h3>
                <p className="text-sm text-ink-secondary leading-relaxed">
                  The broader platform remains gated while we learn. You should know what's happening with your data and why.
                </p>
                <div className="space-y-4 pt-1">
                  {[
                    { color: "bg-forest-light", text: "Soft-launch intake only. No production accounts or feeds are available." },
                    { color: "bg-forest-mid", text: "Manual review of submissions while we tune Authentic Intelligence with real context." },
                    { color: "bg-forest-pale border border-forest-light", text: "Clear Insights. You should feel informed, not pushed." },
                  ].map(({ color, text }, i) => (
                    <div key={i} className="flex items-start gap-3">
                      <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${color}`} />
                      <p className="text-sm text-ink-secondary leading-relaxed">{text}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ─── FAQ ─── */}
        <section id="faq" className="relative overflow-hidden bg-cream-base py-24 px-6">
          <HeroNetworkAnimation theme="light" />
          <div className="relative z-10 mx-auto max-w-7xl">
            <div className="grid gap-12 lg:grid-cols-[1fr_2fr] lg:gap-20 items-start">
              <div className="space-y-4 lg:sticky lg:top-24">
                <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light">
                  Questions we hear
                </p>
                <h2 className="font-display text-[clamp(1.75rem,3vw,2.25rem)] font-bold text-ink-primary leading-snug">
                  A brief FAQ for early collaborators
                </h2>
                <p className="text-sm text-ink-secondary leading-relaxed">
                  Straightforward answers so you know how Solverah works at this stage. If something feels unclear, tell us.
                </p>
              </div>

              <div className="grid gap-4">
                {faqs.map((item) => (
                  <div
                    key={item.q}
                    className="rounded-lg border border-cream-muted bg-white p-5 hover:border-forest-pale transition-colors"
                  >
                    <p className="text-sm font-semibold text-ink-primary mb-2">{item.q}</p>
                    <p className="text-sm text-ink-secondary leading-relaxed">{item.a}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ─── CTA SECTION ─── */}
        <section className="bg-forest-dark py-24 px-6">
          <div className="mx-auto max-w-4xl text-center space-y-6">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-pale">
              Ready to be seen differently
            </p>
            <h2 className="font-display text-[clamp(2rem,4vw,3rem)] font-bold text-white leading-snug">
              Your career is more than your last job title.
            </h2>
            <p className="text-lg text-forest-pale leading-relaxed max-w-[520px] mx-auto">
              Join the early cohort. Share your story, and let us find the conditions where you do your best work.
            </p>
            <div className="flex flex-wrap items-center justify-center gap-4 pt-2">
              <button
                type="button"
                onClick={() => setIsEarlyAccessOpen(true)}
                className="bg-white text-forest-dark font-semibold text-base px-8 py-4 rounded hover:bg-cream-subtle transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-forest-dark"
              >
                Request early access
              </button>
              <a
                href="#waitlist"
                className="border border-white/30 text-white font-semibold text-base px-8 py-4 rounded hover:bg-white/10 transition-colors"
              >
                Submit your intake now
              </a>
            </div>
          </div>
        </section>
      </main>

      {/* ─── FOOTER ─── */}
      <footer className="bg-ink-primary text-white">
        <div className="mx-auto max-w-7xl px-6 py-16">
          <div className="grid grid-cols-1 gap-10 sm:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-3">
              <span className="font-display text-2xl font-bold text-white">Solverah</span>
              <p className="text-sm text-[#AAA] leading-relaxed max-w-[200px]">
                Human-centered career intelligence for the people who deserve better.
              </p>
            </div>
            <div className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[#888]">Navigate</p>
              {[
                { label: "How it works", href: "#features" },
                { label: "About", href: "#about" },
                { label: "FAQ", href: "#faq" },
              ].map(({ label, href }) => (
                <a key={label} href={href} className="block text-sm text-[#AAA] hover:text-white transition-colors leading-relaxed">
                  {label}
                </a>
              ))}
            </div>
            <div className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[#888]">Join</p>
              <button
                type="button"
                onClick={() => setIsEarlyAccessOpen(true)}
                className="block text-sm text-[#AAA] hover:text-white transition-colors leading-relaxed text-left"
              >
                Request early access
              </button>
              <button
                type="button"
                onClick={() => navigate("/quiz-preview")}
                className="block text-sm text-[#AAA] hover:text-white transition-colors leading-relaxed text-left"
              >
                Preview the platform
              </button>
            </div>
            <div className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[#888]">Status</p>
              <p className="text-sm text-[#AAA] leading-relaxed">
                Soft launch — broader access remains closed. Early cohort intake is open.
              </p>
            </div>
          </div>
        </div>
        <div className="border-t border-white/10">
          <div className="mx-auto max-w-7xl px-6 py-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <p className="text-xs text-[#888]">
              © {new Date().getFullYear()} Solverah. All rights reserved.
            </p>
            <div className="flex gap-6">
              <a href="#" className="text-xs text-[#888] hover:text-white transition-colors">Privacy Policy</a>
              <a href="#" className="text-xs text-[#888] hover:text-white transition-colors">Terms</a>
            </div>
          </div>
        </div>
      </footer>

      {/* ─── EARLY ACCESS MODAL ─── */}
      {isEarlyAccessOpen && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto px-4 py-6 sm:py-10">
          <div
            className="absolute inset-0 bg-ink-primary/60 backdrop-blur-sm"
            onClick={() => setIsEarlyAccessOpen(false)}
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
                onClick={() => setIsEarlyAccessOpen(false)}
                className="shrink-0 h-8 w-8 flex items-center justify-center rounded border border-cream-muted text-ink-secondary hover:border-forest-pale hover:text-forest-mid transition-colors"
                aria-label="Close modal"
              >
                ✕
              </button>
            </div>

            <form className="space-y-5">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <label htmlFor={earlyFirstNameId} className="text-sm font-medium text-ink-primary">First name</label>
                  <input
                    id={earlyFirstNameId}
                    type="text"
                    placeholder="Your first name"
                    autoComplete="given-name"
                    value={earlyAccessData.firstName}
                    onChange={(e) => handleEarlyAccessChange("firstName", e.target.value)}
                    className={inputCls}
                  />
                </div>
                <div className="space-y-1.5">
                  <label htmlFor={earlyLastNameId} className="text-sm font-medium text-ink-primary">Last name</label>
                  <input
                    id={earlyLastNameId}
                    type="text"
                    placeholder="Your last name"
                    autoComplete="family-name"
                    value={earlyAccessData.lastName}
                    onChange={(e) => handleEarlyAccessChange("lastName", e.target.value)}
                    className={inputCls}
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <label htmlFor={earlyEmailId} className="text-sm font-medium text-ink-primary">Email</label>
                  <input
                    id={earlyEmailId}
                    type="email"
                    placeholder="you@example.com"
                    autoComplete="email"
                    value={earlyAccessData.email}
                    onChange={(e) => handleEarlyAccessChange("email", e.target.value)}
                    className={inputCls}
                  />
                </div>
                <div className="space-y-1.5">
                  <label htmlFor={earlyPhoneId} className="text-sm font-medium text-ink-primary">Phone</label>
                  <input
                    id={earlyPhoneId}
                    type="tel"
                    placeholder="(555) 555-5555"
                    autoComplete="tel"
                    value={earlyAccessData.phone}
                    onChange={(e) => handleEarlyAccessChange("phone", e.target.value)}
                    className={inputCls}
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label htmlFor={earlyContactId} className="text-sm font-medium text-ink-primary">
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
                        id={option.value === "email" ? earlyContactId : undefined}
                        type="radio"
                        name="preferred-contact"
                        value={option.value}
                        checked={earlyAccessData.preferredContact === option.value}
                        onChange={(e) => handleEarlyAccessChange("preferredContact", e.target.value)}
                        className="h-4 w-4 border-cream-muted text-forest-mid focus:ring-forest-pale"
                      />
                      {option.label}
                    </label>
                  ))}
                </div>
              </div>

              <div className="space-y-1.5">
                <label htmlFor={earlyJourneyId} className="text-sm font-medium text-ink-primary">
                  Career journey and what you want next
                </label>
                <textarea
                  id={earlyJourneyId}
                  placeholder="Share your path so far, and the kinds of roles or environments you're hoping to find."
                  value={earlyAccessData.careerJourney}
                  onChange={(e) => handleEarlyAccessChange("careerJourney", e.target.value)}
                  rows={4}
                  className={inputCls}
                />
              </div>

              <div className="flex flex-wrap items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsEarlyAccessOpen(false)}
                  className="px-5 py-2.5 text-sm font-semibold text-ink-secondary border border-cream-muted rounded hover:border-forest-pale transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="bg-forest-dark text-white font-semibold text-sm px-6 py-2.5 rounded hover:bg-forest-mid transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-forest-light focus-visible:ring-offset-2"
                >
                  Send request
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ─── ACCOUNT MODAL ─── */}
      {accountModalOpen && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto px-4 py-6 sm:py-10">
          <div
            className="absolute inset-0 bg-ink-primary/60 backdrop-blur-sm"
            onClick={() => setAccountModalOpen(false)}
            aria-hidden="true"
          />
          <div className="relative w-full max-w-lg max-h-[calc(100vh-3rem)] overflow-y-auto rounded-xl border border-cream-muted bg-cream-base p-8 shadow-2xl animate-fade-in">
            <button
              type="button"
              aria-label="Close"
              onClick={() => setAccountModalOpen(false)}
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

            {accountStep === "prompt" && (
              <div className="mt-6 space-y-4">
                <div className="rounded border border-cream-muted bg-white p-4 text-sm text-ink-secondary leading-relaxed">
                  We'll populate your personal info, work experience, skills, and education using the resume you shared.
                </div>
                <div className="flex flex-wrap items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => { setAccountStep("signin"); setAccountError(""); setSignInEmail(submissionEmail); setSignInPassword(""); }}
                    className="px-5 py-2.5 text-sm font-semibold text-forest-mid border border-forest-pale rounded hover:bg-forest-pale transition-colors"
                  >
                    Sign in
                  </button>
                  <button
                    type="button"
                    onClick={() => setAccountStep("form")}
                    className="bg-forest-dark text-white font-semibold text-sm px-6 py-2.5 rounded hover:bg-forest-mid transition-colors"
                  >
                    Create account
                  </button>
                </div>
              </div>
            )}

            {accountStep === "form" && (
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
                {accountError && (
                  <p className="rounded bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
                    {accountError}
                  </p>
                )}
                <div className="flex flex-wrap items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setAccountStep("prompt")}
                    className="px-5 py-2.5 text-sm font-semibold text-ink-secondary border border-cream-muted rounded hover:border-forest-pale transition-colors"
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    disabled={isCreatingAccount}
                    onClick={handleCreateAccount}
                    className="bg-forest-dark text-white font-semibold text-sm px-6 py-2.5 rounded hover:bg-forest-mid transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {isCreatingAccount ? "Creating…" : "Create account"}
                  </button>
                </div>
              </div>
            )}

            {accountStep === "signin" && (
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
                {accountError && (
                  <p className="rounded bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
                    {accountError}
                  </p>
                )}
                <div className="flex flex-wrap items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setAccountStep("prompt")}
                    className="px-5 py-2.5 text-sm font-semibold text-ink-secondary border border-cream-muted rounded hover:border-forest-pale transition-colors"
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    disabled={isSigningIn}
                    onClick={handleSignInExisting}
                    className="bg-forest-dark text-white font-semibold text-sm px-6 py-2.5 rounded hover:bg-forest-mid transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {isSigningIn ? "Signing in…" : "Sign in"}
                  </button>
                </div>
              </div>
            )}

            {accountStep === "success" && (
              <div className="mt-6 space-y-4">
                <div className="rounded bg-forest-pale border border-forest-pale px-4 py-3 text-sm text-forest-dark font-medium">
                  {accountAction === "signin"
                    ? "Signed in! Your profile has been updated from your intake submission."
                    : "Account created! Your profile has been filled in from your resume."}
                </div>
                <div className="flex flex-wrap items-center justify-end gap-3">
                  {accountAction === "signin" ? (
                    <button
                      type="button"
                      onClick={() => setAccountModalOpen(false)}
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
      )}
    </div>
  );
}

export default PrelaunchLandingPage;
