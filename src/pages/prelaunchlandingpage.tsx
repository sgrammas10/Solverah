import React, { useId, useState } from "react";

function PrelaunchLandingPage() {
  const firstNameId = useId();
  const lastNameId = useId();
  const resumeId = useId();

  const [selectedFileName, setSelectedFileName] = useState<string>("");

  return (
    <div className="bg-white text-gray-900">
      {/* Page container */}
      <div className="mx-auto max-w-3xl px-5 sm:px-6 lg:px-8 py-14 sm:py-16">
        {/* Masthead */}
        <header className="mb-10 sm:mb-12">
          <div className="flex items-baseline justify-between gap-6">
            <div className="flex flex-col">
              <div className="text-sm tracking-wide text-gray-500">Solverah</div>
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
                    Coming shortly: Archetype reflection (Phase 1)
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
            <h2 className="text-sm font-semibold text-gray-900">Phase 1 objective</h2>
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
  );
}

export default PrelaunchLandingPage;
