import React, { useId, useState } from "react";

function PrelaunchLandingPage() {
  const firstNameId = useId();
  const lastNameId = useId();
  const resumeId = useId();

  const [selectedFileName, setSelectedFileName] = useState<string>("");

  const faqs = [
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
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
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
                <p className="text-sm font-semibold text-emerald-200 tracking-[0.08em] uppercase">Solverah</p>
                <h1 className="text-3xl sm:text-4xl lg:text-5xl font-semibold leading-tight text-slate-50">
                  Modern careers deserve more than keywords. We’re building human-centered matching grounded in lived experience.
                </h1>
                <p className="text-lg text-slate-200/85 max-w-3xl">
                  Solverah blends structured frameworks with Authentic Intelligence to understand how people actually work — and how environments help them thrive. This prelaunch is focused on careful listening and thoughtful iteration.
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
                <a
                  href="#waitlist"
                  className="rounded-full bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 px-6 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-emerald-500/20 transition hover:shadow-emerald-400/25"
                >
                  Request early access
                </a>
                <a
                  href="#about"
                  className="text-sm font-semibold text-emerald-100/90 underline-offset-8 hover:underline"
                >
                  Learn more about Solverah
                </a>
              </div>
            </div>

            <div className="lg:col-span-5">
              <div className="rounded-2xl border border-white/10 bg-slate-900/70 p-6 shadow-2xl shadow-black/40 backdrop-blur">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.14em] text-emerald-200">Early Access</p>
                    <h2 className="text-xl font-semibold text-white">Join the Solverah signal</h2>
                    <p className="mt-1 text-sm text-slate-200/80">Private intake for thoughtful collaborators.</p>
                  </div>
                  <div className="h-12 w-12 rounded-full bg-gradient-to-tr from-emerald-400 to-blue-500 text-slate-950 flex items-center justify-center text-lg font-bold">
                    S
                  </div>
                </div>

                <form className="mt-6 space-y-6" onSubmit={(e) => e.preventDefault()}>
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
                              const f = e.target.files?.[0];
                              setSelectedFileName(f?.name ?? "");
                            }}
                          />
                        </label>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-3 rounded-lg bg-emerald-400/10 p-4 text-sm text-emerald-50 ring-1 ring-emerald-300/20">
                    <p className="font-semibold">How we use this</p>
                    <p className="text-slate-100/80">
                      Your details help us tune the early product. No onboarding, no automated decisions, and no downstream access beyond this prelaunch stage.
                    </p>
                  </div>

                  <button
                    type="submit"
                    className="w-full rounded-full bg-gradient-to-r from-emerald-400 via-blue-500 to-indigo-500 px-5 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-emerald-500/25 transition hover:shadow-emerald-400/30"
                  >
                    Submit interest (soft launch)
                  </button>
                  <p className="text-xs text-slate-200/70">
                    No instant accounts. We will reach out if the early cohort is a fit for this phase.
                  </p>
                </form>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div id="about" className="mx-auto max-w-6xl px-6 py-14 lg:py-20">
        <div className="grid gap-12 lg:grid-cols-12 lg:items-start">
          <div className="lg:col-span-7 space-y-4">
            <p className="text-sm font-semibold uppercase tracking-[0.14em] text-emerald-300">Why Solverah</p>
            <h2 className="text-2xl sm:text-3xl font-semibold text-white">Career intelligence that stays human.</h2>
            <p className="text-base text-slate-200/85 max-w-3xl">
              We build for people who want clarity without compromise. Solverah reads beyond job titles and buzzwords to understand how you work, what you value, and where you thrive. Authentic Intelligence keeps judgment with humans while giving structure to discovery.
            </p>
            <div className="grid gap-4 sm:grid-cols-2">
              {["Context before automation", "Signals over scores", "Careful by design", "Private by default"].map((item) => (
                <div key={item} className="rounded-xl border border-white/10 bg-slate-900/60 p-4 shadow-lg shadow-black/30">
                  <p className="text-sm font-semibold text-white">{item}</p>
                  <p className="mt-2 text-sm text-slate-200/80">
                    Thoughtful patterns, editorial clarity, and responsible handling of the details you choose to share.
                  </p>
                </div>
              ))}
            </div>
          </div>

          <div id="waitlist" className="lg:col-span-5 space-y-5 rounded-2xl border border-white/10 bg-white/5 p-6 shadow-2xl shadow-black/30">
            <p className="text-sm font-semibold uppercase tracking-[0.14em] text-emerald-300">Prelaunch status</p>
            <h3 className="text-xl font-semibold text-white">Only the prelaunch page is live</h3>
            <p className="text-sm text-slate-200/80">
              The broader platform remains gated while we learn. Navigation to other areas is redirected here so you can explore the preview safely.
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
                <p>Clear copy over glossy UI. You should know what’s happening with your data and why.</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-6 pb-14">
        <div className="rounded-2xl border border-white/10 bg-slate-900/70 p-8 shadow-2xl shadow-black/40">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-2xl space-y-3">
              <p className="text-sm font-semibold uppercase tracking-[0.14em] text-emerald-300">Questions we hear</p>
              <h3 className="text-2xl font-semibold text-white">A brief FAQ for early collaborators</h3>
              <p className="text-sm text-slate-200/80">
                Straightforward answers so you know how Solverah works at this stage. If something feels unclear, tell us — iteration is the point.
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
    </div>
  );
}

export default PrelaunchLandingPage;
