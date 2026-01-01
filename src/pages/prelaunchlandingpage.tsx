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
        q: "Does Solverah rescore third-party assessments?",
        a: "No. If you upload prior assessments (e.g., StrengthsFinder, MBTI, DISC), Solverah does not validate or reinterpret them. They’re used only as contextual inputs for broader reflection.",
    },
    {
        q: "Is my data used to train models?",
        a: "Solverah uses data to provide and improve its services, with restricted access and responsible handling. User data is not sold.",
    },
    {
        q: "Can Authentic Intelligence be wrong?",
        a: "It surfaces interpretations, not facts. If something doesn’t resonate, it’s an invitation to question, refine, or explore — not a verdict.",
    },
    {
        q: "Why focus on conditions instead of labels?",
        a: "Because environments matter. Solverah emphasizes conditions, fit, and context so insights stay humane, flexible, and useful across situations.",
    },
    ];



  return (
  <div className="bg-white text-gray-900">
    <div className="mx-auto max-w-6xl px-5 sm:px-6 lg:px-8 py-12 sm:py-14">
      {/* Top bar can stay as-is if you have one */}

      {/* 2-column editorial layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-12">
        {/* Left marginalia (desktop) */}
        <aside className="hidden lg:block lg:col-span-4">
          <div className="sticky top-10">
            <div className="border-l border-red-200 pl-5">
              <div className="flex items-baseline justify-between gap-4">
                <h2 className="text-xs font-semibold tracking-wide text-red-700 uppercase">
                  How it works
                </h2>
                <span className="text-xs text-red-700/70">FAQ</span>
              </div>

              <p className="mt-3 text-sm leading-6 text-gray-600">
                A few clear answers, written for humans. No jargon. No pressure.
              </p>

              <div className="mt-6 space-y-6">
                {faqs.slice(0, 6).map((item) => (
                  <div key={item.q} className="group">
                    <div className="text-[13px] font-semibold text-red-700 leading-5">
                      {item.q}
                    </div>
                    <div className="mt-2 text-[13px] leading-5 text-gray-600">
                      {item.a}
                    </div>
                  </div>
                ))}
              </div>

              {/* Optional: a “read more” section (still editorial, not a buttony UI) */}
              <div className="mt-8 border-t border-red-100 pt-6">
                <div className="text-xs font-semibold tracking-wide text-red-700 uppercase">
                  Notes
                </div>
                <ul className="mt-3 space-y-2 text-sm text-gray-600">
                  <li>• Solverah supports reflection, not decisions.</li>
                  <li>• We prioritize care over scale.</li>
                  <li>• If something feels off, it’s feedback — not failure.</li>
                </ul>
              </div>
            </div>
          </div>
        </aside>

        {/* Mobile FAQ (simple + non “app-like”) */}
        <section className="lg:hidden">
          <div className="border border-gray-200 rounded-md">
            <div className="px-4 py-3 border-b border-gray-200">
              <div className="text-xs font-semibold tracking-wide text-red-700 uppercase">
                How it works
              </div>
              <p className="mt-1 text-sm text-gray-600">
                A few clear answers. No jargon. No pressure.
              </p>
            </div>
            <div className="px-4 py-4 space-y-4">
              {faqs.slice(0, 4).map((item) => (
                <div key={item.q}>
                  <div className="text-sm font-semibold text-gray-900">{item.q}</div>
                  <div className="mt-1 text-sm leading-6 text-gray-600">{item.a}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Main column */}
        <main className="lg:col-span-8">
          <div className="max-w-3xl">
            {/* Paste your existing page content here:
                - Masthead / intro
                - Trust note
                - Intake form
                - Objective / timeline / criteria (optional)
            */}

            {/* Example: keep your current header intact but ensure left alignment */}
    <div className="bg-white text-gray-900">
      {/* Page container */}
      <div className="mx-auto max-w-3xl px-5 sm:px-6 lg:px-8 py-14 sm:py-16">
        {/* Masthead */}
        <header className="mb-10 sm:mb-12">
          <div className="flex items-baseline justify-between gap-6">
            <div className="flex flex-col">
              <h1 className="mt-3 text-2xl sm:text-3xl font-semibold tracking-tight">
                Clarity about where you fit — grounded in real experience.
              </h1>
            </div>

          </div>

          <div className="mt-6 space-y-4 text-[15px] leading-7 text-gray-700">
            <p>
              Solverah is in early development. We’re building a system that helps people
              understand fit beyond keywords — with language, context, and work-style
              signals that reflect how careers actually work.
            </p>
            <p>
              We’re starting by listening. A resume and a small amount of context help us understand experience as it’s actually lived, not how it’s summarized.
            </p>
          </div>

          {/* Trust note (no icons, no hype) */}
          <div className="mt-7 border-t border-gray-200 pt-6">
            <p className="text-sm leading-6 text-gray-600">
              Clear before clever. Editorial, not app-like. Confidence without pressure.
              Your information is used only for evaluation and iteration.
            </p>
          </div>
        </header>

        {/* Intake */}
        <main className="space-y-10">
          <section aria-labelledby="intake-title" className="space-y-4">
            <div className="border-t border-gray-200 pt-8">
              
              <p className="mt-3 text-[15px] leading-7 text-gray-700">
                If you want to be part of the early build, share your resume and name below.
                This is a soft launch intake — no account, no onboarding flow, no noise.
              </p>
            </div>

            <form className="mt-6 space-y-7" onSubmit={(e) => e.preventDefault()}>
              {/* Name */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                <div className="space-y-2">
                  <label
                    htmlFor={firstNameId}
                    className="block text-sm font-medium text-gray-800"
                  >
                    First name
                  </label>
                  <input
                    id={firstNameId}
                    type="text"
                    placeholder="Your first name"
                    autoComplete="given-name"
                    className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm
                               focus:outline-none focus:ring-2 focus:ring-gray-900/10 focus:border-gray-400"
                  />
                </div>

                <div className="space-y-2">
                  <label
                    htmlFor={lastNameId}
                    className="block text-sm font-medium text-gray-800"
                  >
                    Last name
                  </label>
                  <input
                    id={lastNameId}
                    type="text"
                    placeholder="Your last name"
                    autoComplete="family-name"
                    className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm
                               focus:outline-none focus:ring-2 focus:ring-gray-900/10 focus:border-gray-400"
                  />
                </div>
              </div>

              {/* Resume */}
              <div className="space-y-2">
                <label
                  htmlFor={resumeId}
                  className="block text-sm font-medium text-gray-800"
                >
                  Resume (PDF or DOCX)
                </label>

                <div className="rounded-md border border-gray-300">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-4">
                    <div className="text-sm text-gray-700">
                      <div className="font-medium">Upload your resume</div>
                      <div className="mt-1 text-gray-500">
                        We use this to understand your experience in context, not to score you.
                      </div>
                      {selectedFileName ? (
                        <div className="mt-2 text-gray-600">
                          Selected: <span className="font-medium">{selectedFileName}</span>
                        </div>
                      ) : null}
                    </div>

                    <div className="shrink-0">
                      <label className="inline-flex items-center justify-center rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-800 cursor-pointer hover:bg-gray-50">
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
              </div>

              {/* “Quiz placeholders” as editorial notes, not boxes */}
              <div className="space-y-5">
                <div className="border-t border-gray-200 pt-6">
                  <h3 className="text-sm font-semibold text-gray-900">
                    Coming shortly: Archetype reflection 
                  </h3>
                  <p className="mt-2 text-[15px] leading-7 text-gray-700">
                    A short set of questions to capture work style, motivation, and how you
                    approach problems. This will help Solverah learn beyond resume structure.
                  </p>
                  <p className="mt-3 text-sm text-gray-500">
                    Placeholder only — not active yet.
                  </p>
                </div>

                <div className="border-t border-gray-200 pt-6">
                  <h3 className="text-sm font-semibold text-gray-900">
                    Coming shortly: Culture & team fit reflection.
                  </h3>
                  <p className="mt-2 text-[15px] leading-7 text-gray-700">
                    A short reflection on collaboration preferences, feedback style, and how
                    you like to operate within teams — used to support understanding, not pressure.
                  </p>
                  <p className="mt-3 text-sm text-gray-500">
                    Placeholder only — not active yet.
                  </p>
                </div>
              </div>

              {/* Submit (disabled) */}
              <div className="border-t border-gray-200 pt-7">
                <button
                  type="submit"
                  disabled
                  className="w-full rounded-md bg-gray-900 px-4 py-3 text-sm font-medium text-white
                             opacity-60 cursor-not-allowed"
                >
                  Submit intake (coming soon)
                </button>

                <p className="mt-3 text-sm leading-6 text-gray-600">
                  We’ll only use your information to evaluate intake and improve the early system. No hype, no spam.
                </p>
              </div>
            </form>
          </section>

          {/* Phase 1 definition (editorial footer) */}
          <section className="border-t border-gray-200 pt-10">
            <h2 className="text-sm font-semibold text-gray-900">Our Objective</h2>
            <p className="mt-2 text-[15px] leading-7 text-gray-700">
              Enable a credible soft launch to collect resumes and career inputs, build early
              signal for Solverah’s learning systems, and establish trust.
            </p>

          </section>
        </main>

        {/* Bottom note */}
        <footer className="mt-12 border-t border-gray-200 pt-6">
          <p className="text-xs leading-5 text-gray-500">
            © {new Date().getFullYear()} Solverah. Private development.
          </p>
        </footer>
      </div>
    </div>
            </div>
        </main>
      </div>
    </div>
  </div>
);
}

export default PrelaunchLandingPage;
