import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import HeroNetworkAnimation from "../components/HeroNetworkAnimation";
import LandingNav from "../components/landing/LandingNav";
import IntakeForm from "../components/landing/IntakeForm";
import AccountModal from "../components/landing/AccountModal";
import EarlyAccessModal from "../components/landing/EarlyAccessModal";
import { useIntakeForm } from "../hooks/useIntakeForm";
import { useEarlyAccess } from "../hooks/useEarlyAccess";

const faqs = [
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
];

function PrelaunchLandingPage() {
  const navigate = useNavigate();
  const intake = useIntakeForm();
  const earlyAccess = useEarlyAccess();

  // Close modals on Escape
  useEffect(() => {
    if (!earlyAccess.isOpen && !intake.accountModalOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (earlyAccess.isOpen) earlyAccess.setIsOpen(false);
      if (intake.accountModalOpen) intake.setAccountModalOpen(false);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [earlyAccess.isOpen, intake.accountModalOpen]);

  return (
    <div className="min-h-screen bg-cream-base font-sans text-ink-primary" style={{ zoom: 0.8 }}>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-[100] focus:bg-forest-dark focus:text-white focus:px-4 focus:py-2 focus:rounded"
      >
        Skip to main content
      </a>

      <LandingNav onRequestEarlyAccess={() => earlyAccess.setIsOpen(true)} />

      <main id="main">
        {/* ─── HERO ─── */}
        <section className="bg-cream-base" style={{ minHeight: "88vh", paddingTop: "80px", paddingBottom: "80px" }}>
          <div className="mx-auto max-w-7xl px-6">
            <div className="grid grid-cols-1 gap-12 lg:grid-cols-[55fr_45fr] lg:gap-16 items-center">

              {/* Left — Copy */}
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
                  {["Early preview", "Human-led evaluation"].map((badge) => (
                    <span key={badge} className="text-sm text-ink-secondary border border-cream-muted rounded-full px-4 py-1.5">
                      {badge}
                    </span>
                  ))}
                </div>
                <div className="flex flex-wrap items-center gap-4 animate-fade-up-slower opacity-0">
                  <button
                    type="button"
                    onClick={() => earlyAccess.setIsOpen(true)}
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
                  <a href="#features" className="text-sm font-semibold text-forest-mid hover:underline underline-offset-4 transition-colors">
                    See how it works
                  </a>
                </div>
              </div>

              {/* Right — Intake Form */}
              <IntakeForm
                formData={intake.formData}
                onInputChange={intake.handleInputChange}
                privacyConsent={intake.privacyConsent}
                setPrivacyConsent={intake.setPrivacyConsent}
                infoOptIn={intake.infoOptIn}
                setInfoOptIn={intake.setInfoOptIn}
                resumeFile={intake.resumeFile}
                setResumeFile={intake.setResumeFile}
                selectedFileName={intake.selectedFileName}
                setSelectedFileName={intake.setSelectedFileName}
                submissionStatus={intake.submissionStatus}
                errorMessage={intake.errorMessage}
                onSubmit={intake.handleSubmit}
              />
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
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-3">What We Offer</p>
            <h2 className="font-display text-[clamp(2rem,4vw,2.75rem)] font-bold text-ink-primary mb-12 max-w-[480px] leading-snug">
              Built around how people actually grow.
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-6 gap-4 auto-rows-auto">
              <div className="md:col-span-4 md:row-span-2 border border-cream-muted rounded-xl bg-white p-8 flex flex-col justify-between group hover:border-forest-light transition-colors" style={{ minHeight: "320px" }}>
                <div>
                  <span className="inline-block text-[11px] font-semibold uppercase tracking-[0.08em] bg-forest-pale text-forest-mid px-2.5 py-1 rounded mb-5">Core Experience</span>
                  <h3 className="font-display text-[1.75rem] font-semibold text-ink-primary leading-snug mb-3 max-w-[420px]">
                    Matching built around how you actually work
                  </h3>
                  <p className="text-base text-ink-secondary leading-relaxed max-w-[420px]">
                    Solverah reads beyond job titles and buzzwords to understand your work style, values, and the environments where you genuinely thrive.
                  </p>
                </div>
                <a href="#how-it-works" className="mt-8 flex items-center gap-2 text-sm font-semibold text-forest-mid hover:underline underline-offset-4">
                  <span>Learn how it works</span>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="transition-transform group-hover:translate-x-1" aria-hidden="true">
                    <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </a>
              </div>
              <div className="md:col-span-2 border border-cream-muted rounded-xl bg-white p-6 group hover:border-forest-light transition-colors">
                <span className="inline-block text-[11px] font-semibold uppercase tracking-[0.08em] bg-forest-pale text-forest-mid px-2.5 py-1 rounded mb-4">AI-Native</span>
                <h3 className="font-display text-[1.25rem] font-semibold text-ink-primary leading-snug mb-2">Authentic Intelligence</h3>
                <p className="text-sm text-ink-secondary leading-relaxed">Structured frameworks, not black-box scores. Insights that describe patterns and possibilities.</p>
              </div>
              <div className="md:col-span-1 border border-cream-muted rounded-xl bg-forest-pale p-5 group hover:border-forest-light transition-colors">
                <span className="inline-block text-[11px] font-semibold uppercase tracking-[0.08em] text-forest-mid mb-3">Privacy</span>
                <h3 className="font-display text-[1.1rem] font-semibold text-ink-primary leading-snug mb-2">Private by default</h3>
                <p className="text-xs text-ink-secondary leading-relaxed">You control what's shared. We store only what you choose to provide.</p>
              </div>
              <div className="md:col-span-1 border border-cream-muted rounded-xl bg-forest-dark p-5 group">
                <span className="inline-block text-[11px] font-semibold uppercase tracking-[0.08em] text-forest-pale mb-3">Philosophy</span>
                <h3 className="font-display text-[1.1rem] font-semibold text-white leading-snug mb-2">Context before automation</h3>
                <p className="text-xs text-forest-pale leading-relaxed">Human review pairs with every insight we generate.</p>
              </div>
              <div className="md:col-span-2 border border-cream-muted rounded-xl bg-white p-6 group hover:border-forest-light transition-colors">
                <span className="inline-block text-[11px] font-semibold uppercase tracking-[0.08em] bg-forest-pale text-forest-mid px-2.5 py-1 rounded mb-4">Approach</span>
                <h3 className="font-display text-[1.25rem] font-semibold text-ink-primary leading-snug mb-2">Conditions over labels</h3>
                <p className="text-sm text-ink-secondary leading-relaxed">Environments shape outcomes. We look at fit, context, and conditions — not just your last job title.</p>
              </div>
            </div>
          </div>
        </section>

        {/* ─── HOW IT WORKS ─── */}
        <section id="how-it-works" className="bg-forest-mid border-t border-forest-light/30 py-24 px-6">
          <div className="mx-auto max-w-7xl">
            <div className="text-center max-w-[600px] mx-auto mb-16 space-y-4">
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-pale">The Process</p>
              <h2 className="font-display text-[clamp(2rem,4vw,2.75rem)] font-bold text-cream-base leading-snug">
                From your story to actionable insight.
              </h2>
              <p className="text-base text-cream-subtle leading-relaxed">
                Solverah doesn't score you against a template. It reads the full picture of how you work.
              </p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-16">
              {[
                { step: "01", title: "You share your context", body: "Your resume, background, and optionally your LinkedIn or portfolio. We ask only for what's useful.", accent: "bg-forest-pale" },
                { step: "02", title: "Structured frameworks map your signal", body: "Our system applies a layered set of frameworks to translate unstructured career history into meaningful dimensions.", accent: "bg-forest-pale" },
                { step: "03", title: "Patterns are identified, not invented", body: "We surface what the information already suggests — about your work style, environment preferences, and conditions.", accent: "bg-forest-pale" },
                { step: "04", title: "A human reviews before anything reaches you", body: "Every insight set is reviewed by a person before delivery. Automated analysis is a starting point — editorial judgment is the finish line.", accent: "bg-forest-dark" },
              ].map(({ step, title, body, accent }) => (
                <div key={step} className="relative rounded-xl border border-forest-light/40 bg-white p-6 hover:border-forest-light transition-colors flex flex-col gap-4">
                  <span className={`inline-flex items-center justify-center w-9 h-9 rounded-full ${accent} font-display text-sm font-bold ${accent === "bg-forest-dark" ? "text-white" : "text-forest-mid"} shrink-0`}>{step}</span>
                  <div>
                    <h3 className="font-display text-[1.05rem] font-semibold text-ink-primary leading-snug mb-2">{title}</h3>
                    <p className="text-sm text-ink-secondary leading-relaxed">{body}</p>
                  </div>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {[
                { label: "What we look at", content: "Work history, scope of responsibility, environment signals, and the conditions that appear when people do their best work." },
                { label: "What we don't do", content: "We don't assign you a type, a tier, or a numeric score. We don't compare you to a benchmark or rank you against other candidates." },
                { label: "Why this matters", content: "Most career tools optimize for searchability. Solverah optimizes for understanding." },
              ].map(({ label, content }) => (
                <div key={label} className="rounded-xl border border-forest-light/40 bg-white p-6">
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
                <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light">Why Solverah</p>
                <h2 className="font-display text-[clamp(2rem,4vw,2.75rem)] font-bold text-ink-primary leading-snug">
                  Career intelligence that stays human.
                </h2>
                <p className="text-base text-ink-secondary leading-relaxed max-w-[540px]">
                  Solverah reads beyond job titles and buzzwords to understand how you work, what you value, and where you thrive.
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
                <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light">Prelaunch status</p>
                <h3 className="font-display text-[1.5rem] font-semibold text-ink-primary">Early intake is live</h3>
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
                <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light">Questions we hear</p>
                <h2 className="font-display text-[clamp(1.75rem,3vw,2.25rem)] font-bold text-ink-primary leading-snug">
                  A brief FAQ for early collaborators
                </h2>
                <p className="text-sm text-ink-secondary leading-relaxed">
                  Straightforward answers so you know how Solverah works at this stage.
                </p>
              </div>
              <div className="grid gap-4">
                {faqs.map((item) => (
                  <div key={item.q} className="rounded-lg border border-cream-muted bg-white p-5 hover:border-forest-pale transition-colors">
                    <p className="text-sm font-semibold text-ink-primary mb-2">{item.q}</p>
                    <p className="text-sm text-ink-secondary leading-relaxed">{item.a}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ─── CTA ─── */}
        <section className="bg-forest-dark py-24 px-6">
          <div className="mx-auto max-w-4xl text-center space-y-6">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-pale">Ready to be seen differently</p>
            <h2 className="font-display text-[clamp(2rem,4vw,3rem)] font-bold text-white leading-snug">
              Your career is more than your last job title.
            </h2>
            <p className="text-lg text-forest-pale leading-relaxed max-w-[520px] mx-auto">
              Join the early cohort. Share your story, and let us find the conditions where you do your best work.
            </p>
            <div className="flex flex-wrap items-center justify-center gap-4 pt-2">
              <button
                type="button"
                onClick={() => earlyAccess.setIsOpen(true)}
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
                onClick={() => earlyAccess.setIsOpen(true)}
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
            <p className="text-xs text-[#888]">© {new Date().getFullYear()} Solverah. All rights reserved.</p>
            <div className="flex gap-6">
              <a href="#" className="text-xs text-[#888] hover:text-white transition-colors">Privacy Policy</a>
              <a href="#" className="text-xs text-[#888] hover:text-white transition-colors">Terms</a>
            </div>
          </div>
        </div>
      </footer>

      {/* ─── MODALS ─── */}
      <EarlyAccessModal
        isOpen={earlyAccess.isOpen}
        onClose={() => earlyAccess.setIsOpen(false)}
        isSuccess={earlyAccess.isSuccess}
        onDismissSuccess={() => earlyAccess.setIsSuccess(false)}
        formData={earlyAccess.formData}
        onChange={earlyAccess.handleChange}
        isSubmitting={earlyAccess.isSubmitting}
        error={earlyAccess.error}
        onSubmit={earlyAccess.handleSubmit}
      />

      <AccountModal
        isOpen={intake.accountModalOpen}
        onClose={() => intake.setAccountModalOpen(false)}
        submissionEmail={intake.submissionEmail}
        step={intake.accountStep}
        setStep={intake.setAccountStep}
        action={intake.accountAction}
        signInEmail={intake.signInEmail}
        setSignInEmail={intake.setSignInEmail}
        signInPassword={intake.signInPassword}
        setSignInPassword={intake.setSignInPassword}
        accountPassword={intake.accountPassword}
        setAccountPassword={intake.setAccountPassword}
        accountConfirm={intake.accountConfirm}
        setAccountConfirm={intake.setAccountConfirm}
        error={intake.accountError}
        setError={intake.setAccountError}
        isCreatingAccount={intake.isCreatingAccount}
        isSigningIn={intake.isSigningIn}
        onCreateAccount={intake.handleCreateAccount}
        onSignInExisting={intake.handleSignInExisting}
      />
    </div>
  );
}

export default PrelaunchLandingPage;
