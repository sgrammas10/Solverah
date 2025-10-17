import { useState } from "react";

type Question = {
  id: number;
  text: string;
  options: string[];
};

const sections: { title: string; startId: number; questions: Question[] }[] = [
  {
    title: "Career & Job Search",
    startId: 1,
    questions: [
      {
        id: 1,
        text: "How’s your job search making you feel?",
        options: [
          "Pumped — I’m lining up interviews",
          "Drained — sending apps into the void",
          "Nervous — interviews stress me out",
          "Avoidant — I’ll deal with it… later",
        ],
      },
      {
        id: 2,
        text: "What’s your biggest job hunt anxiety?",
        options: [
          "Rejection emails",
          "Recruiter ghosting",
          "Saying the wrong thing in interviews",
          "Not finding anything in my field",
        ],
      },
      {
        id: 3,
        text: "When you hear “networking,” you think…",
        options: [
          "Opportunity! Love meeting people",
          "Awkward — small talk panic",
          "Stressful — what if I say something dumb?",
          "Ugh, can’t I just skip this?",
        ],
      },
      {
        id: 4,
        text: "Did you do internships in college?",
        options: [
          "Multiple — I feel prepared",
          "One or two — decent experience",
          "Nope — just school and side hustles",
          "Tried but couldn’t land one (stressful!)",
        ],
      },
      {
        id: 5,
        text: "Dream first-job perk?",
        options: [
          "Remote forever (PJs = uniform)",
          "A snack wall that never runs out",
          "A boss who doesn’t schedule 8 a.m. meetings",
          "Health insurance so I can finally go to the dentist",
        ],
      },
    ],
  },
  {
    title: "Work Style & Adulting",
    startId: 6,
    questions: [
      {
        id: 6,
        text: "Your first-day-on-the-job fear is…",
        options: [
          "Forgetting everyone’s name in 3 seconds",
          "Accidentally hitting “Reply All” to the whole company",
          "Wearing something way too casual",
          "Sitting at someone else’s desk and not realizing",
        ],
      },
      {
        id: 7,
        text: "Morning routine as a working adult?",
        options: [
          "Sunrise yoga + smoothie (who am I kidding?)",
          "Coffee, panic, repeat",
          "Snooze button until the last possible second",
          "Already scrolling Slack before brushing teeth",
        ],
      },
      {
        id: 8,
        text: "What part of a 9–5 gives you the most anxiety?",
        options: [
          "Speaking up in meetings",
          "Messing up in front of my boss",
          "Getting stuck doing boring tasks",
          "Honestly… waking up on time",
        ],
      },
      {
        id: 9,
        text: "What stresses you out most about adulting?",
        options: [
          "Bills + student loans",
          "Work/life balance",
          "Picking the “right” career path",
          "Feeling behind my peers",
        ],
      },
      {
        id: 10,
        text: "What’s your “first paycheck” move?",
        options: [
          "Save like a responsible adult (boring but smart)",
          "Splurge on something I don’t need but desperately want",
          "Pay down loans while crying softly",
          "Celebrate with bottomless brunch + zero regrets",
        ],
      },
    ],
  },
  {
    title: "Growth & Identity",
    startId: 11,
    questions: [
      {
        id: 11,
        text: "Biggest lesson college left you with?",
        options: [
          "How to juggle deadlines without losing my mind",
          "Connections matter as much as grades",
          "Balance is harder than it looks",
          "Failure isn’t the end — you bounce back",
        ],
      },
      {
        id: 12,
        text: "Your 3-year goal is…",
        options: [
          "Career growth",
          "Financial independence",
          "Travel + adventure",
          "Honestly, just figuring it out",
        ],
      },
      {
        id: 13,
        text: "What’s your growth anxiety?",
        options: [
          "Wasting time in the wrong job",
          "Falling behind my peers",
          "Not living up to my potential",
          "Needing help but not asking",
        ],
      },
      {
        id: 14,
        text: "How do you handle setbacks?",
        options: [
          "Bounce back fast",
          "Quiet panic, then keep going",
          "Ask for advice/support",
          "Distract myself + avoid",
        ],
      },
      {
        id: 15,
        text: "Your “adulting superpower” is…",
        options: [
          "Stretching $20 across an entire week",
          "Googling how to do literally anything",
          "Making connections out of thin air",
          "Finding side hustles faster than I find clean laundry",
        ],
      },
    ],
  },
  {
    title: "Networking & Social Life",
    startId: 16,
    questions: [
      {
        id: 16,
        text: "After work, you’re most likely to…",
        options: [
          "Networking or happy hour",
          "Side hustle grind",
          "Netflix + sweatpants",
          "Gym or hobbies",
        ],
      },
      {
        id: 17,
        text: "Who do you lean on when anxiety spikes?",
        options: ["Family", "Friends", "Professors/mentors", "The internet"],
      },
      {
        id: 18,
        text: "Alumni networking feels…",
        options: [
          "Like free career gold",
          "Meh, depends on the school",
          "Awkward but useful",
          "Stressful, so I avoid it",
        ],
      },
      {
        id: 19,
        text: "Your biggest social fear at work?",
        options: [
          "Not fitting in with coworkers",
          "Saying something dumb",
          "Being left out of things",
          "Having no friends at work",
        ],
      },
      {
        id: 20,
        text: "What kind of work friends do you want?",
        options: [
          "A tight crew, like college friends",
          "Friendly coworkers, nothing deep",
          "Mentor relationships",
          "Keep work + personal separate",
        ],
      },
    ],
  },
  {
    title: "Stress & Balance",
    startId: 21,
    questions: [
      {
        id: 21,
        text: "Right now, your #1 stressor is…",
        options: [
          "Loans + money",
          "Finding a job I actually like",
          "Leaving friends/community behind",
          "Not knowing what’s next",
        ],
      },
      {
        id: 22,
        text: "When anxiety hits, what’s your coping move?",
        options: [
          "Call/text a friend",
          "Hit the gym or take a walk",
          "Netflix + snacks",
          "Shut down + hide",
        ],
      },
      {
        id: 23,
        text: "Weekends are for…",
        options: [
          "Sleeping like a raccoon in daylight",
          "Brunch + mimosas with friends",
          "Netflix + sweatpants (uniform, part two)",
          "Spontaneous adventures I probably can’t afford",
        ],
      },
      {
        id: 24,
        text: "How do you feel about moving for a job?",
        options: [
          "Excited — new adventure!",
          "Nervous but open",
          "Ugh, I want to stay close to home",
          "Only if the paycheck’s big enough",
        ],
      },
      {
        id: 25,
        text: "If college was “the bubble,” life now feels…",
        options: [
          "Scary but exciting",
          "Free and independent",
          "Overwhelming",
          "Still figuring it out",
        ],
      },
    ],
  },
];

export default function CareerAndJobSearchTab() {
  // store answers by question id -> option index
  const [answers, setAnswers] = useState<Record<number, number>>({});

  const handleChange = (qid: number, idx: number) => {
    setAnswers((prev) => ({ ...prev, [qid]: idx }));
  };

  const handleSubmit = () => {
    // super simple: just dump selections to console; replace with your save logic
    console.log("Career & Job Search responses:", answers);
    alert("Responses saved (see console).");
  };

  return (
    <div className="p-4 max-w-3xl mx-auto">
      <h2 className="text-xl font-semibold mb-2">Career &amp; Job Search</h2>

      {sections.map((sec) => (
        <div key={sec.title} className="mb-6">
          <h3 className="text-lg font-medium mb-2">{sec.title}</h3>
          <ol start={sec.startId} className="space-y-4 pl-5">
            {sec.questions.map((q) => (
              <li key={q.id}>
                <fieldset>
                  <legend className="mb-1">{q.text}</legend>
                  {q.options.map((opt, idx) => (
                    <label key={idx} className="block">
                      <input
                        type="radio"
                        name={`q${q.id}`}
                        checked={answers[q.id] === idx}
                        onChange={() => handleChange(q.id, idx)}
                      />{" "}
                      {opt}
                    </label>
                  ))}
                </fieldset>
              </li>
            ))}
          </ol>
        </div>
      ))}

      <button
        onClick={handleSubmit}
        className="border px-3 py-2"
        type="button"
      >
        Submit
      </button>
    </div>
  );
}
