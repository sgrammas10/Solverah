import { useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useNavigate } from "react-router-dom";


/* -----------------------------------------------------------
   Type Definitions
   ----------------------------------------------------------- */
// Each quiz item has an id (unique), display text, and 4 options.
type Question = { 
  id: number; 
  text: string; 
  options: string[]; 
};

/* -----------------------------------------------------------
   Quiz Intro Copy
   ----------------------------------------------------------- */
// Simple content block used to render the heading and intro text.
const intro = {
  title: "Your Future, Your Way",
  subtitle: "A Fun Quiz to Explore What’s Next",
  blurb: "Discover your strengths, explore options, and find your future path.",
};

/* -----------------------------------------------------------
   Question Bank
   -----------------------------------------------------------
   - 30 questions total
   - Each question has 4 answer options.
   - We store responses using the question id as a key and
     the index of the chosen option (0–3) as the value.
----------------------------------------------------------- */
const questions: Question[] = [
  { 
    id: 1, 
    text: "In a group project, what role do you usually take?", 
    options: [
      "Keep everyone on track and boss people around (nicely… mostly).",
      "Throw out crazy ideas and make it look good.",
      "Do all the research because no one else will.",
      "Try to keep everyone from fighting (basically the group therapist).",
    ]
  },
  { 
    id: 2, 
    text: "If you get a free afternoon, what’s most fun?", 
    options: [
      "Planning something — even if it’s just what we’re eating.",
      "Making random TikToks, art, or music.",
      "Gaming, coding, or going down a weird YouTube rabbit hole.",
      "Hanging out, helping family, or just being the “chill one.”",
    ]
  },
  { 
    id: 3, 
    text: "What class do you usually enjoy the most?", 
    options: [
      "Business or leadership — I like being the boss.",
      "Art, drama, or creative writing — finally, a class where doodling is allowed.",
      "Math, science, or computer studies — give me the numbers or the code.",
      "History, psychology, or health — learning about people is actually interesting.",
    ]
  },
  { 
    id: 4, 
    text: "What excites you most about a future job?", 
    options: [
      "Being in charge (hello, CEO vibes).",
      "Getting paid to be creative instead of doodling in math class.",
      "Solving tough problems — like why Wi-Fi always breaks during tests.",
      "Helping people — because not everything is about $$$.",
    ]
  },
  { 
    id: 5, 
    text: "When people come to you for help, it’s usually because…", 
    options: [
      "I’ll organize their chaos (and maybe boss them a little).",
      "I’m the one with the random creative idea.",
      "I can actually explain stuff without sounding like a textbook.",
      "I’ll listen and probably hand out free therapy sessions.",
    ]
  },
  { 
    id: 6, 
    text: "If you could shadow someone for a day, who would it be?", 
    options: [
      "A business leader, coach, or literally anyone with a corner office.",
      "A YouTuber, musician, or fashion designer.",
      "A scientist, coder, or the person who invented Doritos Locos Tacos.",
      "A teacher, nurse, or the coach who actually cares.",
    ]
  },
  { 
    id: 7, 
    text: "Which phrase fits you best?", 
    options: [
      "I like planning and being in charge (aka boss energy).",
      "I’m the “ideas person” — some good, some wild.",
      "I’m the one Googling random facts at 2 a.m.",
      "I’m the “how are you really doing?” friend.",
    ]
  },
  { 
    id: 8, 
    text: "What kind of work vibe sounds best?", 
    options: [
      "Fast-paced and goal-driven.",
      "Flexible and creative.",
      "Structured and problem-solving.",
      "Supportive and meaningful.",
    ]
  },
  { 
    id: 9, 
    text: "If money wasn’t an issue, what would you do forever?", 
    options: [
      "Start businesses or lead projects.",
      "Make art, videos, or music.",
      "Invent things or solve problems.",
      "Help people improve their lives.",
    ]
  },
  { 
    id: 10, 
    text: "What about the future excites you most?", 
    options: [
      "Building something successful.",
      "Expressing myself in new ways.",
      "Discovering solutions to big problems.",
      "Making a positive impact.",
    ]
  },
  { 
    id: 11, 
    text: "School gets canceled for the day — what are you doing?", 
    options: [
      "Making plans with friends.",
      "Drawing, gaming, or working on a hobby.",
      "Messing with tech or tutorials online.",
      "Hanging with family or helping someone.",
    ] 
  },
  { 
    id: 12, 
    text: "What kind of content do you binge the most?", 
    options: [
      "Funny skits, pranks, or challenges.",
      "Music, art, fashion, or gaming streams.",
      "Science, tech, or “how it works” videos.",
      "Motivational, advice, or feel-good clips.",
    ] 
  },  
  { 
    id: 13, 
    text: "You just got $500 — first move?", 
    options: [
      "Start a side hustle or invest.",
      "Buy stuff for my creative hobby.",
      "Get new tech or gear.",
      "Spend it on friends, family, or give some away.",
    ]
  },
  { 
    id: 14, 
    text: "In your friend group, you’re usually the one who…", 
    options: [
      "Makes the plans.",
      "Comes up with funny or creative ideas.",
      "Fixes tech problems or knows random facts.",
      "Listens and gives advice.",
    ]
  },
  { 
    id: 15, 
    text: "If you could have a superpower, which would you pick?", 
    options: [
      "Convince or inspire anyone.",
      "Unlimited creativity.",
      "Super-intelligence.",
      "Healing/helping powers.",
    ]
  },
  { 
    id: 16, 
    text: "If your friends had to describe you in one word, you’d want it to be…", 
    options: [
      "Successful",
      "Creative",
      "Smart",
      "Kind",
    ]
  },
  { 
    id: 17, 
    text: "Your school’s doing a fundraiser. Where do you sign up?", 
    options: [
      "Organizing and running it.",
      "Designing posters, videos, or theme.",
      "Handling the money or tech.",
      "Greeting people and hyping the crowd.",
    ]
  },
  { 
    id: 18, 
    text: "If your future job could promise ONE thing, what would you want?", 
    options: [
      "Good money and promotions.",
      "Freedom to be creative.",
      "Learning and solving problems.",
      "Making a real difference.",
    ]
  },
  { 
    id: 19, 
    text: "Think about your favorite teacher or coach. Why were they great?", 
    options: [
      "They were organized and pushed me to do my best.",
      "They made class or practice fun and creative.",
      "They explained things in a way that made sense.",
      "They cared about me and were supportive.",
    ]
  },
  { 
    id: 20,
    text: "Now think about your least favorite teacher or coach. What bugged you most?", 
    options: [
      "Too strict and never listened.",
      "Boring and not engaging.",
      "Didn’t explain things clearly.",
      "Didn’t seem to care about students.",
    ] 
  },
  { 
    id: 21, 
    text: "Sports or clubs: what fits you best?", 
    options: [
      "I like being busy and in lots of activities.",
      "I’d rather focus on one passion.",
      "I join when I have time, not all the time.",
      "I’d rather chill and recharge.",
    ] 
  },
  { 
    id: 22, 
    text: "What’s your least favorite subject — and why?", 
    options: [
      "Math/Science — feels too hard or boring.",
      "English/History — too much reading or writing.",
      "Art/Music — not my thing.",
      "PE/Health — just not into it.",
    ]
  },
  { 
    id: 23, 
    text: "When a class gets tough, how do you usually react?", 
    options: [
      "Push through and try to figure it out.",
      "Zone out and lose interest.",
      "Ask for help or find another way to learn it.",
      "Get frustrated and want to give up.",
    ]
  },
  { 
    id: 24, 
    text: "After high school, what sounds most exciting?", 
    options: [
      "Getting a job and making money right away.",
      "Traveling, creating, or trying new things.",
      "Going to college for something like science, tech, or engineering.",
      "Studying something that helps people, like teaching or healthcare.",
    ]
  },
  { 
    id: 25, 
    text: "What’s most important to you after graduation?", 
    options: [
      "Making money and buying my own stuff.",
      "Freedom to do what I enjoy.",
      "Learning more and building skills.",
      "Being around people and making a difference.",
    ]
  },
  { 
    id: 26, 
    text: "When you have a lot of homework or chores, what do you usually do?", 
    options: [
      "Get it done right away so I can relax later.",
      "Try to make it fun or creative (music on, doodles in the margins).",
      "Make a plan and knock it out step by step.",
      "Put it off… or bribe my sibling/friend to do it for me. 😅",
    ]
  },
  { 
    id: 27, 
    text: "If a group project is falling apart, what’s your move?", 
    options: [
      "Take charge and run the show.",
      "Whip up something last-minute but make it look good.",
      "Quietly fix the mess because no one else will.",
      "Shrug — hey, at least it’s not just my grade.",
    ]
  },
  { 
    id: 28, 
    text: "If your teacher or coach gave you the wrong grade/score, what would you do?", 
    options: [
      "March up and argue my case until it’s fixed.",
      "Make a funny TikTok or snap about it.",
      "Bring proof (notes, screenshots) and present my case like a lawyer.",
      "Let it slide — grades aren’t everything.",
    ]
  },
  { 
    id: 29, 
    text: "You’re late to class. Why?", 
    options: [
      "Had a meeting/club thing — I’m busy!",
      "Was in the bathroom making TikToks.",
      "Lost track of time geeking out on something else.",
      "Stopped to help a friend or teacher.",
    ]
  },
  { 
    id: 30, 
    text: "If school let you design your own class, what would it be?", 
    options: [
      "How to start a business and make $$$.",
      "Meme-making 101 or Creative Hacks.",
      "Build a robot or code your own game.",
      "Life skills — like taxes, cooking, and how to adult.",
    ]
  },
];

export const yourFutureYourWayQuestionBank = questions;


/* ===========================================================
   COMPONENT: YourFutureYourWayTab
   -----------------------------------------------------------
   Responsibilities:
   ✔ Render the quiz UI
   ✔ Track selected answers
   ✔ Save results into the user's profile via AuthContext
   =========================================================== */
export default function YourFutureYourWayTab() {
  // answers: maps question id → selected option index (0–3)
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const { fetchProfileData, saveProfileData } = useAuth();
  const navigate = useNavigate();


  /* ---------------------------------------------------------
     onChange
     ---------------------------------------------------------
     Updates the selected answer for a single question.
     qid = question id
     idx = index of chosen option
  --------------------------------------------------------- */
  const onChange = (qid: number, idx: number) =>
    setAnswers((prev) => ({ ...prev, [qid]: idx }));

  /* ---------------------------------------------------------
     onSubmit
     ---------------------------------------------------------
     - Fetch existing profile data
     - Adds/overwrites quizResults.yourFutureYourWay
     - Saves via saveProfileData from AuthContext
  --------------------------------------------------------- */
  const onSubmit = () => {
    (async () => {
      try {
        // Get current profile data if available
        const current = await (fetchProfileData
          ? fetchProfileData()
          : Promise.resolve(null));

        // Handle shape { profileData: {...} } or raw object
        const profileData = current?.profileData || current || {};

        const newProfileData = {
          ...profileData,
          quizResults: {
            yourFutureYourWay: answers,
            submittedAt: new Date().toISOString(),
          },
        };

        if (saveProfileData) {
          await saveProfileData(newProfileData);
          alert("Responses saved to your profile.");
          navigate("/job-seeker/profile?tab=quizzes");
        } else {
          alert("Unable to save responses (not authenticated).");
        }
      } catch (err) {
        console.error(err);
        alert("Failed to save responses. Check console for details.");
      }
    })();
  };

  /* =======================================================
     RENDER
     ======================================================= */
  return (
    <div className="p-4 max-w-3xl mx-auto">
      {/* Intro block */}
      <h2 className="text-xl font-semibold">{intro.title}</h2>
      <p className="mt-1">{intro.subtitle}</p>
      <p className="mt-1 mb-4">{intro.blurb}</p>

      {/* Quiz header */}
      <h3 className="text-lg font-medium mb-2">Your Future, Your Way Quiz</h3>

      {/* Question list */}
      <ol start={1} className="space-y-4 pl-5">
        {questions.map((q) => (
          <li key={q.id}>
            <fieldset>
              {/* Question text */}
              <legend className="mb-1">
                {q.id}. {q.text}
              </legend>

              {/* Options as radio inputs */}
              {q.options.map((opt, idx) => (
                <label key={idx} className="block">
                  <input
                    type="radio"
                    name={`q${q.id}`}               // group radios per question
                    checked={answers[q.id] === idx} // controlled radio
                    onChange={() => onChange(q.id, idx)}
                  />{" "}
                  {String.fromCharCode(65 + idx)}) {opt}
                </label>
              ))}
            </fieldset>
          </li>
        ))}
      </ol>

      {/* Submit button */}
      <button
        type="button"
        onClick={onSubmit}
        className="border px-3 py-2 mt-4"
      >
        Submit
      </button>
    </div>
  );
}
