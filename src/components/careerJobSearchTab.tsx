import React, { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { CheckCircle, Send, AlertCircle } from "lucide-react";

// If your project already uses shadcn/ui, uncomment these and remove the simple fallback components below.
// import { Button } from "@/components/ui/button";
// import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
// import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";

/***********************************
 * Lightweight UI fallbacks (no deps)
 ***********************************/
const Button: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement>> = ({ className = "", children, ...props }) => (
  <button
    className={`inline-flex items-center justify-center rounded-2xl px-4 py-2 text-sm font-medium shadow-sm hover:shadow transition-all disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
    {...props}
  >
    {children}
  </button>
);

const Card: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className = "", children, ...props }) => (
  <div className={`rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-neutral-900 shadow-sm ${className}`} {...props}>
    {children}
  </div>
);
const CardHeader: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className = "", children, ...props }) => (
  <div className={`p-4 sm:p-6 border-b border-gray-100 dark:border-neutral-800 ${className}`} {...props}>
    {children}
  </div>
);
const CardTitle: React.FC<React.HTMLAttributes<HTMLHeadingElement>> = ({ className = "", children, ...props }) => (
  <h2 className={`text-xl sm:text-2xl font-semibold tracking-tight ${className}`} {...props}>
    {children}
  </h2>
);
const CardContent: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className = "", children, ...props }) => (
  <div className={`p-4 sm:p-6 ${className}`} {...props}>
    {children}
  </div>
);

/***********************************
 * Data
 ***********************************/

type Question = {
  id: number;
  text: string;
  options: string[];
  section: "Career & Job Search" | "Work Style & Adulting" | "Growth & Identity" | "Networking & Social Life" | "Stress & Balance";
};

const QUESTIONS: Question[] = [
  // Career & Job Search (1-5)
  { id: 1, section: "Career & Job Search", text: "How’s your job search making you feel?", options: [
    "Pumped — I’m lining up interviews",
    "Drained — sending apps into the void",
    "Nervous — interviews stress me out",
    "Avoidant — I’ll deal with it… later",
  ] },
  { id: 2, section: "Career & Job Search", text: "What’s your biggest job hunt anxiety?", options: [
    "Rejection emails",
    "Recruiter ghosting",
    "Saying the wrong thing in interviews",
    "Not finding anything in my field",
  ] },
  { id: 3, section: "Career & Job Search", text: "When you hear “networking,” you think…", options: [
    "Opportunity! Love meeting people",
    "Awkward — small talk panic",
    "Stressful — what if I say something dumb?",
    "Ugh, can’t I just skip this?",
  ] },
  { id: 4, section: "Career & Job Search", text: "Did you do internships in college?", options: [
    "Multiple — I feel prepared",
    "One or two — decent experience",
    "Nope — just school and side hustles",
    "Tried but couldn’t land one (stressful!)",
  ] },
  { id: 5, section: "Career & Job Search", text: "Dream first-job perk?", options: [
    "Remote forever (PJs = uniform)",
    "A snack wall that never runs out",
    "A boss who doesn’t schedule 8 a.m. meetings",
    "Health insurance so I can finally go to the dentist",
  ] },

  // Work Style & Adulting (6-10)
  { id: 6, section: "Work Style & Adulting", text: "Your first-day-on-the-job fear is…", options: [
    "Forgetting everyone’s name in 3 seconds",
    "Accidentally hitting “Reply All” to the whole company",
    "Wearing something way too casual",
    "Sitting at someone else’s desk and not realizing",
  ] },
  { id: 7, section: "Work Style & Adulting", text: "Morning routine as a working adult?", options: [
    "Sunrise yoga + smoothie (who am I kidding?)",
    "Coffee, panic, repeat",
    "Snooze button until the last possible second",
    "Already scrolling Slack before brushing teeth",
  ] },
  { id: 8, section: "Work Style & Adulting", text: "What part of a 9–5 gives you the most anxiety?", options: [
    "Speaking up in meetings",
    "Messing up in front of my boss",
    "Getting stuck doing boring tasks",
    "Honestly… waking up on time",
  ] },
  { id: 9, section: "Work Style & Adulting", text: "What stresses you out most about adulting?", options: [
    "Bills + student loans",
    "Work/life balance",
    "Picking the “right” career path",
    "Feeling behind my peers",
  ] },
  { id: 10, section: "Work Style & Adulting", text: "What’s your “first paycheck” move?", options: [
    "Save like a responsible adult (boring but smart)",
    "Splurge on something I don’t need but desperately want",
    "Pay down loans while crying softly",
    "Celebrate with bottomless brunch + zero regrets",
  ] },

  // Growth & Identity (11-15)
  { id: 11, section: "Growth & Identity", text: "Biggest lesson college left you with?", options: [
    "How to juggle deadlines without losing my mind",
    "Connections matter as much as grades",
    "Balance is harder than it looks",
    "Failure isn’t the end — you bounce back",
  ] },
  { id: 12, section: "Growth & Identity", text: "Your 3-year goal is…", options: [
    "Career growth",
    "Financial independence",
    "Travel + adventure",
    "Honestly, just figuring it out",
  ] },
  { id: 13, section: "Growth & Identity", text: "What’s your growth anxiety?", options: [
    "Wasting time in the wrong job",
    "Falling behind my peers",
    "Not living up to my potential",
    "Needing help but not asking",
  ] },
  { id: 14, section: "Growth & Identity", text: "How do you handle setbacks?", options: [
    "Bounce back fast",
    "Quiet panic, then keep going",
    "Ask for advice/support",
    "Distract myself + avoid",
  ] },
  { id: 15, section: "Growth & Identity", text: "Your “adulting superpower” is…", options: [
    "Stretching $20 across an entire week",
    "Googling how to do literally anything",
    "Making connections out of thin air",
    "Finding side hustles faster than I find clean laundry",
  ] },

  // Networking & Social Life (16-20)
  { id: 16, section: "Networking & Social Life", text: "After work, you’re most likely to…", options: [
    "Networking or happy hour",
    "Side hustle grind",
    "Netflix + sweatpants",
    "Gym or hobbies",
  ] },
  { id: 17, section: "Networking & Social Life", text: "Who do you lean on when anxiety spikes?", options: [
    "Family",
    "Friends",
    "Professors/mentors",
    "The internet",
  ] },
  { id: 18, section: "Networking & Social Life", text: "Alumni networking feels…", options: [
    "Like free career gold",
    "Meh, depends on the school",
    "Awkward but useful",
    "Stressful, so I avoid it",
  ] },
  { id: 19, section: "Networking & Social Life", text: "Your biggest social fear at work?", options: [
    "Not fitting in with coworkers",
    "Saying something dumb",
    "Being left out of things",
    "Having no friends at work",
  ] },
  { id: 20, section: "Networking & Social Life", text: "What kind of work friends do you want?", options: [
    "A tight crew, like college friends",
    "Friendly coworkers, nothing deep",
    "Mentor relationships",
    "Keep work + personal separate",
  ] },

  // Stress & Balance (21-25)
  { id: 21, section: "Stress & Balance", text: "Right now, your #1 stressor is…", options: [
    "Loans + money",
    "Finding a job I actually like",
    "Leaving friends/community behind",
    "Not knowing what’s next",
  ] },
  { id: 22, section: "Stress & Balance", text: "When anxiety hits, what’s your coping move?", options: [
    "Call/text a friend",
    "Hit the gym or take a walk",
    "Netflix + snacks",
    "Shut down + hide",
  ] },
  { id: 23, section: "Stress & Balance", text: "Weekends are for…", options: [
    "Sleeping like a raccoon in daylight",
    "Brunch + mimosas with friends",
    "Netflix + sweatpants (uniform, part two)",
    "Spontaneous adventures I probably can’t afford",
  ] },
  { id: 24, section: "Stress & Balance", text: "How do you feel about moving for a job?", options: [
    "Excited — new adventure!",
    "Nervous but open",
    "Ugh, I want to stay close to home",
    "Only if the paycheck’s big enough",
  ] },
  { id: 25, section: "Stress & Balance", text: "If college was “the bubble,” life now feels…", options: [
    "Scary but exciting",
    "Free and independent",
    "Overwhelming",
    "Still figuring it out",
  ] },
];

/***********************************
 * Utilities
 ***********************************/
const groupBySection = (qs: Question[]) =>
  qs.reduce<Record<string, Question[]>>((acc, q) => {
    (acc[q.section] ||= []).push(q);
    return acc;
  }, {});

/***********************************
 * Component
 ***********************************/
export default function CareerJobSearchTab() {
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [submitted, setSubmitted] = useState(false);
  const [showErrors, setShowErrors] = useState(false);

  const sections = useMemo(() => groupBySection(QUESTIONS), []);
  const total = QUESTIONS.length;
  const countAnswered = Object.keys(answers).length;
  const progress = Math.round((countAnswered / total) * 100);

  const missingIds = useMemo(() => QUESTIONS.filter(q => !answers[q.id]).map(q => q.id), [answers]);

  const onSelect = (id: number, value: string) => {
    setAnswers(a => ({ ...a, [id]: value }));
  };

  const onSubmit = () => {
    if (countAnswered < total) {
      setShowErrors(true);
      setSubmitted(false);
      return;
    }
    setSubmitted(true);
    setShowErrors(false);
  };

  const onReset = () => {
    setAnswers({});
    setSubmitted(false);
    setShowErrors(false);
  };

  return (
    <div className="mx-auto max-w-3xl p-4 sm:p-6">
      <div className="mb-6 flex items-center justify-between gap-3">
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Career & Job Search</h1>
        <div className="text-sm text-gray-600 dark:text-gray-300">{countAnswered}/{total} answered</div>
      </div>

      <Card className="mb-6">
        <CardContent className="py-4">
          <div className="h-2 w-full rounded-full bg-gray-200 dark:bg-neutral-800 overflow-hidden">
            <motion.div
              className="h-full bg-black/80 dark:bg-white/90"
              initial={{ width: 0 }}
              animate={{ width: `${progress}%` }}
              transition={{ type: "spring", stiffness: 120, damping: 20 }}
            />
          </div>
          <div className="mt-2 text-xs text-gray-600 dark:text-gray-300">{progress}% complete</div>
        </CardContent>
      </Card>

      {showErrors && missingIds.length > 0 && (
        <div className="mb-4 flex items-start gap-2 text-amber-700 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 rounded-xl p-3">
          <AlertCircle className="mt-0.5 h-5 w-5" />
          <p className="text-sm">Please answer all questions before submitting. Missing: {missingIds.join(", ")}</p>
        </div>
      )}

      {/* Sections */}
      <div className="space-y-6">
        {Object.entries(sections).map(([sectionName, qs]) => (
          <Card key={sectionName}>
            <CardHeader>
              <CardTitle>{sectionName}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              {qs.map((q) => (
                <div key={q.id} className="space-y-3">
                  <div className="font-medium">{q.id}. {q.text}</div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {q.options.map((opt) => {
                      const checked = answers[q.id] === opt;
                      return (
                        <label key={opt} className={`cursor-pointer rounded-xl border p-3 text-sm transition-all ${checked ? "border-black/80 dark:border-white/80 shadow" : "border-gray-200 dark:border-neutral-800 hover:border-gray-300 dark:hover:border-neutral-700"}`}>
                          <input
                            type="radio"
                            name={`q-${q.id}`}
                            value={opt}
                            checked={checked}
                            onChange={() => onSelect(q.id, opt)}
                            className="hidden"
                          />
                          <div className="flex items-start gap-3">
                            <span className={`mt-0.5 inline-block h-4 w-4 rounded-full border ${checked ? "bg-black/80 dark:bg-white/90 border-black/80 dark:border-white/90" : "border-gray-300 dark:border-neutral-700"}`} />
                            <span>{opt}</span>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Actions */}
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <Button onClick={onSubmit} className="bg-black text-white dark:bg-white dark:text-black">
          <Send className="mr-2 h-4 w-4" /> Submit
        </Button>
        <Button onClick={onReset} className="bg-gray-100 dark:bg-neutral-800">
          Reset
        </Button>
      </div>

      {submitted && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-6"
        >
          <Card className="border-emerald-200 dark:border-emerald-900 bg-emerald-50/60 dark:bg-emerald-900/20">
            <CardContent className="py-6">
              <div className="flex items-start gap-3">
                <CheckCircle className="mt-0.5 h-5 w-5 text-emerald-600" />
                <div>
                  <div className="font-semibold">Thanks for completing the quiz!</div>
                  <p className="text-sm text-gray-700 dark:text-gray-300 mt-1">
                    Your responses are saved in local state for now. Hook the <code className="px-1 py-0.5 rounded bg-gray-100 dark:bg-neutral-800">answers</code> object into your backend to persist results or compute an archetype.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}
    </div>
  );
}

/***********************************
 * Integration Notes
 ***********************************
 * 1) Add a new Tab called "Career & Job Search" in your app's tab router/nav.
 *    Example (React):
 *
 *    import CareerJobSearchTab from "./CareerJobSearchTab";
 *    ...
 *    <Tabs value={activeTab} onValueChange={setActiveTab}>
 *      <TabsList>
 *        <TabsTrigger value="early-career">Early Career</TabsTrigger>
 *        <TabsTrigger value="career-job-search">Career & Job Search</TabsTrigger>
 *      </TabsList>
 *      <TabsContent value="early-career"><EarlyCareerTab /></TabsContent>
 *      <TabsContent value="career-job-search"><CareerJobSearchTab /></TabsContent>
 *    </Tabs>
 *
 * 2) End-of-quiz behavior: This component shows a completion card and, by default,
 *    lets the user navigate to other tabs via your existing nav. If you want an
 *    auto-advance button, add a callback prop like onComplete?.
 *
 * 3) Data access: The user's selected answers live in the `answers` state map.
 *    Wire this into your backend via fetch/axios in `onSubmit()`.
 *
 * 4) Styling: Component uses Tailwind utility classes. If you have shadcn/ui,
 *    replace the simple fallback UI with your imports for Button/Card/etc.
 */
