import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/useAuth";
import { useProfile } from "../hooks/useProfile";
import type { PathSuggestionsResponse } from "../types/pathIntelligence";
import PathSuggestionList from "../components/PathIntelligence/PathSuggestionList";
import PathPreferencesForm from "../components/PathIntelligence/PathPreferencesForm";
import SkillProficiencyModal from "../components/PathIntelligence/SkillProficiencyModal";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type FetchState = "loading" | "error" | "career_status_not_set" | "profile_incomplete" | "needs_preferences" | "success";

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

// Placeholder — will be replaced by the full component in SOL-31.
function CareerStatusOnboardingPrompt() {
  const navigate = useNavigate();
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
            state: { showCareerStatusModal: true },
          })
        }
        className="bg-forest-dark text-white font-semibold px-4 py-2 rounded text-sm hover:bg-forest-mid transition-colors"
      >
        Update Profile
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

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

  const [fetchState, setFetchState] = useState<FetchState>("loading");
  const [data, setData] = useState<PathSuggestionsResponse | null>(null);
  const [showProficiencyModal, setShowProficiencyModal] = useState(false);
  const [proficiencySaving, setProficiencySaving] = useState(false);
  const [proficiencySkipped, setProficiencySkipped] = useState(false);
  const hasFiredRef = useRef(false);

  const fetchSuggestions = useCallback(async () => {
    setFetchState("loading");
    try {
      const result = await fetchWithAuth<PathSuggestionsResponse>(
        "/me/path-suggestions"
      );
      setData(result);
      setFetchState("success");
    } catch (err) {
      if (err instanceof Error && err.message === "career_status_not_set") {
        setFetchState("career_status_not_set");
      } else if (err instanceof Error && err.message === "profile_incomplete") {
        setFetchState("profile_incomplete");
      } else {
        setFetchState("error");
      }
    }
  }, [fetchWithAuth]);

  const proceedAfterProficiency = useCallback(() => {
    if (!profile?.path_preferences) {
      setFetchState("needs_preferences");
    } else {
      fetchSuggestions();
    }
  }, [profile, fetchSuggestions]);

  const handleProficiencySave = async (levels: Record<string, string>) => {
    setProficiencySaving(true);
    try {
      // PUT, not PATCH: the write replaces the whole ratings map rather than
      // merging into it, and Phase 1b made the verb match what happens.
      await fetchWithAuth("/me/skills", {
        method: "PUT",
        body: JSON.stringify({
          skills: Object.entries(levels).map(([name, proficiency]) => ({
            name,
            proficiency,
          })),
        }),
      });
    } catch {
      // Non-fatal — proceed anyway so the user isn't blocked
    } finally {
      setProficiencySaving(false);
    }
    setShowProficiencyModal(false);
    proceedAfterProficiency();
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
      if (userSkills.length > 0 && proficiencyConfirmed !== true) {
        setShowProficiencyModal(true);
        // Don't set fetchState here — modal controls what happens next
      } else if (!profile?.path_preferences) {
        setFetchState("needs_preferences");
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
          saving={proficiencySaving}
          onSave={handleProficiencySave}
          onSkip={handleProficiencySkip}
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
                Pro
              </span>
            </div>
            <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
              Your Career Paths
            </h1>
            <p className="text-sm text-ink-secondary pt-1">
              Career paths scored against your skills and work profile, with plain-language
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
              <PathSuggestionList
                suggestions={data.suggestions}
                currentTitle={currentTitle}
                careerStatus={data.career_status}
              />
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
                  onClick={() => setFetchState("needs_preferences")}
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
