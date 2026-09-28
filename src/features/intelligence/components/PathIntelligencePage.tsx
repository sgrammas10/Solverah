/**
 * PathIntelligencePage — path suggestions, scored by a job rather than inline.
 *
 * Phase 3c: `GET /me/path-suggestions` fanned out to O*NET *and* OpenAI inside
 * the request. This screen now enqueues `POST /me/path-suggestion-jobs` and
 * polls (A19). The succeeded job's `result` is byte-for-byte what the
 * synchronous GET would have returned, so everything below the fetch is
 * unchanged — including the two failure codes that used to arrive as a 400 and
 * now arrive as a `failed` job carrying the same string in `error`.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../auth";
import { useProfile } from "../../profile";
import {
  isKnownScoringPhase,
  isNarrationPending,
  PATH_NARRATION_MAX_POLLS,
  pathSuggestionJobKeys,
  usePathSuggestionJobStatus,
  useStartPathSuggestionJob,
  type PathSuggestionJobResult,
} from "../usePathSuggestionJob";
import type { PathSuggestionsResponse } from "../types";
import {
  isProfileLevelFailure,
  stateForFailure,
  type FetchState,
} from "../pathFailure";
import {
  useClearPathFeedback,
  usePathFit,
  usePrefetchPathFits,
  useRecordPathFeedback,
  type PathFeedbackMap,
  type PathVerdict,
} from "../usePathFeedback";
import PathSuggestionList from "./PathSuggestionList";
import PathPreferencesForm from "./PathPreferencesForm";
import PathFitPanel from "./PathFitPanel";
import PathWantsPanel from "./PathWantsPanel";
import SkillProficiencyModal from "./SkillProficiencyModal";
import { careerStatusNavState } from "../../../shared/lib/careerStatusReturn";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
//
// `FetchState` and `stateForFailure` moved to `../pathFailure` for F-6. They
// were module-private here, which was right while one screen used them; the
// feedback controls and the deep-fit panel make three call sites, and three
// private copies is how the error vocabulary drifts apart.

/**
 * The job's `result` in the shape this page renders.
 *
 * The generated `PathSuggestionsResponse` is the looser of the two —
 * `suggestions?` optional, `career_status: string` rather than the three-way
 * union — because that is how the API documents it. `types/pathIntelligence.ts`
 * holds the narrower shape the components take, and the synchronous call this
 * replaces asserted it identically with `fetchWithAuth<PathSuggestionsResponse>`.
 */
function asPathSuggestions(result: PathSuggestionJobResult): PathSuggestionsResponse {
  return result as unknown as PathSuggestionsResponse;
}

/**
 * W-16. *current* with the sentences *fresh* has for its still-empty cards.
 *
 * Used for a re-ranked list that came back while the job's narration was still
 * running: the narration fills the server's copy of that list, and this copies
 * the sentences across by code. Card ORDER is always *current*'s -- the list
 * the user is looking at does not move when its sentences land.
 */
function withSentencesFrom(
  current: PathSuggestionsResponse,
  fresh: PathSuggestionsResponse | null
): PathSuggestionsResponse {
  const byCode = new Map((fresh?.suggestions ?? []).map((s) => [s.onet_code, s]));
  return {
    ...current,
    narration_pending: false,
    suggestions: current.suggestions.map((card) => {
      if (card.why_text) return card;
      const written = byCode.get(card.onet_code);
      return written?.why_text
        ? { ...card, why_text: written.why_text, profile_dimensions: written.profile_dimensions ?? [] }
        : card;
    }),
  };
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SkeletonCards() {
  return (
    <div className="space-y-4" aria-label="Loading suggestions">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="rounded-xl border border-cream-muted bg-white px-5 py-5 animate-pulse"
        >
          <div className="h-4 bg-cream-muted rounded w-1/3 mb-3" />
          <div className="h-3 bg-cream-muted rounded w-full mb-2" />
          <div className="h-3 bg-cream-muted rounded w-5/6 mb-4" />
          <div className="flex gap-2">
            <div className="h-5 bg-cream-muted rounded-full w-24" />
            <div className="h-5 bg-cream-muted rounded-full w-32" />
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * Does the profile say where the user is in their career?
 *
 * Mirrors the server's rule (`profile.get("career_status") or
 * derive_career_status(profile)` in intelligence_service): a stored status, or
 * any experience entry ending "Present"/"Current", which the server reads as
 * employed. Checking it on mount is what lets the page ask for the status
 * first, instead of walking the user through skill ratings and preferences
 * only to fail the scoring job on `career_status_not_set` at the end.
 */
function hasCareerStatus(profile: Record<string, unknown> | undefined): boolean {
  const stored = profile?.career_status;
  if (typeof stored === "string" && stored.trim()) return true;
  const experience = profile?.experience;
  if (!Array.isArray(experience)) return false;
  return experience.some((entry) => {
    const end = (entry as { endDate?: unknown } | null)?.endDate;
    return ["present", "current"].includes(String(end ?? "").trim().toLowerCase());
  });
}

// Placeholder — will be replaced by the full component in SOL-31.
function CareerStatusOnboardingPrompt() {
  const navigate = useNavigate();
  const location = useLocation();
  return (
    <div className="rounded-xl border border-cream-muted bg-white px-6 py-8 text-center space-y-4">
      <p className="font-semibold text-ink-primary">Set your career status to get started.</p>
      <p className="text-sm text-ink-secondary leading-relaxed">
        Tell us where you are in your career so we can tailor your path suggestions.
      </p>
      <button
        type="button"
        onClick={() =>
          navigate("/job-seeker/profile?tab=experience", {
            // returnTo: once the status is saved, the profile page offers to
            // bring the user straight back here.
            state: careerStatusNavState(
              location.pathname + location.search,
              "Path Intelligence"
            ),
          })
        }
        className="bg-forest-dark text-white font-semibold px-4 py-2 rounded text-sm hover:bg-forest-mid transition-colors"
      >
        Update Profile
      </button>
    </div>
  );
}

/** Shown before the preferences form to a user with no skills on file: the
 *  scorer needs at least one, so asking for preferences first would only end
 *  at `profile_incomplete`. Best-guess copy; Julie revises. */
function AddSkillsPrompt() {
  return (
    <div className="rounded-xl border border-cream-muted bg-white px-6 py-8 text-center space-y-4">
      <p className="font-semibold text-ink-primary">Add a few skills to get started.</p>
      <p className="text-sm text-ink-secondary leading-relaxed">
        Path Intelligence matches career paths to what you can already do. Add at least
        one skill in the Skills section of your profile's Experience tab, then come back here.
      </p>
      <Link
        to="/job-seeker/profile?tab=experience"
        className="inline-block bg-forest-dark text-white font-semibold px-4 py-2 rounded text-sm hover:bg-forest-mid transition-colors"
      >
        Add skills
      </Link>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

/** The page's screen: every job-lifecycle state, plus `needs_skills`, which is
 *  decided on mount and never by the job. */
type PageState = FetchState | "needs_skills";

export default function PathIntelligencePage() {
  const navigate = useNavigate();
  const { fetchWithAuth } = useAuth();
  const { data: profile, isLoading: profileLoading } = useProfile();
  const experience =
    (profile?.experience as Array<{ position?: string }> | undefined) ?? [];
  const currentTitle = experience[0]?.position ?? null;
  const userSkills = (profile?.["skills"] as string[] | undefined) ?? [];
  const skillLevels = (profile?.["skill_levels"] as Record<string, string> | undefined) ?? {};
  const proficiencyConfirmed = profile?.["skills_proficiency_confirmed"] as boolean | undefined;

  // The preferences form is UI navigation, not job state: it is entered from
  // the mount decision and from "Adjust search preferences", and rendering it
  // takes precedence over whatever the job lifecycle says below.
  const [showPreferences, setShowPreferences] = useState(false);
  const [showProficiencyModal, setShowProficiencyModal] = useState(false);
  const [proficiencySkipped, setProficiencySkipped] = useState(false);
  // Decided once on mount, before anything else: no career status, or no
  // skills, means nothing below can succeed yet, so the page says so up front.
  const [entryGate, setEntryGate] = useState<"career_status" | "skills" | null>(null);
  const hasFiredRef = useRef(false);

  const startSuggestions = useStartPathSuggestionJob();
  const [jobId, setJobId] = useState<string | null>(null);
  const suggestionJob = usePathSuggestionJobStatus(jobId);

  // ---------------------------------------------------------------------
  // F-6: the feedback loop
  // ---------------------------------------------------------------------
  //
  // The re-ranked list arrives in the POST's own response, so it is held here
  // and rendered in place of the job's result. It is NOT merged into the job
  // query's cache: that cache is keyed by job id and describes a scoring run,
  // and a judgement does not make the run have produced something else. A fresh
  // enqueue clears the override, which is the correct precedence — a new
  // scoring is newer than the last re-rank of an older one.
  const [rerank, setRerank] = useState<PathSuggestionsResponse | null>(null);
  const [feedback, setFeedback] = useState<PathFeedbackMap>({});
  const [feedbackError, setFeedbackError] = useState<string | null>(null);
  // Has this session written a judgement? Until it has, the server's map is the
  // truth; after it has, ours is. See `effectiveFeedback`.
  const [feedbackTouched, setFeedbackTouched] = useState(false);

  const recordFeedback = useRecordPathFeedback();
  const clearFeedback = useClearPathFeedback();

  // F-6: the deep fit, opened by a card click. W-9 made it a query keyed by
  // occupation, so reopening a card is free and the cards on screen can be
  // warmed before anybody clicks one.
  const [openCode, setOpenCode] = useState<string | null>(null);
  const pathFit = usePathFit(openCode);
  const prefetchFits = usePrefetchPathFits();

  const fetchSuggestions = useCallback(() => {
    setShowPreferences(false);
    setRerank(null);
    setFeedbackError(null);
    setFeedbackTouched(false);
    startSuggestions.mutate(undefined, {
      // A new enqueue re-keys the poll query, so a stale job's terminal state
      // cannot shadow the fresh run.
      onSuccess: (accepted) => setJobId(accepted.job_id),
    });
  // `startSuggestions` is a stable TanStack Query mutation object; listing it
  // would rebuild this callback on every mutation state change, and the mount
  // effect below depends on it being stable.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const jobData: PathSuggestionsResponse | null =
    suggestionJob.data?.status === "succeeded" && suggestionJob.data.result
      ? asPathSuggestions(suggestionJob.data.result)
      : null;
  const data: PathSuggestionsResponse | null = rerank ?? jobData;

  // Judgements outlive a page load, and the list a returning user is handed was
  // already shaped by them. So the controls start in the state the *server*
  // says, not empty: without this, someone who tapped yesterday would come back
  // to a re-ranked shortlist with no lit buttons and no reset — bent by state
  // they could neither see nor undo. `feedback` on the payload is what carries
  // it; `feedbackTouched` is what stops a DELETE's empty map being overwritten
  // by the stale job result still sitting in the query cache.
  const serverFeedback = (jobData?.feedback ?? {}) as PathFeedbackMap;
  const effectiveFeedback = feedbackTouched ? feedback : serverFeedback;

  // Derived, not stored: the enqueue mutation's phase and the poll's terminal
  // state are the whole of what the old hand-rolled fetchState tracked, and
  // reading them at render time removes the two effects that routed them.
  const jobState: FetchState = (() => {
    if (startSuggestions.isPending) return "loading";
    // A19 gives the enqueue a rate limit the synchronous GET never needed, so
    // a 429 is reachable here and is one of the things "error" renders.
    if (startSuggestions.isError) {
      return stateForFailure(
        startSuggestions.error instanceof Error ? startSuggestions.error.message : ""
      );
    }
    const job = suggestionJob.data;
    // W-16: cards on screen stay on screen. Since the job succeeds as soon as
    // the list is scored, the poll keeps running for the sentences -- and a
    // failed poll THEN (a 429, a blip) must not replace a list the user is
    // reading with an error page. It only stops the shimmer (`narrating`).
    if (job?.status === "succeeded" && job.result) return "success";
    // A rejected poll (404 on a stale handle) is terminal too: the hook has
    // stopped polling, so the skeletons would otherwise never clear.
    if (suggestionJob.error) {
      return stateForFailure(
        suggestionJob.error instanceof Error ? suggestionJob.error.message : ""
      );
    }
    if (job === undefined) return "loading";
    if (job.status === "failed") return stateForFailure(job.error ?? "");
    // Fail closed: the hook has already stopped polling an unrecognised
    // status, so leaving the skeletons up would hang the screen.
    if (!isKnownScoringPhase(job.status)) return "error";
    return "loading";
  })();

  // A deep fit that fails on the *profile* is the same whole-screen condition a
  // feedback failure is, and for the same reason: `profile_incomplete` is not a
  // fact about the card that was clicked. Every other deep-fit code stays in the
  // panel, where the user can close it and keep reading the other nine.
  const fitError =
    pathFit.isError && pathFit.error instanceof Error ? pathFit.error.message : null;

  // A feedback failure that is about the *profile* (`career_status_not_set`,
  // `profile_incomplete`) takes the whole screen, because nine good suggestions
  // are no use to somebody who has to go and fill in their job title. Anything
  // else stays inline next to the controls that caused it — see `feedbackError`.
  const profileLevelFailure = [feedbackError, fitError]
    .filter((message): message is string => typeof message === "string")
    .find(isProfileLevelFailure);
  const feedbackState: FetchState | null = profileLevelFailure
    ? stateForFailure(profileLevelFailure)
    : null;

  const fetchState: PageState =
    entryGate === "career_status"
      ? "career_status_not_set"
      : entryGate === "skills"
        ? "needs_skills"
        : showPreferences
          ? "needs_preferences"
          : feedbackState ?? jobState;

  const feedbackPending = recordFeedback.isPending || clearFeedback.isPending;

  // ---------------------------------------------------------------------
  // W-16: cards first, sentences after
  // ---------------------------------------------------------------------
  //
  // The job's result says `narration_pending` while the server is still writing
  // sentences, and the poll keeps going until it stops saying so. If the poll
  // itself stops first -- an error, or the hook's own cap -- nothing more is
  // coming to this page, so the shimmer stops too: a card never shimmers
  // forever. (The server has its own deadline and normally ends the wait
  // first, with the fallback sentence.)
  //
  // The poll count is read off the query's own state: the render that follows
  // the hook's last permitted poll is the one that sees the cap reached.
  const queryClient = useQueryClient();
  const pollCount =
    (jobId !== null
      ? queryClient.getQueryState(pathSuggestionJobKeys.status(jobId))?.dataUpdateCount
      : 0) ?? 0;
  const pollGaveUp = Boolean(suggestionJob.error) || pollCount >= PATH_NARRATION_MAX_POLLS;
  const jobNarrating = isNarrationPending(suggestionJob.data) && !pollGaveUp;

  // A tap that landed mid-narration came back with its unwritten cards empty
  // and `narration_pending` set. The narration fills the SERVER's copy of that
  // list, so once the job's poll says the narration is over, read the list back
  // once and copy the sentences into the one on screen, in place.
  const rerankWaiting = Boolean(rerank?.narration_pending);
  useEffect(() => {
    if (!rerankWaiting || jobNarrating) return;
    let cancelled = false;
    fetchWithAuth<PathSuggestionsResponse>("/me/path-suggestions", { method: "GET" })
      .then((fresh) => {
        if (!cancelled) setRerank((current) => (current ? withSentencesFrom(current, fresh) : current));
      })
      .catch(() => {
        if (!cancelled) setRerank((current) => (current ? withSentencesFrom(current, null) : current));
      });
    return () => {
      cancelled = true;
    };
  // `fetchWithAuth` is stable for the session; the two flags are the trigger.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rerankWaiting, jobNarrating]);

  const narrating = rerank ? rerankWaiting : jobNarrating;
  const shownSuggestions = (data?.suggestions ?? []).map((suggestion) =>
    narrating && !suggestion.why_text ? { ...suggestion, sentence_pending: true } : suggestion
  );

  /**
   * Record a verdict and swap in the list the server ranks from it.
   *
   * **Optimistic, and only as optimistic as it can honestly be.** The client
   * cannot predict a Rocchio re-rank, so it does not try: what it predicts is
   * the one part it knows for certain — a card called `too_similar` or
   * `not_for_me` is gone, a card called `interesting` stays and its button
   * lights up. Guessing an order and then correcting it a second later would
   * make the list jump twice for no added responsiveness.
   *
   * On failure the predicted removal is reverted and the error panel appears;
   * the previous list and the previous verdict map both come back, so a failed
   * tap leaves no trace.
   */
  const handleVerdict = useCallback(
    (onetCode: string, verdict: PathVerdict) => {
      // `rerank`, not `data`: restoring `data` on failure would pin the job's
      // own result into the override slot, and a later poll update would then be
      // shadowed by a copy of itself. The revert has to put back the state that
      // was there, not a value equal to what it rendered.
      const previousRerank = rerank;
      const previousFeedback = effectiveFeedback;
      setFeedbackError(null);
      setFeedbackTouched(true);
      setFeedback({ ...previousFeedback, [onetCode]: verdict });
      if (data && verdict !== "interesting") {
        setRerank({
          ...data,
          suggestions: data.suggestions.filter((s) => s.onet_code !== onetCode),
        });
      }

      recordFeedback.mutate(
        { onet_code: onetCode, verdict },
        {
          onSuccess: (result) => {
            setRerank(result as unknown as PathSuggestionsResponse);
            setFeedback((result.feedback ?? {}) as PathFeedbackMap);
          },
          onError: (error) => {
            setRerank(previousRerank);
            setFeedback(previousFeedback);
            setFeedbackError(error instanceof Error ? error.message : "");
          },
        },
      );
    },
    [data, rerank, effectiveFeedback, recordFeedback],
  );

  const handleClearFeedback = useCallback(() => {
    const previousRerank = rerank;
    const previousFeedback = effectiveFeedback;
    setFeedbackError(null);
    setFeedbackTouched(true);
    clearFeedback.mutate(undefined, {
      onSuccess: (result) => {
        setRerank(result as unknown as PathSuggestionsResponse);
        setFeedback({});
      },
      onError: (error) => {
        setRerank(previousRerank);
        setFeedback(previousFeedback);
        setFeedbackError(error instanceof Error ? error.message : "");
      },
    });
  }, [rerank, effectiveFeedback, clearFeedback]);

  // Opening a card is now state and nothing else: the query below it fires on
  // the code, and if the card was prefetched there is nothing to fire.
  const openFit = useCallback((onetCode: string) => setOpenCode(onetCode), []);

  const openTitle =
    data?.suggestions.find((s) => s.onet_code === openCode)?.title ?? "this path";

  const proceedAfterProficiency = useCallback(() => {
    if (!profile?.path_preferences) {
      setShowPreferences(true);
    } else {
      fetchSuggestions();
    }
  }, [profile, fetchSuggestions]);

  const saveProficiency = useMutation({
    // PUT, not PATCH: the write replaces the whole ratings map rather than
    // merging into it, and Phase 1b made the verb match what happens.
    mutationFn: (levels: Record<string, string>) =>
      fetchWithAuth("/me/skills", {
        method: "PUT",
        body: JSON.stringify({
          skills: Object.entries(levels).map(([name, proficiency]) => ({
            name,
            proficiency,
          })),
        }),
      }),
  });

  const handleProficiencySave = (levels: Record<string, string>) => {
    saveProficiency.mutate(levels, {
      // onSettled, not onSuccess: a failed save is non-fatal — proceed anyway
      // so the user isn't blocked, exactly as the swallowed catch did.
      onSettled: () => {
        setShowProficiencyModal(false);
        proceedAfterProficiency();
      },
    });
  };

  const handleProficiencySkip = () => {
    setShowProficiencyModal(false);
    setProficiencySkipped(true);
    proceedAfterProficiency();
  };

  useEffect(() => {
    // Every branch below reads the profile document. Running before it arrives
    // would see no skills and no path_preferences and send a user who has both
    // to the preferences form -- the failure this gate exists to prevent.
    // The gate covers in-flight only; a failed fetch is handled upstream by
    // useProfile's throwOnError, which routes it to RouteErrorBoundary rather
    // than letting this effect read `undefined` as "has no preferences".
    if (profileLoading) return;
    if (!hasFiredRef.current) {
      hasFiredRef.current = true;
      if (!hasCareerStatus(profile)) {
        // First, because every later step is wasted without it: the scoring
        // job would fail on `career_status_not_set` after the user had rated
        // skills and answered preferences.
        setEntryGate("career_status");
      } else if (userSkills.length === 0) {
        setEntryGate("skills");
      } else if (proficiencyConfirmed !== true) {
        setShowProficiencyModal(true);
        // Don't decide a screen here — the modal controls what happens next
      } else if (!profile?.path_preferences) {
        setShowPreferences(true);
      } else {
        fetchSuggestions();
      }
    }
  // Runs once the profile settles; hasFiredRef guards against Strict Mode's
  // double-invoke and against a later re-render firing it again.
  }, [profileLoading]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      {showProficiencyModal && (
        <SkillProficiencyModal
          skills={userSkills}
          initialLevels={skillLevels}
          saving={saveProficiency.isPending}
          onSave={handleProficiencySave}
          onSkip={handleProficiencySkip}
        />
      )}

      {/* The deep fit, opened by a card click (F-5's endpoint, F-6's wiring).
          Closed when the failure is a profile-level one: that has already taken
          the whole screen, and a panel over a "complete your profile" prompt
          would be two answers to one question. */}
      {openCode && !feedbackState && (
        <PathFitPanel
          title={openTitle}
          fit={pathFit.data}
          pending={pathFit.isPending}
          errorCode={fitError}
          // Closing clears nothing, deliberately (W-9). Each occupation has its
          // own cache entry, so the next card cannot inherit this one's error --
          // and dropping queries here could tear down a prefetch another card is
          // waiting on.
          onClose={() => setOpenCode(null)}
          onRetry={pathFit.retry}
        />
      )}

      <div className="min-h-screen bg-cream-base">
        <div className="mx-auto max-w-2xl px-6 pt-12 pb-20 space-y-8">

          {/* Header */}
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
                Path Intelligence
              </p>
              <span className="rounded-full bg-forest-pale border border-forest-light px-2 py-0.5 text-xs font-semibold text-forest-mid">
                Pro · coming soon
              </span>
            </div>
            <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
              Your Career Paths
            </h1>
            <p className="text-sm text-ink-secondary pt-1">
              {/* W-13. "scored against" was the page telling the user there is
                  a score, on the one screen ruling flag 12 says must not show
                  one. Best-guess copy; Julie revises on the built product. */}
              Career paths matched to your skills and work profile, with plain-language
              guidance on why each one fits.
            </p>
          </div>

          {/* Nudge banner — shown when user skipped the proficiency modal */}
          {proficiencySkipped && fetchState === "success" && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-3 flex items-center justify-between gap-4">
              <p className="text-sm text-amber-800">
                Rate your skills to get more accurate career matches.
              </p>
              <button
                type="button"
                onClick={() => setShowProficiencyModal(true)}
                className="shrink-0 text-xs font-semibold text-amber-800 underline hover:text-amber-900 transition-colors"
              >
                Rate skills
              </button>
            </div>
          )}

          {/* Preferences intake */}
          {fetchState === "needs_preferences" && (
            <PathPreferencesForm onComplete={() => fetchSuggestions()} />
          )}

          {/* W-5: what should change about the job they have now.
              Above the results and never in front of them: it renders while the
              job is still scoring as well as after it lands, so pressing
              "Update my suggestions" does not make the control that is working
              disappear behind its own skeletons. It renders nothing at all for
              a user with no current job, and nothing while its own request is
              in flight or if that request fails — the page below is unaffected
              either way (design doc §8.3, ⚑7). */}
          {(fetchState === "loading" || fetchState === "success") && (
            <PathWantsPanel
              onSaved={fetchSuggestions}
              rescoring={fetchState === "loading"}
            />
          )}

          {/* Loading */}
          {fetchState === "loading" && <SkeletonCards />}

          {/* Error */}
          {fetchState === "error" && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
              <p className="font-medium mb-1">
                We couldn't load your path suggestions right now.
              </p>
              <p className="text-xs">Please try again in a moment.</p>
              <button
                type="button"
                onClick={fetchSuggestions}
                className="mt-3 text-xs font-semibold text-red-700 underline"
              >
                Try again
              </button>
            </div>
          )}

          {/* No skills on file */}
          {fetchState === "needs_skills" && <AddSkillsPrompt />}

          {/* Career status not set */}
          {fetchState === "career_status_not_set" && <CareerStatusOnboardingPrompt />}

          {/* Profile too sparse to score */}
          {fetchState === "profile_incomplete" && (
            <div className="rounded-xl border border-cream-muted bg-white px-6 py-8 text-center space-y-4">
              <p className="font-semibold text-ink-primary">Add a job title and a few skills to get started.</p>
              <p className="text-sm text-ink-secondary leading-relaxed">
                Path Intelligence needs your current (or most recent) job title and at least one skill to find matching career paths.
              </p>
              <button
                type="button"
                onClick={() => navigate("/job-seeker/profile?tab=experience")}
                className="bg-forest-dark text-white font-semibold px-4 py-2 rounded text-sm hover:bg-forest-mid transition-colors"
              >
                Complete Your Profile
              </button>
            </div>
          )}

          {/* Success */}
          {fetchState === "success" && data && (
            <>
              {/* A feedback failure that is not about the profile stays here,
                  beside the controls that caused it, rather than replacing the
                  list — the suggestions on screen are still good ones and the
                  user has not lost anything but the tap. */}
              {feedbackError && !feedbackState && (
                <div
                  role="alert"
                  className="rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700"
                >
                  <p className="font-medium mb-1">
                    We couldn't save that just now.
                  </p>
                  <p className="text-xs">Your suggestions haven't changed.</p>
                  <button
                    type="button"
                    onClick={() => setFeedbackError(null)}
                    className="mt-3 text-xs font-semibold text-red-700 underline"
                  >
                    Try again
                  </button>
                </div>
              )}

              <PathSuggestionList
                suggestions={shownSuggestions}
                currentTitle={currentTitle}
                careerStatus={data.career_status}
                onOpen={openFit}
                // W-9: warm the three cards that are on screen. Silent, once
                // per code, and fired from the list's own effect so it cannot
                // delay the list.
                onVisibleCodes={prefetchFits}
                feedback={effectiveFeedback}
                onVerdict={handleVerdict}
                feedbackPending={feedbackPending}
              />

              {Object.keys(effectiveFeedback).length > 0 && (
                <div className="flex items-center justify-between gap-4 rounded-xl border border-cream-muted bg-white px-5 py-3">
                  <p className="text-xs text-ink-secondary">
                    These paths are shaped by what you've told us.
                  </p>
                  <button
                    type="button"
                    onClick={handleClearFeedback}
                    disabled={feedbackPending}
                    className="shrink-0 text-xs font-semibold text-forest-mid underline hover:text-forest-dark transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    Start over
                  </button>
                </div>
              )}

              <div className="flex items-center justify-between pt-2">
                <button
                  type="button"
                  onClick={() => setShowProficiencyModal(true)}
                  className="text-xs text-ink-secondary underline hover:text-ink-primary transition-colors"
                >
                  Edit skill ratings
                </button>
                <button
                  type="button"
                  onClick={() => setShowPreferences(true)}
                  className="text-xs text-ink-secondary underline hover:text-ink-primary transition-colors"
                >
                  Adjust search preferences
                </button>
              </div>
            </>
          )}

        </div>
      </div>
    </>
  );
}
