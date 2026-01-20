import React, { FormEvent, useId, useMemo, useState } from "react";

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

  const firstNameId = useId();
  const lastNameId = useId();
  const emailId = useId();
  const stateId = useId();
  const phoneId = useId();
  const linkedinId = useId();
  const portfolioId = useId();
  const resumeId = useId();
  const earlyFirstNameId = useId();
  const earlyLastNameId = useId();
  const earlyEmailId = useId();
  const earlyPhoneId = useId();
  const earlyContactId = useId();
  const earlyJourneyId = useId();

  const API_BASE = (import.meta as any).env?.VITE_API_URL ?? "";

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
        a: "Authentic Intelligence is Solverah’s approach to generating insights that respect human complexity. It uses structured frameworks, rules-based logic, and automated analysis to surface patterns about how people work and where environments support or create friction.",
      },
      {
        q: "Is this the same as artificial intelligence?",
        a: "It may use automated systems and AI-supported techniques, but it isn’t designed to replace human judgment. It supports reflection and understanding — not decisions.",
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

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmissionStatus("submitting");
    setErrorMessage("");

    try {
      // Basic client-side validation
      const firstName = formData.firstName.trim();
      const lastName = formData.lastName.trim();
      const email = formData.email.trim();
      const state = formData.state.trim();
      const linkedinUrl = formData.linkedinUrl.trim();

      if (!firstName || !lastName) throw new Error("Please enter your name.");
      if (!email) throw new Error("Please enter your email.");
      if (!state) throw new Error("Please enter your state / region.");

      // NEW: require at least one of LinkedIn or Resume
      const hasLinkedIn = linkedinUrl.length > 0;
      const hasResume = !!resumeFile;
      if (!hasLinkedIn && !hasResume) {
        throw new Error("Please provide either a LinkedIn URL or attach a resume (at least one is required).");
      }

      // Optional: if LinkedIn provided, ensure it's a valid URL
      if (hasLinkedIn) {
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
        // 1) Presign
        const presignRes = await fetch(`${API_BASE}/api/intake/presign`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mime: resumeFile.type, size: resumeFile.size }),
        });

        const presignData = await presignRes.json().catch(() => ({}));
        if (!presignRes.ok) throw new Error(presignData?.error || "Unable to start upload.");

        ({ submission_id, object_key } = presignData as { submission_id: string; object_key: string });
        const { upload_url } = presignData as { upload_url: string };

        if (!submission_id || !object_key || !upload_url) {
          throw new Error("Upload initialization failed. Please try again.");
        }

        // 2) PUT upload
        const putRes = await fetch(upload_url, {
          method: "PUT",
          headers: { "Content-Type": resumeFile.type },
          body: resumeFile,
        });
        if (!putRes.ok) throw new Error("Upload failed. Please try again.");

        mime = resumeFile.type;
        size = resumeFile.size;
      }

      // 3) Finalize
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
      };

      const finalizeRes = await fetch(`${API_BASE}/api/intake/finalize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(finalizePayload),
      });

      const finalizeData = await finalizeRes.json().catch(() => ({}));
      if (!finalizeRes.ok) {
        throw new Error(finalizeData?.error || "Unable to submit right now.");
      }

      setSubmissionStatus("success");
      setFormData({
        firstName: "",
        lastName: "",
        email: "",
        state: "",
        phone: "",
        linkedinUrl: "",
        portfolioUrl: "",
      });
      setResumeFile(null);
      setSelectedFileName("");
    } catch (error) {
      setSubmissionStatus("error");
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Unable to submit right now. Please try again.",
      );
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* HERO */}
      <div className="relative isolate overflow-hidden bg-gradient-to-br from-emerald-600/30 via-blue-700/20 to-indigo-800/30">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(16,185,129,0.18),_transparent_45%),radial-gradient(circle_at_bottom_right,_rgba(59,130,246,0.18),_transparent_45%)]" />
        <div className="absolute inset-y-0 right-10 w-72 rounded-full bg-emerald-400/10 blur-3xl" />

        <div className="relative mx-auto max-w-6xl px-6 pb-16 pt-14 lg:pt-20">
          <div className="flex items-center justify-between gap-6">
            <div className="flex items-center gap-3">
              <span className="inline-flex items-center rounded-full bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-emerald-200 ring-1 ring-white/15">
                Prelaunch
              </span>
              <div className="h-px flex-1 bg-gradient-to-r from-emerald-300/60 via-slate-100/30 to-transparent" />
            </div>
            <p className="text-xs text-slate-200/80">Private build · Access by invitation only</p>
          </div>

          <div className="grid gap-12 lg:grid-cols-12 lg:gap-16 pt-10 lg:pt-14">
            <div className="lg:col-span-7 space-y-6">
              <div className="space-y-4">
                <p className="text-sm font-semibold text-emerald-200 tracking-[0.08em] uppercase">
                  Solverah
                </p>
                <h1 className="text-3xl sm:text-4xl lg:text-5xl font-semibold leading-tight text-slate-50">
                  Modern careers deserve more than keywords. We’re building human-centered matching grounded in lived experience.
                </h1>
                <p className="text-lg text-slate-200/85 max-w-3xl">
                  Solverah blends structured frameworks with Authentic Intelligence to understand how people actually work — and how environments help them thrive.
                </p>
              </div>

              <div className="flex flex-wrap gap-3 text-sm text-slate-200/90">
                <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1">
                  <span className="h-2 w-2 rounded-full bg-emerald-300" /> Early preview
                </span>
                <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1">
                  <span className="h-2 w-2 rounded-full bg-blue-300" /> No accounts or onboarding
                </span>
                <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1">
                  <span className="h-2 w-2 rounded-full bg-indigo-300" /> Human-led evaluation
                </span>
              </div>

              <div className="flex flex-wrap items-center gap-4">
                <button
                  type="button"
                  onClick={() => setIsEarlyAccessOpen(true)}
                  className="rounded-full bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 px-6 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-emerald-500/20 transition hover:shadow-emerald-400/25"
                >
                  Request early access
                </button>
                <a
                  href="#about"
                  className="text-sm font-semibold text-emerald-100/90 underline-offset-8 hover:underline"
                >
                  Learn more
                </a>
              </div>
            </div>

            {/* FORM CARD */}
            <div className="lg:col-span-5" id="waitlist">
              <div className="rounded-2xl border border-white/10 bg-slate-900/70 p-6 shadow-2xl shadow-black/40 backdrop-blur">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.14em] text-emerald-200">Early Access</p>
                    <h2 className="text-xl font-semibold text-white">Join the Solverah signal</h2>
                    <p className="mt-1 text-sm text-slate-200/80">
                      Private intake for thoughtful collaborators. Resumes upload directly to secure storage; we store only what you choose to share.
                    </p>
                  </div>
                  {/*<div className="h-12 w-12 rounded-full bg-gradient-to-tr from-emerald-400 to-blue-500 text-slate-950 flex items-center justify-center text-lg font-bold">
                    S
                  </div>*/}
                </div>

                <form className="mt-6 space-y-6" onSubmit={handleSubmit}>
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div className="space-y-2">
                      <label htmlFor={firstNameId} className="text-sm font-medium text-slate-100">
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
                        className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-400 focus:border-emerald-300/70 focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                      />
                    </div>
                    <div className="space-y-2">
                      <label htmlFor={lastNameId} className="text-sm font-medium text-slate-100">
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
                        className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-400 focus:border-emerald-300/70 focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label htmlFor={emailId} className="text-sm font-medium text-slate-100">
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
                      className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-400 focus:border-emerald-300/70 focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                    />
                  </div>

                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div className="space-y-2">
                      <label htmlFor={stateId} className="text-sm font-medium text-slate-100">
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
                        className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-400 focus:border-emerald-300/70 focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                      />
                    </div>
                    <div className="space-y-2">
                      <label htmlFor={phoneId} className="text-sm font-medium text-slate-100">
                        Phone (optional)
                      </label>
                      <input
                        id={phoneId}
                        type="tel"
                        placeholder="(555) 555-5555"
                        autoComplete="tel"
                        value={formData.phone}
                        onChange={(e) => handleInputChange("phone", e.target.value)}
                        className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-400 focus:border-emerald-300/70 focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div className="space-y-2">
                      <label htmlFor={linkedinId} className="text-sm font-medium text-slate-100">
                        LinkedIn (optional)
                      </label>
                      <input
                        id={linkedinId}
                        type="url"
                        placeholder="https://www.linkedin.com/in/you"
                        value={formData.linkedinUrl}
                        onChange={(e) => handleInputChange("linkedinUrl", e.target.value)}
                        className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-400 focus:border-emerald-300/70 focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                      />
                    </div>
                    <div className="space-y-2">
                      <label htmlFor={portfolioId} className="text-sm font-medium text-slate-100">
                        Personal site / portfolio (optional)
                      </label>
                      <input
                        id={portfolioId}
                        type="url"
                        placeholder="https://your-site.com"
                        value={formData.portfolioUrl}
                        onChange={(e) => handleInputChange("portfolioUrl", e.target.value)}
                        className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-400 focus:border-emerald-300/70 focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label htmlFor={resumeId} className="text-sm font-medium text-slate-100">
                      Resume (PDF or DOCX)
                    </label>
                    <div className="rounded-lg border border-dashed border-white/15 bg-white/5 p-4">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                        <div>
                          <p className="text-sm font-medium text-white">Upload your resume</p>
                          <p className="text-xs text-slate-200/75">
                            We read for context, not to score you. Your file stays private.
                          </p>
                          {selectedFileName ? (
                            <p className="mt-2 text-sm text-emerald-100">
                              Selected: <span className="font-semibold">{selectedFileName}</span>
                            </p>
                          ) : null}
                        </div>
                        <label className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-full bg-emerald-400/90 px-4 py-2 text-sm font-semibold text-slate-950 shadow-md shadow-emerald-500/30 transition hover:bg-emerald-300">
                          Choose file
                          <input
                            id={resumeId}
                            type="file"
                            accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                            className="hidden"
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

                  <button
                    type="submit"
                    disabled={submissionStatus === "submitting"}
                    className="w-full rounded-full bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 px-5 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-emerald-500/25 transition hover:shadow-emerald-400/30 disabled:cursor-not-allowed disabled:opacity-70"
                  >
                    {submissionStatus === "submitting" ? "Submitting..." : "Request early access"}
                  </button>

                  <div className="space-y-2 text-xs text-slate-200/80">
                    <p>No instant accounts. We’ll reach out if the early cohort is a fit.</p>
                    {submissionStatus === "success" && (
                      <p className="rounded-md bg-emerald-400/10 p-2 text-emerald-50 ring-1 ring-emerald-300/30">
                        Thanks — your submission was received.
                      </p>
                    )}
                    {submissionStatus === "error" && (
                      <p className="rounded-md bg-red-500/10 p-2 text-red-100 ring-1 ring-red-500/30">
                        We couldn’t save this right now. {errorMessage || "Please try again in a moment."}
                      </p>
                    )}
                  </div>

                  {/* Small note if API base isn't configured (helps you debug without breaking build) */}
                  {!API_BASE ? (
                    <p className="text-[11px] text-slate-300/70">
                      Dev note: set <span className="font-semibold">VITE_API_URL</span> to your Render backend URL for submissions to work.
                    </p>
                  ) : null}
                </form>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ABOUT */}
      <div id="about" className="mx-auto max-w-6xl px-6 py-14 lg:py-20">
        <div className="grid gap-12 lg:grid-cols-12 lg:items-start">
          <div className="lg:col-span-7 space-y-4">
            <p className="text-sm font-semibold uppercase tracking-[0.14em] text-emerald-300">Why Solverah</p>
            <h2 className="text-2xl sm:text-3xl font-semibold text-white">Career intelligence that stays human.</h2>
            <p className="text-base text-slate-200/85 max-w-3xl">
              Solverah reads beyond job titles and buzzwords to understand how you work, what you value, and where you thrive. Authentic Intelligence keeps judgment with humans while giving structure to discovery.
            </p>
            <div className="grid gap-4 sm:grid-cols-2">
              {["Context before automation", "Signals over scores", "Careful by design", "Private by default"].map(
                (item) => (
                  <div
                    key={item}
                    className="rounded-xl border border-white/10 bg-slate-900/60 p-4 shadow-lg shadow-black/30"
                  >
                    <p className="text-sm font-semibold text-white">{item}</p>
                    <p className="mt-2 text-sm text-slate-200/80">
                      Thoughtful patterns, editorial clarity, and responsible handling of the details you choose to share.
                    </p>
                  </div>
                ),
              )}
            </div>
          </div>

          <div className="lg:col-span-5 space-y-5 rounded-2xl border border-white/10 bg-white/5 p-6 shadow-2xl shadow-black/30">
            <p className="text-sm font-semibold uppercase tracking-[0.14em] text-emerald-300">Prelaunch status</p>
            <h3 className="text-xl font-semibold text-white">Early intake is live</h3>
            <p className="text-sm text-slate-200/80">
              The broader platform remains gated while we learn. You should know what’s happening with your data and why.
            </p>
            <div className="space-y-3 text-sm text-slate-200/85">
              <div className="flex items-start gap-3">
                <span className="mt-1 h-2.5 w-2.5 rounded-full bg-emerald-300" />
                <p>Soft-launch intake only. No production accounts or feeds are available.</p>
              </div>
              <div className="flex items-start gap-3">
                <span className="mt-1 h-2.5 w-2.5 rounded-full bg-blue-300" />
                <p>Manual review of submissions while we tune Authentic Intelligence with real context.</p>
              </div>
              <div className="flex items-start gap-3">
                <span className="mt-1 h-2.5 w-2.5 rounded-full bg-indigo-300" />
                <p>Clear copy over glossy UI. You should feel informed, not pushed.</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* FAQ */}
      <div className="mx-auto max-w-6xl px-6 pb-14">
        <div className="rounded-2xl border border-white/10 bg-slate-900/70 p-8 shadow-2xl shadow-black/40">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-2xl space-y-3">
              <p className="text-sm font-semibold uppercase tracking-[0.14em] text-emerald-300">Questions we hear</p>
              <h3 className="text-2xl font-semibold text-white">A brief FAQ for early collaborators</h3>
              <p className="text-sm text-slate-200/80">
                Straightforward answers so you know how Solverah works at this stage. If something feels unclear, tell us.
              </p>
            </div>
            <div className="grid w-full gap-4 lg:max-w-xl">
              {faqs.map((item) => (
                <div key={item.q} className="rounded-xl border border-white/10 bg-white/5 p-4">
                  <p className="text-sm font-semibold text-white">{item.q}</p>
                  <p className="mt-2 text-sm text-slate-200/80">{item.a}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <footer className="border-t border-white/10 bg-slate-950/80 py-6 text-center text-xs text-slate-400">
        © {new Date().getFullYear()} Solverah. Soft launch — broader access remains closed.
      </footer>
      {isEarlyAccessOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4 py-10">
          <div
            className="absolute inset-0 bg-slate-950/70 backdrop-blur-sm"
            onClick={() => setIsEarlyAccessOpen(false)}
          />
          <div className="relative w-full max-w-2xl rounded-2xl border border-white/10 bg-slate-900/90 p-6 shadow-2xl shadow-black/50">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.14em] text-emerald-200">Request early access</p>
                <h3 className="text-2xl font-semibold text-white">Tell us how you want to connect</h3>
                <p className="mt-2 text-sm text-slate-200/80">
                  We’ll keep it personal. Share your journey and how you’d like to hear from us.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsEarlyAccessOpen(false)}
                className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold text-slate-200 transition hover:border-emerald-300/60 hover:text-emerald-100"
              >
                Close
              </button>
            </div>

            <form className="mt-6 space-y-5">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <label htmlFor={earlyFirstNameId} className="text-sm font-medium text-slate-100">
                    First name
                  </label>
                  <input
                    id={earlyFirstNameId}
                    type="text"
                    placeholder="Your first name"
                    autoComplete="given-name"
                    value={earlyAccessData.firstName}
                    onChange={(e) => handleEarlyAccessChange("firstName", e.target.value)}
                    className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-400 focus:border-emerald-300/70 focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                  />
                </div>
                <div className="space-y-2">
                  <label htmlFor={earlyLastNameId} className="text-sm font-medium text-slate-100">
                    Last name
                  </label>
                  <input
                    id={earlyLastNameId}
                    type="text"
                    placeholder="Your last name"
                    autoComplete="family-name"
                    value={earlyAccessData.lastName}
                    onChange={(e) => handleEarlyAccessChange("lastName", e.target.value)}
                    className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-400 focus:border-emerald-300/70 focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <label htmlFor={earlyEmailId} className="text-sm font-medium text-slate-100">
                    Email
                  </label>
                  <input
                    id={earlyEmailId}
                    type="email"
                    placeholder="you@example.com"
                    autoComplete="email"
                    value={earlyAccessData.email}
                    onChange={(e) => handleEarlyAccessChange("email", e.target.value)}
                    className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-400 focus:border-emerald-300/70 focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                  />
                </div>
                <div className="space-y-2">
                  <label htmlFor={earlyPhoneId} className="text-sm font-medium text-slate-100">
                    Phone
                  </label>
                  <input
                    id={earlyPhoneId}
                    type="tel"
                    placeholder="(555) 555-5555"
                    autoComplete="tel"
                    value={earlyAccessData.phone}
                    onChange={(e) => handleEarlyAccessChange("phone", e.target.value)}
                    className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-400 focus:border-emerald-300/70 focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label htmlFor={earlyContactId} className="text-sm font-medium text-slate-100">
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
                      className="flex cursor-pointer items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-100 transition hover:border-emerald-300/60"
                    >
                      <input
                        id={option.value === "email" ? earlyContactId : undefined}
                        type="radio"
                        name="preferred-contact"
                        value={option.value}
                        checked={earlyAccessData.preferredContact === option.value}
                        onChange={(e) => handleEarlyAccessChange("preferredContact", e.target.value)}
                        className="h-4 w-4 border-white/20 bg-white/10 text-emerald-400 focus:ring-emerald-400/60"
                      />
                      {option.label}
                    </label>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <label htmlFor={earlyJourneyId} className="text-sm font-medium text-slate-100">
                  Career journey and what you want next
                </label>
                <textarea
                  id={earlyJourneyId}
                  placeholder="Share your path so far, and the kinds of roles or environments you’re hoping to find."
                  value={earlyAccessData.careerJourney}
                  onChange={(e) => handleEarlyAccessChange("careerJourney", e.target.value)}
                  rows={4}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-400 focus:border-emerald-300/70 focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
                />
              </div>

              <div className="flex flex-wrap items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsEarlyAccessOpen(false)}
                  className="rounded-full border border-white/10 bg-white/5 px-5 py-2 text-sm font-semibold text-slate-100 transition hover:border-emerald-300/60 hover:text-emerald-100"
                >
                  Save for later
                </button>
                <button
                  type="button"
                  className="rounded-full bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 px-5 py-2 text-sm font-semibold text-slate-950 shadow-lg shadow-emerald-500/25 transition hover:shadow-emerald-400/30"
                >
                  Send request
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default PrelaunchLandingPage;
