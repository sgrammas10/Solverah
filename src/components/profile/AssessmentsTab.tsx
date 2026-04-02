import { Brain } from "lucide-react";
import { Link } from "react-router-dom";
import { ProfileFormData } from "../../types/profile";

type Props = {
  formData: ProfileFormData;
};

const quizCards = [
  {
    id: "earlyCareer",
    group: "careerQuizzes",
    title: "Early Career",
    description: "Explore your motivations, feedback preferences, and ideal early-career environment.",
    path: "/career-quizzes/early-career",
    wide: false,
  },
  {
    id: "careerTransition",
    group: "careerQuizzes",
    title: "Career Transition",
    description: "Clarify what you want to leave behind and what success looks like in your next chapter.",
    path: "/career-quizzes/career-transition",
    wide: false,
  },
  {
    id: "careerJobSearch",
    group: null,
    title: "Career & Job Search",
    description: "A reflection-based quiz for graduates and early-career professionals navigating their next chapter.",
    path: "/career-job-search",
    wide: false,
  },
  {
    id: "midCareer",
    group: "careerQuizzes",
    title: "Mid-Career / Strategic",
    description: "Define your leadership legacy, strategic growth areas, and ideal team environment.",
    path: "/career-quizzes/mid-career",
    wide: false,
  },
  {
    id: "teenFocused",
    group: "careerQuizzes",
    title: "Your Future, Your Way (Teen-Focused)",
    description: "A fun, teen-focused quiz that helps you explore interests, personality, and future goals in an engaging way.",
    path: "/career-quizzes/teen-focused",
    wide: true,
  },
];

export default function AssessmentsTab({ formData }: Props) {
  const hasResult = (group: string | null, id: string): boolean => {
    if (group) {
      return !!(formData.quizResults as any)?.[group]?.[id];
    }
    return !!formData.quizResults?.[id];
  };

  const insightsPath = (group: string | null): string =>
    group ? `/quiz-insights?group=${group}` : "/quiz-insights";

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl shadow-sm border border-cream-muted p-6">
        <h2 className="text-lg font-semibold text-ink-primary font-display mb-4">
          Solverah Career &amp; Psychometric Quizzes
        </h2>
        <p className="text-ink-secondary mb-6">
          Explore our curated set of quizzes to uncover your strengths, personality traits, and career
          motivations. Your responses will be automatically saved to your profile.
        </p>

        <div className="grid md:grid-cols-2 gap-6">
          {quizCards.map((card) => {
            const completed = hasResult(card.group, card.id);
            return (
              <div
                key={card.id}
                className={`border border-cream-muted rounded-xl p-5 bg-white hover:border-forest-pale transition-colors${card.wide ? " md:col-span-2" : ""}`}
              >
                <h3 className="text-lg font-semibold text-ink-primary font-display mb-2">{card.title}</h3>
                <p className="text-sm text-ink-secondary mb-4">{card.description}</p>
                <div className="flex flex-wrap gap-2">
                  <Link
                    to={card.path}
                    className="inline-block px-4 py-2 bg-forest-dark text-white rounded-md hover:bg-forest-mid text-sm"
                  >
                    {completed ? "View Answers" : "Start Quiz"}
                  </Link>
                  {completed && (
                    <Link
                      to={insightsPath(card.group)}
                      className="inline-block px-4 py-2 border border-forest-pale text-forest-mid rounded-md hover:bg-forest-pale text-sm"
                    >
                      View Insights
                    </Link>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-8 p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-center gap-4">
          <Brain className="h-5 w-5 text-amber-600 shrink-0" />
          <div className="flex-1">
            <h3 className="font-semibold text-amber-900">Complete Your Assessments</h3>
            <p className="text-sm text-amber-800 mt-0.5">
              Taking these quizzes will improve your personalized job matching accuracy and help you stand out to employers.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
