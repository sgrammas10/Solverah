export type QuizOption = { id: string; label: string };
export type QuizQuestion = { id: string; prompt: string; options: QuizOption[] };
export type Quiz = { id: string; title: string; questions: QuizQuestion[] };

export const quizzes: Quiz[] = [
  {
    id: 'q1',
    title: 'Quiz 1: Early Career',
    questions: [
      {
        id: 'ec1',
        prompt: 'What is one thing you would change about your current position?',
        options: [
          { id: 'ec1a', label: 'More growth opportunities' },
          { id: 'ec1b', label: 'Better manager support' },
          { id: 'ec1c', label: 'Higher pay' },
          { id: 'ec1d', label: 'Different team or culture' },
        ],
      },
      {
        id: 'ec2',
        prompt: 'What motivates you most at work?',
        options: [
          { id: 'ec2a', label: 'Recognition and feedback' },
          { id: 'ec2b', label: 'Achieving results' },
          { id: 'ec2c', label: 'Helping others' },
          { id: 'ec2d', label: 'Learning new skills' },
        ],
      },
      {
        id: 'ec3',
        prompt: 'How do you prefer to receive feedback?',
        options: [
          { id: 'ec3a', label: 'In the moment, directly' },
          { id: 'ec3b', label: 'In private, with explanation' },
          { id: 'ec3c', label: 'Written feedback I can review' },
          { id: 'ec3d', label: 'Through regular check-ins' },
        ],
      },
      {
        id: 'ec4',
        prompt: 'What type of projects excite you most?',
        options: [
          { id: 'ec4a', label: 'Creative and innovative projects' },
          { id: 'ec4b', label: 'Problem-solving challenges' },
          { id: 'ec4c', label: 'Clear, structured tasks' },
          { id: 'ec4d', label: 'Collaborative team efforts' },
        ],
      },
      {
        id: 'ec5',
        prompt: 'Do you prefer structured tasks or open-ended challenges?',
        options: [
          { id: 'ec5a', label: 'Structured tasks with clear direction' },
          { id: 'ec5b', label: 'Open-ended challenges where I can decide' },
          { id: 'ec5c', label: 'A mix of both' },
          { id: 'ec5d', label: 'Depends on the situation' },
        ],
      },
    ],
  },
  {
    id: 'q2',
    title: 'Quiz 2: Career Transition',
    questions: [
      {
        id: 'ct1',
        prompt: 'Why are you considering a career change?',
        options: [
          { id: 'ct1a', label: 'Burnout in current role' },
          { id: 'ct1b', label: 'Desire for new challenge' },
          { id: 'ct1c', label: 'Better pay and benefits' },
          { id: 'ct1d', label: 'Personal passion or interest' },
        ],
      },
      {
        id: 'ct2',
        prompt: 'What skills from your past roles do you want to leverage most?',
        options: [
          { id: 'ct2a', label: 'Leadership' },
          { id: 'ct2b', label: 'Technical expertise' },
          { id: 'ct2c', label: 'Creativity and innovation' },
          { id: 'ct2d', label: 'Problem-solving' },
        ],
      },
      {
        id: 'ct3',
        prompt: 'What are you hoping to leave behind in your current/previous role?',
        options: [
          { id: 'ct3a', label: 'Toxic work culture' },
          { id: 'ct3b', label: 'Lack of growth' },
          { id: 'ct3c', label: 'Work-life imbalance' },
          { id: 'ct3d', label: 'Repetitive tasks' },
        ],
      },
      {
        id: 'ct4',
        prompt: 'What type of culture do you want in your next role?',
        options: [
          { id: 'ct4a', label: 'Collaborative and team-focused' },
          { id: 'ct4b', label: 'Innovative and fast-paced' },
          { id: 'ct4c', label: 'Stable and predictable' },
          { id: 'ct4d', label: 'Supportive and developmental' },
        ],
      },
      {
        id: 'ct5',
        prompt: 'What would success look like for you in a new career path?',
        options: [
          { id: 'ct5a', label: 'Financial stability' },
          { id: 'ct5b', label: 'Work-life balance' },
          { id: 'ct5c', label: 'Recognition and growth' },
          { id: 'ct5d', label: 'Meaningful contribution' },
        ],
      },
    ],
  },
  {
    id: 'q3',
    title: 'Quiz 3: Mid-Career / Strategic',
    questions: [
      {
        id: 'mc1',
        prompt: 'What do you want your leadership legacy to be?',
        options: [
          { id: 'mc1a', label: 'Building strong teams' },
          { id: 'mc1b', label: 'Driving innovation' },
          { id: 'mc1c', label: 'Delivering results' },
          { id: 'mc1d', label: 'Developing future leaders' },
        ],
      },
      {
        id: 'mc2',
        prompt: 'How do you balance strategic vision with day-to-day execution?',
        options: [
          { id: 'mc2a', label: 'Delegate operational tasks' },
          { id: 'mc2b', label: 'Focus on strategy first' },
          { id: 'mc2c', label: 'Alternate between both' },
          { id: 'mc2d', label: 'Struggle with balance' },
        ],
      },
      {
        id: 'mc3',
        prompt: 'Where do you want to grow in the next 3–5 years?',
        options: [
          { id: 'mc3a', label: 'People leadership' },
          { id: 'mc3b', label: 'Technical expertise' },
          { id: 'mc3c', label: 'Strategic influence' },
          { id: 'mc3d', label: 'Entrepreneurial ventures' },
        ],
      },
      {
        id: 'mc4',
        prompt: 'What type of team environment allows you to thrive?',
        options: [
          { id: 'mc4a', label: 'High accountability' },
          { id: 'mc4b', label: 'Creative and open-minded' },
          { id: 'mc4c', label: 'Structured and organized' },
          { id: 'mc4d', label: 'Supportive and collaborative' },
        ],
      },
      {
        id: 'mc5',
        prompt: 'How do you want to be remembered by your peers and reports?',
        options: [
          { id: 'mc5a', label: 'As a trusted advisor' },
          { id: 'mc5b', label: 'As an innovator' },
          { id: 'mc5c', label: 'As a dependable operator' },
          { id: 'mc5d', label: 'As a mentor and coach' },
        ],
      },
    ],
  },
  {
    id: 'q4',
    title: 'Quiz 4: Your Future, Your Way (Teen-Focused)',
    questions: [
      {
        id: 'tf1',
        prompt: 'What is your least favorite subject and why?',
        options: [
          { id: 'tf1a', label: 'Math – too many rules' },
          { id: 'tf1b', label: 'English – too much writing' },
          { id: 'tf1c', label: 'Science – too complicated' },
          { id: 'tf1d', label: 'History – too boring' },
        ],
      },
      {
        id: 'tf2',
        prompt: 'What did your favorite teacher or coach do that made them stand out?',
        options: [
          { id: 'tf2a', label: 'Made learning fun' },
          { id: 'tf2b', label: 'Believed in me' },
          { id: 'tf2c', label: 'Pushed me to do better' },
          { id: 'tf2d', label: 'Listened and cared' },
        ],
      },
      {
        id: 'tf3',
        prompt: 'Do you like to stay busy all the time or chill out more?',
        options: [
          { id: 'tf3a', label: 'Always busy – I like action' },
          { id: 'tf3b', label: 'Chill out – I need downtime' },
          { id: 'tf3c', label: 'A balance of both' },
          { id: 'tf3d', label: 'Depends on my mood' },
        ],
      },
      {
        id: 'tf4',
        prompt: 'What do you want life to look like after high school?',
        options: [
          { id: 'tf4a', label: 'Go to college' },
          { id: 'tf4b', label: 'Start working right away' },
          { id: 'tf4c', label: 'Travel and explore' },
          { id: 'tf4d', label: 'Not sure yet' },
        ],
      },
      {
        id: 'tf5',
        prompt: 'How do you usually handle school projects?',
        options: [
          { id: 'tf5a', label: 'Do it right away' },
          { id: 'tf5b', label: 'Wait until the last minute' },
          { id: 'tf5c', label: 'Bribe a sibling or friend to help' },
          { id: 'tf5d', label: 'Work with a group' },
        ],
      },
    ],
  },
];

export const archetypes = [
  { id: 'builder', label: 'The Builder', desc: 'Thrives on creating new systems, projects, and opportunities.' },
  { id: 'strategist', label: 'The Strategist', desc: 'Excels in long-term planning and pattern recognition.' },
  { id: 'operator', label: 'The Operator', desc: 'Delivers reliable execution and stability.' },
  { id: 'visionary', label: 'The Visionary', desc: 'Inspires others with big-picture thinking and innovation.' },
  { id: 'connector', label: 'The Connector', desc: 'Builds relationships and drives collaboration.' },
];