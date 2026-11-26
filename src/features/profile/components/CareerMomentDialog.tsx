/**
 * CareerMomentDialog -- the first two steps of the first-run flow, shown on the
 * signed-in dashboard (agreed by Sebastian and Julie, 2026-11-24).
 *
 * 1. "What brings you here?" Six large choices. Four already say whether the
 *    user is working, and the server writes that status with the moment. The
 *    other two ("Looking for my next role", "Understanding how I work") ask
 *    "Are you working right now?" -- unless the profile already holds a
 *    status, which then stands.
 * 2. "In your own words", optional. One text box, saved word for word and
 *    never scored. "Skip" just closes.
 *
 * Step 1's "Not now" (and Esc) snoozes the dialog; the parent owns the snooze.
 * Step 2 is never re-asked: a user who leaves between the steps has answered
 * the question that matters. All copy is best-guess; Julie revises.
 */
import { useEffect, useId, useRef, useState } from "react";

import {
  CAREER_MOMENT_OPTIONS,
  OWN_WORDS_MAX_CHARS,
  WORKING_NOW_OPTIONS,
  WORKING_NOW_QUESTION,
  type CareerMomentOption,
} from "../careerMoments";
import type { CareerStatus } from "../types";
import { useSaveOnboarding, type OnboardingUpdate } from "./useSaveOnboarding";

export interface CareerMomentDialogProps {
  /** The stored career status. When set, the follow-up question is skipped. */
  careerStatus: string | null | undefined;
  /** Step 1 dismissed without an answer ("Not now" or Esc). */
  onNotNow: () => void;
  /** The flow is over: step 2 saved or skipped. */
  onClose: () => void;
}

type Step = "moment" | "own_words";

const FOCUSABLE =
  'button:not([disabled]), textarea:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';

const focusRing =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-light";

const choiceCls = (selected: boolean) =>
  [
    "w-full min-h-[56px] text-left px-4 py-3.5 rounded-xl border text-base font-medium transition-colors",
    selected
      ? "border-forest-mid bg-forest-pale text-forest-dark"
      : "border-cream-muted bg-white text-ink-primary hover:border-forest-light",
    focusRing,
  ].join(" ");

const quietButtonCls = `px-3 py-2 rounded text-sm font-medium text-ink-secondary hover:text-ink-primary transition-colors ${focusRing}`;

const primaryButtonCls = `bg-forest-dark text-white font-semibold px-5 py-2.5 rounded text-sm hover:bg-forest-mid transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${focusRing}`;

export default function CareerMomentDialog({ careerStatus, onNotNow, onClose }: CareerMomentDialogProps) {
  const [step, setStep] = useState<Step>("moment");
  const [moment, setMoment] = useState<CareerMomentOption | null>(null);
  const [ownWords, setOwnWords] = useState("");
  const save = useSaveOnboarding();

  const panelRef = useRef<HTMLDivElement>(null);
  const firstChoiceRef = useRef<HTMLButtonElement>(null);
  const followUpRef = useRef<HTMLButtonElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const titleId = useId();
  const helperId = useId();
  const textareaId = useId();
  const followUpId = useId();

  const hasStatus = Boolean(careerStatus);
  const askingFollowUp = step === "moment" && moment !== null && moment.impliedStatus === null && !hasStatus;

  // Focus follows the step: the first choice, then the follow-up's first
  // answer, then the text box. Restored to whatever had it once the dialog goes.
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    firstChoiceRef.current?.focus();
    return () => previous?.focus?.();
  }, []);
  useEffect(() => {
    if (askingFollowUp) followUpRef.current?.focus();
  }, [askingFollowUp]);
  useEffect(() => {
    if (step === "own_words") textareaRef.current?.focus();
  }, [step]);

  const submitMoment = (update: OnboardingUpdate) => {
    save.mutate(update, {
      onSuccess: () => {
        save.reset();
        setStep("own_words");
      },
    });
  };

  const chooseMoment = (option: CareerMomentOption) => {
    if (save.isPending) return;
    setMoment(option);
    if (option.impliedStatus !== null || hasStatus) {
      submitMoment({ career_moment: option.id });
    } else {
      save.reset();
    }
  };

  const chooseWorkingNow = (status: CareerStatus) => {
    if (!moment || save.isPending) return;
    submitMoment({ career_moment: moment.id, career_status: status });
  };

  const trimmed = ownWords.trim();
  const saveOwnWords = () => {
    if (!trimmed || save.isPending) return;
    save.mutate({ own_words: trimmed }, { onSuccess: () => onClose() });
  };

  const dismiss = () => {
    if (save.isPending) return;
    if (step === "moment") onNotNow();
    else onClose();
  };

  // Esc is "Not now" on step 1 and "Skip" on step 2; Tab stays inside. On the
  // document, not the panel, so a click on the backdrop cannot strand focus
  // outside the trap. Read through a ref so the listener is attached once.
  const dismissRef = useRef(dismiss);
  dismissRef.current = dismiss;
  useEffect(() => {
    const onKeyDown = (e: globalThis.KeyboardEvent) => {
      const panel = panelRef.current;
      if (!panel) return;
      if (e.key === "Escape") {
        e.preventDefault();
        dismissRef.current();
        return;
      }
      if (e.key !== "Tab") return;
      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      const inside = panel.contains(active);
      if (e.shiftKey && (active === first || !inside)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (active === last || !inside)) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  // A fixed line, not the server's text: a 400 here is a client bug, and its
  // error code ("invalid_career_moment") means nothing to the reader.
  const errorText = save.isError ? "We couldn't save that. Please try again." : "";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4 py-4">
      {/* The backdrop does not dismiss: a stray tap is not "Not now". */}
      <div className="absolute inset-0 bg-ink-primary/50" aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={step === "own_words" ? helperId : undefined}
        className="relative z-10 w-full max-w-lg max-h-[calc(100vh-2rem)] overflow-y-auto bg-cream-base rounded-2xl shadow-2xl px-5 py-6 sm:px-7"
      >
        {step === "moment" ? (
          <>
            <h2 id={titleId} className="font-display text-2xl font-bold text-ink-primary">
              What brings you here?
            </h2>
            <p className="text-sm text-ink-secondary mt-1.5">Pick the one that fits best right now.</p>

            <div role="group" aria-labelledby={titleId} className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-3">
              {CAREER_MOMENT_OPTIONS.map((option, index) => (
                <button
                  key={option.id}
                  ref={index === 0 ? firstChoiceRef : undefined}
                  type="button"
                  aria-pressed={moment?.id === option.id}
                  onClick={() => chooseMoment(option)}
                  className={choiceCls(moment?.id === option.id)}
                >
                  {option.label}
                </button>
              ))}
            </div>

            {askingFollowUp && (
              <div role="group" aria-labelledby={followUpId} className="mt-6">
                <p id={followUpId} className="text-base font-semibold text-ink-primary">
                  {WORKING_NOW_QUESTION}
                </p>
                <div className="mt-3 flex flex-col gap-2">
                  {WORKING_NOW_OPTIONS.map((option, index) => (
                    <button
                      key={option.status}
                      ref={index === 0 ? followUpRef : undefined}
                      type="button"
                      onClick={() => chooseWorkingNow(option.status)}
                      className={choiceCls(false)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {errorText && (
              <p role="alert" className="mt-4 text-sm text-red-700">
                {errorText}
              </p>
            )}
            {save.isPending && (
              <p role="status" className="mt-4 text-sm text-ink-secondary">
                Saving…
              </p>
            )}

            <div className="mt-6 flex justify-end">
              <button type="button" onClick={dismiss} className={quietButtonCls}>
                Not now
              </button>
            </div>
          </>
        ) : (
          <>
            <h2 id={titleId} className="font-display text-2xl font-bold text-ink-primary">
              In your own words
            </h2>
            <label htmlFor={textareaId} className="block text-base font-semibold text-ink-primary mt-4">
              What's going on, in a sentence or two?
            </label>
            <p id={helperId} className="text-sm text-ink-secondary mt-1">
              Optional. It stays in your words; we'll show it back to you, and it's never scored.
            </p>
            <textarea
              ref={textareaRef}
              id={textareaId}
              value={ownWords}
              onChange={(e) => setOwnWords(e.target.value)}
              maxLength={OWN_WORDS_MAX_CHARS}
              rows={4}
              aria-describedby={helperId}
              className="mt-3 w-full rounded-lg border border-cream-muted bg-white px-3.5 py-2.5 text-base text-ink-primary placeholder:text-ink-tertiary focus:outline-none focus:ring-2 focus:ring-forest-pale focus:border-forest-light transition-colors"
            />
            <p className="mt-1 text-right text-xs text-ink-tertiary">
              {ownWords.length}/{OWN_WORDS_MAX_CHARS}
            </p>

            {errorText && (
              <p role="alert" className="mt-2 text-sm text-red-700">
                {errorText}
              </p>
            )}

            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={dismiss} className={quietButtonCls}>
                Skip
              </button>
              <button
                type="button"
                onClick={saveOwnWords}
                disabled={!trimmed}
                className={primaryButtonCls}
              >
                {save.isPending ? "Saving…" : "Save"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
