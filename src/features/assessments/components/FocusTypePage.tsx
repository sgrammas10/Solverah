import { useState, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../../auth";
import { useProfile, useProfileActions } from "../../profile";
import Scene1 from "./focustype/Scene1";
import Scene2 from "./focustype/Scene2";
import Scene3 from "./focustype/Scene3";
import Scene4 from "./focustype/Scene4";
import Scene5 from "./focustype/Scene5";
import HeroNetworkAnimation from "../../../shared/ui/HeroNetworkAnimation";
import ResumePrompt from "../../../shared/ui/ResumePrompt";
import { firstUnansweredIndex, useResumePrompt } from "../../../shared/lib/resumeDraft";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Scene1Payload = string[];
type Scene2Payload = { now: string[]; later: string[]; ignore: string[] };
type Scene3Payload = {
  deep_solo: number;
  planning: number;
  social: number;
  breaks: number;
  exploring: number;
};
type Scene4Payload = {
  now: string[];
  tomorrow: string[];
  avg_decision_time_ms: number;
};
type Scene5Payload = string[];

interface ScenePayloads {
  scene_1?: Scene1Payload;
  scene_2?: Scene2Payload;
  scene_3?: Scene3Payload;
  scene_4?: Scene4Payload;
  scene_5?: Scene5Payload;
}

export interface FocusTypeResult {
  archetype: string;
  dimension_scores: Record<string, number>;
  recommendations: string[];
}

// ---------------------------------------------------------------------------
// Draft persistence -- sessionStorage, like every other quiz's in-progress
// answers, so a reload mid-simulator no longer throws finished scenes away.
// ---------------------------------------------------------------------------

export const FOCUS_TYPE_DRAFT_KEY = "focus_type_draft";
const SCENE_NUMBERS = [1, 2, 3, 4, 5] as const;

function readDraft(): ScenePayloads {
  try {
    const raw = sessionStorage.getItem(FOCUS_TYPE_DRAFT_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return parsed as ScenePayloads;
  } catch {
    return {};
  }
}

function writeDraft(payloads: ScenePayloads) {
  try {
    sessionStorage.setItem(FOCUS_TYPE_DRAFT_KEY, JSON.stringify(payloads));
  } catch {
    // A full or disabled sessionStorage costs the resume and nothing else.
  }
}

function clearDraft() {
  try {
    sessionStorage.removeItem(FOCUS_TYPE_DRAFT_KEY);
  } catch {
    // As above.
  }
}

function hasScene(payloads: ScenePayloads, n: number): boolean {
  return payloads[`scene_${n}` as keyof ScenePayloads] !== undefined;
}

/** `submitting` and `error` are no longer members: the POST lives on a
 *  mutation, whose isPending/isError carry those two screens. */
type Phase = "intro" | "scenes";

// ---------------------------------------------------------------------------
// Progress indicator
// ---------------------------------------------------------------------------

function SceneIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center gap-3">
      <p className="text-xs font-semibold uppercase tracking-widest text-ink-tertiary">
        Scene {current} of {total}
      </p>
      <div className="flex gap-1.5">
        {Array.from({ length: total }, (_, i) => (
          <div
            key={i}
            className={`h-1 rounded-full transition-all duration-300 ${
              i < current ? "w-5 bg-forest-dark" : "w-5 bg-cream-muted"
            }`}
          />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function FocusTypePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const isRetake = (location.state as { retake?: boolean } | null)?.retake === true;
  const { fetchWithAuth } = useAuth();
  const { updateProfileData } = useProfileActions();
  const { data: profile, isLoading: profileLoading } = useProfile();

  const [phase, setPhase] = useState<Phase>("intro");
  const [currentScene, setCurrentScene] = useState(1);
  // A retake starts clean; anything else picks up the stored draft (if any),
  // and the resume prompt below decides what happens to it.
  const [scenePayloads, setScenePayloads] = useState<ScenePayloads>(() => {
    if (isRetake) {
      clearDraft();
      return {};
    }
    return readDraft();
  });
  const draftSceneCount = SCENE_NUMBERS.filter((n) => hasScene(scenePayloads, n)).length;
  const { showResumePrompt, dismissResumePrompt } = useResumePrompt(
    () => draftSceneCount > 0
  );

  const savedResult = profile?.focus_type_result as FocusTypeResult | undefined;
  useEffect(() => {
    if (savedResult && !isRetake) {
      navigate("/focus-type/results", { replace: true, state: { result: savedResult } });
    }
  }, [savedResult, isRetake, navigate]);

  const submitMutation = useMutation({
    mutationFn: (payloads: ScenePayloads) =>
      fetchWithAuth<FocusTypeResult>("/assessments/focus_type/submissions", {
        method: "POST",
        body: JSON.stringify(payloads),
      }),
    onSuccess: (result) => {
      clearDraft();
      updateProfileData({ focus_type_result: result });
      navigate("/focus-type/results", { state: { result } });
    },
  });

  const submit = (payloads: ScenePayloads) => {
    // isPending replaces the hasFiredRef double-fire guard; a failed attempt
    // clears it, so the error screen's retry can go again.
    if (submitMutation.isPending) return;
    submitMutation.mutate(payloads);
  };

  function handleSceneComplete(sceneNum: number, payload: unknown) {
    const key = `scene_${sceneNum}` as keyof ScenePayloads;
    const updated = { ...scenePayloads, [key]: payload } as ScenePayloads;
    setScenePayloads(updated);
    writeDraft(updated);

    if (sceneNum < 5) {
      setCurrentScene(sceneNum + 1);
    } else {
      submit(updated);
    }
  }

  function handleResume() {
    dismissResumePrompt();
    const allDone = SCENE_NUMBERS.every((n) => hasScene(scenePayloads, n));
    if (allDone) {
      // Every scene was finished but the submit never landed (a reload in the
      // gap): send it rather than replay the last scene.
      submit(scenePayloads);
      return;
    }
    const idx = firstUnansweredIndex(SCENE_NUMBERS, (n) => hasScene(scenePayloads, n));
    setCurrentScene(SCENE_NUMBERS[idx]);
    setPhase("scenes");
  }

  function handleStartOver() {
    clearDraft();
    setScenePayloads({});
    setCurrentScene(1);
    setPhase("scenes");
    dismissResumePrompt();
  }

  // ── Submitting ──
  if (submitMutation.isPending) {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">Calculating your FocusType…</p>
      </div>
    );
  }

  // ── Error ──
  if (submitMutation.isError) {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div className="max-w-sm w-full rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
          <p className="font-medium mb-1">Something went wrong submitting your results.</p>
          <p className="text-xs">Please try again — your scene answers are still saved.</p>
          <button
            type="button"
            onClick={() => submit(scenePayloads)}
            className="mt-3 text-xs font-semibold text-red-700 underline"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  // ── Waiting on the profile document ──
  // A user who has already taken FocusType is redirected by the effect above,
  // but only once the document arrives. Rendering the intro in the meantime
  // would flash "Begin" at someone about to be sent to their results.
  // A failed fetch does not fall through to the intro either — useProfile
  // throws to RouteErrorBoundary rather than reporting an empty document.
  if (phase === "intro" && profileLoading) {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
      </div>
    );
  }

  // ── A saved draft: ask before resuming ──
  if (phase === "intro" && showResumePrompt && !(savedResult && !isRetake)) {
    return (
      <div className="min-h-screen bg-cream-base">
        <div className="mx-auto max-w-lg px-6 pt-16 pb-20">
          <ResumePrompt
            title="FocusType™"
            answeredCount={draftSceneCount}
            total={SCENE_NUMBERS.length}
            unit="scene"
            onResume={handleResume}
            onStartOver={handleStartOver}
          />
        </div>
      </div>
    );
  }

  // ── Intro ──
  if (phase === "intro") {
    return (
      <div className="min-h-screen bg-cream-base">
        <div className="mx-auto max-w-lg px-6 pt-16 pb-20">
          <div className="space-y-8">
            {/* Eyebrow */}
            <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
              FocusType™
            </p>

            {/* Headline */}
            <div className="space-y-4">
              <h1 className="font-display text-3xl sm:text-4xl font-semibold text-ink-primary leading-tight">
                Discover how you actually focus.
              </h1>
              <p className="text-base text-ink-secondary leading-relaxed">
                Most people don't know how their attention really works — they just
                adapt to whatever environment they're placed in. FocusType is a
                five-scene workday simulator that reveals your natural focus patterns,
                energy rhythms, and the conditions where you do your best work.
              </p>
              <p className="text-base text-ink-secondary leading-relaxed">
                You'll move through five short interactive scenes — no questions,
                just decisions. Your behaviour across all five produces one of six
                FocusType archetypes.
              </p>
            </div>

            {/* Disclaimer */}
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
              <p className="text-sm font-semibold text-amber-800">
                Each choice is final. There's no going back.
              </p>
              <p className="text-xs text-amber-700 mt-1">
                Each scene commits when you complete it — treat every decision as real.
              </p>
            </div>

            {/* Time estimate */}
            <p className="text-xs text-ink-tertiary flex items-center gap-1.5">
              <span>⏱</span>
              Takes about 4 minutes
            </p>

            {/* CTA */}
            <button
              type="button"
              onClick={() => setPhase("scenes")}
              className="w-full bg-forest-dark text-white font-semibold py-4 rounded hover:bg-forest-mid transition-colors text-base"
            >
              Begin
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Scenes ──
  return (
    <div className="relative min-h-screen bg-cream-base overflow-hidden">
      <HeroNetworkAnimation theme="light" />
      <div className="relative z-10 mx-auto max-w-2xl px-6 pt-10 pb-20 space-y-8">
        {/* Progress */}
        <SceneIndicator current={currentScene} total={5} />

        {/* Scene content */}
        {currentScene === 1 && (
          <Scene1 onComplete={(p) => handleSceneComplete(1, p)} />
        )}
        {currentScene === 2 && (
          <Scene2 onComplete={(p) => handleSceneComplete(2, p)} />
        )}
        {currentScene === 3 && (
          <Scene3 onComplete={(p) => handleSceneComplete(3, p)} />
        )}
        {currentScene === 4 && (
          <Scene4 onComplete={(p) => handleSceneComplete(4, p)} />
        )}
        {currentScene === 5 && (
          <Scene5 onComplete={(p) => handleSceneComplete(5, p)} />
        )}
      </div>
    </div>
  );
}
