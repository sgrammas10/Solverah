import { ReactNode, Suspense, lazy, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { IntakeForm, AccountModal, useIntakeForm } from "../../intake";
import ScrollStory from "./hero/ScrollStory";
import { CONTAINER, PAGE_H1, PRIMARY, SECONDARY } from "../../../shared/ui/publicStyles";
import "./landing.css";

// Below the fold and still on trial, so it ships in its own chunk with its own
// stylesheet rather than in the entry bundle.
const EcosystemSection = lazy(() => import("./ecosystem/EcosystemSection"));


/**
 * The public landing page at "/".
 *
 * The hero is a scroll story (hero/ScrollStory.tsx): the top of the page pins
 * while the visitor scrolls through what Solverah produces, then the rest of
 * the page explains how a reading is made, what it will never be used for,
 * and where to start.
 *
 * The intake flow, the account modal and the account-deletion notice all
 * live here.
 */

const H2 = PAGE_H1;

const STEPS = [
  {
    title: "Your answers are evidence, not conclusions.",
    body: "Work Pulse and the other assessments are structured questions, not a chat. Each answer is one data point about how you work: pace, structure, autonomy, feedback, recognition, how you handle change. None of them is a verdict on its own.",
  },
  {
    title: "Read against conditions, not templates.",
    body: "Frameworks turn those answers into a reading on each dimension and set it beside the conditions where people do their best work. No rank against other people. No single number.",
  },
  {
    title: "Checked by a person before it reaches you.",
    body: "Every submission gets a human review. Automated analysis is where a reading starts. Someone's judgment is where it finishes.",
  },
];

const WE_READ = [
  "Your work history, and the scope of responsibility behind each title.",
  "The environment signals in your answers.",
  "The conditions that were present when you did your best work.",
  "Only what you choose to give us: responses, background, optional uploads.",
];

const WE_WONT = [
  "Assign you a type, a tier, or a numeric score.",
  "Rank you against other candidates.",
  "Make hiring, promotion, or pay decisions.",
  "Sell your data, or show it to an employer.",
];

const COMMITMENTS = [
  {
    head: "Never sold.",
    body: "Your data is yours. We don't sell it and we don't trade it.",
  },
  {
    head: "Never shown to employers.",
    body: "No recruiter, hiring manager, or company sees your profile. That rule is enforced in the code, not just written in a policy.",
  },
  {
    head: "Never a decision.",
    body: "Solverah doesn't make hiring, promotion, or pay decisions. A reading is something for you to think with.",
  },
];

const FAQS = [
  {
    q: "What is Authentic Intelligence?",
    a: "Authentic Intelligence is Solverah's approach to generating insights that respect human complexity. It uses structured frameworks, rules-based logic, and automated analysis to surface patterns about how people work and where environments support or create friction.",
  },
  {
    q: "Is this the same as artificial intelligence?",
    a: "It may use automated systems and AI-supported techniques, but it isn't designed to replace human judgment. It supports reflection and understanding, not decisions.",
  },
  {
    q: "What information does it use?",
    a: "Only what you choose to provide: responses, career background, and optional uploads. It may also use contextual information about roles or environments to generate insights.",
  },
  {
    q: "Does it make career or employment decisions?",
    a: "No. Solverah does not make hiring, promotion, compensation, or career decisions. Insights are advisory and interpretive. Final decisions remain with you.",
  },
  {
    q: "Are the insights personalized?",
    a: "Yes. They reflect the factors you provide and how they interact. But personalization is not prediction. Insights describe patterns and possibilities, not outcomes.",
  },
  {
    q: "Why focus on conditions instead of labels?",
    a: "Because environments matter. Solverah emphasizes conditions, fit, and context so insights stay humane, flexible, and useful across situations.",
  },
];

function PlusIcon() {
  return (
    <svg
      className="lp-plus shrink-0 text-ink-secondary"
      width="18"
      height="18"
      viewBox="0 0 18 18"
      fill="none"
      aria-hidden="true"
    >
      <path d="M9 3v12M3 9h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

const NAV_LINKS = [
  { label: "How it reads", href: "#how-it-reads" },
  { label: "Work Pulse", href: "#work-pulse" },
  { label: "FAQ", href: "#faq" },
];

function LandingPageNav() {
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`sticky top-0 z-40 border-b border-cream-muted transition-colors duration-300 ${
        scrolled ? "bg-cream-base" : "bg-transparent"
      }`}
    >
      <div className={`${CONTAINER} flex h-16 items-center justify-between`}>
        <Link
          to="/"
          className="font-headline text-[1.35rem] font-extrabold tracking-[-0.02em] text-ink-primary"
        >
          Solverah
        </Link>

        <nav aria-label="Primary" className="hidden items-center gap-8 md:flex">
          {NAV_LINKS.map(({ label, href }) => (
            <a
              key={label}
              href={href}
              className="text-[0.9rem] font-medium text-ink-secondary transition-colors hover:text-forest-mid"
            >
              {label}
            </a>
          ))}
        </nav>

        <div className="hidden items-center gap-3 md:flex">
          <Link
            to="/login"
            className="px-3 py-2 text-[0.9rem] font-medium text-ink-secondary transition-colors hover:text-forest-mid"
          >
            Sign in
          </Link>
          <a
            href="#intake"
            className="inline-flex items-center rounded-[4px] bg-forest-dark px-5 py-2.5 font-headline text-[0.9rem] font-bold text-white transition-colors hover:bg-forest-mid"
          >
            Get started
          </a>
        </div>

        <button
          type="button"
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
          aria-controls="landing-mobile-menu"
          onClick={() => setMenuOpen((v) => !v)}
          className="-mr-2 flex flex-col gap-1.5 p-2 md:hidden"
        >
          <span
            className={`block h-0.5 w-6 bg-ink-primary transition-transform duration-200 ${
              menuOpen ? "translate-y-2 rotate-45" : ""
            }`}
          />
          <span
            className={`block h-0.5 w-6 bg-ink-primary transition-opacity duration-200 ${menuOpen ? "opacity-0" : ""}`}
          />
          <span
            className={`block h-0.5 w-6 bg-ink-primary transition-transform duration-200 ${
              menuOpen ? "-translate-y-2 -rotate-45" : ""
            }`}
          />
        </button>
      </div>

      {menuOpen && (
        <div
          id="landing-mobile-menu"
          className="border-t border-cream-muted bg-cream-base px-6 py-5 md:hidden"
        >
          <nav aria-label="Primary, mobile" className="flex flex-col">
            {NAV_LINKS.map(({ label, href }) => (
              <a
                key={label}
                href={href}
                onClick={() => setMenuOpen(false)}
                className="border-b border-cream-muted py-3.5 text-[1rem] font-medium text-ink-primary"
              >
                {label}
              </a>
            ))}
            <Link
              to="/login"
              className="border-b border-cream-muted py-3.5 text-[1rem] font-medium text-ink-primary"
            >
              Sign in
            </Link>
          </nav>
          <a
            href="#intake"
            onClick={() => setMenuOpen(false)}
            className={`${PRIMARY} mt-5 w-full`}
          >
            Get started
          </a>
        </div>
      )}
    </header>
  );
}

function HowItReads() {
  return (
    <section id="how-it-reads" className="scroll-mt-16 border-t border-cream-muted">
      <div
        className={`${CONTAINER} grid gap-12 py-20 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] md:gap-20 md:py-28`}
      >
        <div className="md:sticky md:top-24 md:self-start">
          <h2 className={H2}>What a reading is made of.</h2>
          <p className="mt-5 max-w-[42ch] text-[1.02rem] leading-[1.6] text-ink-secondary">
            Solverah doesn't score you against a template, and it doesn't hand you a percentage. It
            reads for conditions: the scope you had, the pace you keep, the structure you need, and
            what the words on your resume were standing in for.
          </p>
        </div>

        <div className="border-t border-cream-muted">
          {STEPS.map((step) => (
            <article
              key={step.title}
              className="grid gap-3 border-b border-cream-muted py-8 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] md:gap-10"
            >
              <h3 className="font-headline text-[1.35rem] font-bold leading-tight text-balance">
                {step.title}
              </h3>
              <p className="text-[0.98rem] leading-[1.65] text-ink-secondary">{step.body}</p>
            </article>
          ))}
        </div>
      </div>

      <div className={`${CONTAINER} pb-20 md:pb-28`}>
        <div className="grid gap-[2px] bg-cream-muted md:grid-cols-2">
          <div className="bg-white p-7">
            <h3 className="font-headline text-[1.15rem] font-bold">What we read</h3>
            <ul className="mt-4 space-y-2.5 text-[0.95rem] leading-[1.55] text-ink-secondary">
              {WE_READ.map((item) => (
                <li key={item} className="flex gap-3">
                  <span className="mt-[0.7em] h-px w-4 shrink-0 bg-forest-dark" aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <div className="bg-white p-7">
            <h3 className="font-headline text-[1.15rem] font-bold">What we won't do</h3>
            <ul className="mt-4 space-y-2.5 text-[0.95rem] leading-[1.55] text-ink-secondary">
              {WE_WONT.map((item) => (
                <li key={item} className="flex gap-3">
                  <span className="mt-[0.7em] h-px w-4 shrink-0 bg-ink-tertiary" aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

function WorkPulse({ navigate }: { navigate: (to: string) => void }) {
  return (
    <section id="work-pulse" className="scroll-mt-16 border-t border-cream-muted">
      <div className={`${CONTAINER} py-20 md:py-28`}>
        <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between md:gap-12">
          <h2 className={H2}>Start with Work Pulse™.</h2>
          <p className="max-w-[40ch] text-[1.02rem] leading-[1.6] text-ink-secondary">
            Twelve questions about how you actually work. Free, with an account, so your reading
            has somewhere to live.
          </p>
        </div>

        <div className="mt-12 border-t border-cream-muted">
          <div className="grid gap-4 border-b border-cream-muted py-7 md:grid-cols-[minmax(0,3fr)_minmax(0,5fr)_auto] md:items-center md:gap-10">
            <div>
              <h3 className="font-headline text-[1.35rem] font-bold">Work Pulse™</h3>
              <p className="mt-1 text-[0.86rem] text-ink-secondary">12 questions · free · account required</p>
            </div>
            <p className="text-[0.97rem] leading-[1.6] text-ink-secondary">
              A full narrative insight, your primary work archetype, and the emerging signals shaping
              how you experience work. It also starts your Solverah profile.
            </p>
            <button type="button" onClick={() => navigate("/register")} className={PRIMARY}>
              Create an account
            </button>
          </div>

          <div className="grid gap-4 border-b border-cream-muted py-7 md:grid-cols-[minmax(0,3fr)_minmax(0,5fr)_auto] md:items-center md:gap-10">
            <div>
              <h3 className="font-headline text-[1.35rem] font-bold">Quiz previews</h3>
              <p className="mt-1 text-[0.86rem] text-ink-secondary">No account · a few minutes</p>
            </div>
            <p className="text-[0.97rem] leading-[1.6] text-ink-secondary">
              Short reflection quizzes you can take without signing up, one for each career stage.
              A taste of the questions, not a full reading.
            </p>
            <button type="button" onClick={() => navigate("/quiz-preview")} className={SECONDARY}>
              Preview a quiz
            </button>
          </div>

          <div className="grid gap-4 border-b border-cream-muted py-7 md:grid-cols-[minmax(0,3fr)_minmax(0,5fr)_auto] md:items-center md:gap-10">
            <div>
              <h3 className="font-headline text-[1.35rem] font-bold text-ink-secondary">Work Pulse Pro™</h3>
              <p className="mt-1 text-[0.86rem] text-ink-secondary">On the roadmap</p>
            </div>
            <p className="text-[0.97rem] leading-[1.6] text-ink-secondary">
              Deeper pattern analysis and company-environment matching. Not available yet. When it
              is, it will say so here, and not before.
            </p>
            <p className="text-[0.86rem] font-semibold text-ink-secondary md:text-right">Not yet available</p>
          </div>
        </div>
      </div>
    </section>
  );
}

function Commitments() {
  return (
    <section aria-labelledby="commitments-heading" className="border-t border-cream-muted">
      <div className={`${CONTAINER} py-16 md:py-20`}>
        <h2 id="commitments-heading" className="sr-only">
          What Solverah will never do with your data
        </h2>
        <div className="border-t border-cream-muted">
          {COMMITMENTS.map((c) => (
            <div
              key={c.head}
              className="grid gap-2 border-b border-cream-muted py-6 md:grid-cols-[minmax(0,3fr)_minmax(0,5fr)] md:items-baseline md:gap-10"
            >
              <p className="font-headline text-[1.6rem] font-extrabold leading-tight tracking-[-0.01em]">
                {c.head}
              </p>
              <p className="max-w-[60ch] text-[0.97rem] leading-[1.6] text-ink-secondary">{c.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Faq() {
  return (
    <section id="faq" className="scroll-mt-16 border-t border-cream-muted">
      <div
        className={`${CONTAINER} grid gap-10 py-20 md:grid-cols-[minmax(0,4fr)_minmax(0,8fr)] md:gap-20 md:py-28`}
      >
        <div>
          <h2 className={H2}>Questions we get.</h2>
          <p className="mt-5 max-w-[36ch] text-[1.02rem] leading-[1.6] text-ink-secondary">
            Plain answers about what Solverah is, what it uses, and what it will never decide for
            you.
          </p>
        </div>
        <div className="border-t border-cream-muted">
          {FAQS.map((item) => (
            <details key={item.q} className="border-b border-cream-muted">
              <summary className="flex cursor-pointer items-center justify-between gap-6 py-5 text-[1.05rem] font-semibold text-ink-primary">
                {item.q}
                <PlusIcon />
              </summary>
              <p className="max-w-[68ch] pb-6 pr-10 text-[0.97rem] leading-[1.65] text-ink-secondary">
                {item.a}
              </p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

function Closing({ navigate }: { navigate: (to: string) => void }) {
  return (
    <section className="border-t border-cream-muted bg-white">
      <div className={`${CONTAINER} py-20 md:py-28`}>
        <h2 className="max-w-[16ch] text-balance font-headline text-[clamp(2.2rem,5.5vw,4rem)] font-extrabold leading-[1] tracking-[-0.025em]">
          Your title is where the reading starts, not where it ends.
        </h2>
        <div className="mt-9 flex flex-wrap items-center gap-x-5 gap-y-4">
          <a href="#intake" className={PRIMARY}>
            Get started
          </a>
          <button type="button" onClick={() => navigate("/quiz-preview")} className={SECONDARY}>
            Preview a quiz first
          </button>
        </div>
      </div>
    </section>
  );
}

function FooterColumn({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div>
      <p className="text-[0.86rem] font-semibold text-white">{title}</p>
      <div className="mt-3 flex flex-col gap-2">{children}</div>
    </div>
  );
}

const FOOTER_LINK = "text-[0.9rem] text-[#AAA] transition-colors hover:text-white";

function Footer() {
  return (
    <footer className="border-t border-white/10 bg-ink-primary">
      <div className={`${CONTAINER} grid gap-10 py-14 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr]`}>
        <div>
          <span className="font-headline text-[1.35rem] font-extrabold tracking-[-0.02em] text-white">
            Solverah
          </span>
          <p className="mt-3 max-w-[28ch] text-[0.9rem] leading-[1.6] text-[#AAA]">
            Career readings built from conditions and context, checked by a person, and kept away
            from employers.
          </p>
        </div>
        <FooterColumn title="This page">
          {NAV_LINKS.map(({ label, href }) => (
            <a key={label} href={href} className={FOOTER_LINK}>
              {label}
            </a>
          ))}
        </FooterColumn>
        <FooterColumn title="Account">
          <Link to="/login" className={FOOTER_LINK}>
            Sign in
          </Link>
          <Link to="/register" className={FOOTER_LINK}>
            Create an account
          </Link>
          <Link to="/quiz-preview" className={FOOTER_LINK}>
            Preview a quiz
          </Link>
        </FooterColumn>
        <FooterColumn title="Legal">
          <Link to="/privacy" className={FOOTER_LINK}>
            Privacy policy
          </Link>
          <Link to="/terms" className={FOOTER_LINK}>
            Terms
          </Link>
          <Link to="/how-matching-works" className={FOOTER_LINK}>
            How matching works
          </Link>
        </FooterColumn>
      </div>
      <div className="border-t border-white/10">
        <div className={`${CONTAINER} py-5`}>
          <p className="text-[0.76rem] text-[#AAA]">
            © {new Date().getFullYear()} Solverah. All rights reserved.
          </p>
        </div>
      </div>
      <div className="border-t border-white/10">
        <div className="mx-auto max-w-[760px] px-6 py-5">
          <p className="text-[0.76rem] leading-[1.6] text-[#AAA]">
            This page includes information from the{" "}
            <a
              href="https://www.onetcenter.org/database.html"
              target="_blank"
              rel="noopener noreferrer"
              className="underline underline-offset-2 transition-colors hover:text-white"
            >
              O*NET 30.3 Database
            </a>{" "}
            by the U.S. Department of Labor, Employment and Training Administration (USDOL/ETA).
            Used under the{" "}
            <a
              href="https://creativecommons.org/licenses/by/4.0/"
              target="_blank"
              rel="noopener noreferrer"
              className="underline underline-offset-2 transition-colors hover:text-white"
            >
              CC BY 4.0
            </a>{" "}
            license. O*NET® is a trademark of USDOL/ETA. Solverah has modified all or some of this
            information. USDOL/ETA has not approved, endorsed, or tested these modifications.
          </p>
        </div>
      </div>
    </footer>
  );
}

function LandingPage() {
  const navigate = useNavigate();
  const intake = useIntakeForm();

  // Account-deletion confirmation, handed over in router state by
  // AccountSettingsPage on its way out. Router state and nothing else: the
  // account is gone, so there is no session to read it from, and a public route
  // that announced a deletion from a query string or localStorage would show a
  // stranger's confirmation to whoever opened the link next.
  const location = useLocation();
  const deletion = location.state as
    | { accountDeleted?: boolean; filesLeftBehind?: boolean }
    | null;
  const [deletionDismissed, setDeletionDismissed] = useState(false);
  const showDeletionNote = Boolean(deletion?.accountDeleted) && !deletionDismissed;

  // Close the account modal on Escape
  useEffect(() => {
    if (!intake.accountModalOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") intake.setAccountModalOpen(false);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [intake.accountModalOpen]);

  return (
    <div className="landing min-h-screen bg-cream-base font-body text-ink-primary antialiased">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-[100] focus:rounded-[4px] focus:bg-forest-dark focus:px-4 focus:py-2 focus:font-semibold focus:text-white"
      >
        Skip to main content
      </a>

      {showDeletionNote && (
        <div
          role="status"
          className="border-b border-cream-muted bg-white px-6 py-3 text-[0.9rem] text-ink-primary"
        >
          <div className="mx-auto flex max-w-[1180px] items-start justify-between gap-4">
            <p>
              Your account has been deleted.
              {deletion?.filesLeftBehind && (
                <>
                  {" "}
                  One or more uploaded files couldn't be removed from storage yet. Email{" "}
                  <a href="mailto:info@solverah.com" className="font-medium underline underline-offset-2">
                    info@solverah.com
                  </a>{" "}
                  and we'll confirm once they're gone.
                </>
              )}
            </p>
            <button
              type="button"
              onClick={() => setDeletionDismissed(true)}
              aria-label="Dismiss"
              className="shrink-0 font-medium text-ink-secondary transition-colors hover:text-forest-mid"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      <LandingPageNav />

      <main id="main">
        <ScrollStory />
        <HowItReads />
        <Suspense fallback={<div aria-hidden="true" style={{ minHeight: "40rem" }} />}>
          <EcosystemSection />
        </Suspense>
        <WorkPulse navigate={navigate} />

        <section id="intake" className="scroll-mt-16 border-t border-cream-muted bg-cream-subtle text-ink-primary">
          <div
            className={`${CONTAINER} grid gap-12 py-20 md:py-28 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16`}
          >
            <div className="lg:sticky lg:top-24 lg:self-start">
              <h2 className={H2}>Start your reading.</h2>
              <p className="mt-5 max-w-[44ch] text-[1.02rem] leading-[1.6] text-ink-secondary">
                Share your resume and a little context. You set up your account in the same step,
                and a person reviews what you send before anything comes back to you.
              </p>
              <ul className="mt-8 space-y-3 border-t border-cream-muted pt-6 text-[0.95rem] leading-[1.55] text-ink-secondary">
                <li>Resume as PDF or DOCX. We read it for context, not to score you.</li>
                <li>Your file goes to private storage and is never shown to employers.</li>
                <li>
                  Already have an account?{" "}
                  <Link to="/login" className="font-semibold text-ink-primary underline underline-offset-4">
                    Sign in
                  </Link>
                  .
                </li>
              </ul>
            </div>

            <IntakeForm
              formData={intake.formData}
              onInputChange={intake.handleInputChange}
              privacyConsent={intake.privacyConsent}
              setPrivacyConsent={intake.setPrivacyConsent}
              infoOptIn={intake.infoOptIn}
              setInfoOptIn={intake.setInfoOptIn}
              setResumeFile={intake.setResumeFile}
              selectedFileName={intake.selectedFileName}
              setSelectedFileName={intake.setSelectedFileName}
              submissionStatus={intake.submissionStatus}
              errorMessage={intake.errorMessage}
              onSubmit={intake.handleSubmit}
            />
          </div>
        </section>

        <Commitments />
        <Faq />
        <Closing navigate={navigate} />
      </main>

      <Footer />

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

export default LandingPage;
