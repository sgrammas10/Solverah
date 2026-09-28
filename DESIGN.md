---
name: Solverah — Landing ("/")
description: Cream ground, ink type, forest green for every action; a pinned scroll-story hero that changes scene as you scroll. Landing page route only; provisional.
colors:
  cream-base: "#FAF7F2"
  cream-subtle: "#EAE4DB"
  cream-muted: "#D4CFC8"
  pane-white: "#FFFFFF"
  forest-dark: "#1B4332"
  forest-mid: "#2D6A4F"
  forest-light: "#40916C"
  forest-pale: "#D8F3DC"
  ink-primary: "#1A1A1A"
  ink-secondary: "#555555"
  ink-tertiary: "#888888"
  footer-muted: "#AAAAAA"
typography:
  display:
    fontFamily: "Archivo, 'Arial Narrow', system-ui, sans-serif"
    fontSize: "clamp(2.75rem, 5.6vw, 5.2rem)"
    fontWeight: 800
    lineHeight: 0.98
    letterSpacing: "-0.025em"
  display-closing:
    fontFamily: "Archivo, 'Arial Narrow', system-ui, sans-serif"
    fontSize: "clamp(2.2rem, 5.5vw, 4rem)"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.025em"
  headline:
    fontFamily: "Archivo, 'Arial Narrow', system-ui, sans-serif"
    fontSize: "clamp(2rem, 4.2vw, 3.1rem)"
    fontWeight: 800
    lineHeight: 1.02
    letterSpacing: "-0.02em"
  title-strong:
    fontFamily: "Archivo, 'Arial Narrow', system-ui, sans-serif"
    fontSize: "1.6rem"
    fontWeight: 800
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Archivo, 'Arial Narrow', system-ui, sans-serif"
    fontSize: "1.35rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "normal"
  title-sm:
    fontFamily: "Archivo, 'Arial Narrow', system-ui, sans-serif"
    fontSize: "1.15rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "normal"
  lead:
    fontFamily: "'Public Sans', system-ui, sans-serif"
    fontSize: "clamp(1.02rem, 1.6vw, 1.18rem)"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  body:
    fontFamily: "'Public Sans', system-ui, sans-serif"
    fontSize: "0.97rem"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  body-emphasis:
    fontFamily: "'Public Sans', system-ui, sans-serif"
    fontSize: "1.05rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "normal"
  label:
    fontFamily: "'Public Sans', system-ui, sans-serif"
    fontSize: "0.86rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
  nav:
    fontFamily: "'Public Sans', system-ui, sans-serif"
    fontSize: "0.9rem"
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: "normal"
  fine:
    fontFamily: "'Public Sans', system-ui, sans-serif"
    fontSize: "0.76rem"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
rounded:
  none: "0px"
  sm: "4px"
  pill: "9999px"
spacing:
  gap: "2px"
  xs: "8px"
  sm: "16px"
  md: "24px"
  lg: "28px"
  xl: "32px"
  section: "80px"
  section-lg: "112px"
components:
  button-primary:
    backgroundColor: "{colors.forest-dark}"
    textColor: "{colors.pane-white}"
    typography: "{typography.title}"
    rounded: "{rounded.sm}"
    padding: "14px 28px"
  button-primary-hover:
    backgroundColor: "{colors.forest-mid}"
    textColor: "{colors.pane-white}"
  button-primary-nav:
    backgroundColor: "{colors.forest-dark}"
    textColor: "{colors.pane-white}"
    rounded: "{rounded.sm}"
    padding: "10px 20px"
  button-primary-on-dark:
    backgroundColor: "{colors.cream-base}"
    textColor: "{colors.forest-dark}"
    rounded: "{rounded.sm}"
    padding: "14px 28px"
  button-primary-on-dark-hover:
    backgroundColor: "{colors.forest-pale}"
    textColor: "{colors.forest-dark}"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.forest-dark}"
    rounded: "{rounded.sm}"
    padding: "12px 24px"
  button-secondary-hover:
    backgroundColor: "{colors.forest-pale}"
    textColor: "{colors.forest-dark}"
  button-secondary-on-dark:
    backgroundColor: "transparent"
    textColor: "{colors.cream-base}"
    rounded: "{rounded.sm}"
    padding: "12px 24px"
  story-stage:
    backgroundColor: "{colors.cream-base}"
    textColor: "{colors.ink-primary}"
  story-stage-dark:
    backgroundColor: "{colors.forest-dark}"
    textColor: "{colors.cream-base}"
  result-card:
    backgroundColor: "{colors.pane-white}"
    textColor: "{colors.ink-secondary}"
    rounded: "{rounded.sm}"
    padding: "20px 22px"
    width: "272px"
  result-card-wide:
    backgroundColor: "{colors.pane-white}"
    textColor: "{colors.ink-secondary}"
    rounded: "{rounded.sm}"
    padding: "20px 22px"
    width: "400px"
  result-icon:
    backgroundColor: "{colors.forest-pale}"
    textColor: "{colors.forest-dark}"
    rounded: "{rounded.sm}"
    size: "28px"
  step-dot:
    backgroundColor: "transparent"
    rounded: "{rounded.pill}"
    size: "10px"
  step-dot-current:
    backgroundColor: "{colors.forest-dark}"
    rounded: "{rounded.pill}"
    width: "10px"
    height: "24px"
  pane:
    backgroundColor: "{colors.pane-white}"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.none}"
    padding: "28px"
  eco-node:
    backgroundColor: "{colors.pane-white}"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.sm}"
    size: "54px"
  eco-node-lit:
    backgroundColor: "{colors.forest-pale}"
    textColor: "{colors.forest-dark}"
    rounded: "{rounded.sm}"
    size: "54px"
  nav-bar:
    backgroundColor: "{colors.cream-base}"
    textColor: "{colors.ink-secondary}"
    height: "64px"
  intake-band:
    backgroundColor: "{colors.cream-subtle}"
    textColor: "{colors.ink-primary}"
    padding: "80px 24px"
  footer:
    backgroundColor: "{colors.ink-primary}"
    textColor: "{colors.footer-muted}"
    padding: "56px 24px"
---

# Design System: Solverah — Landing ("/")

## Overview

**Creative North Star: "Scroll Through What You Get"**

This is the visual system of Solverah's public landing page at "/", recorded from the shipped code on 2026-09-28. It uses the same cream, forest and ink tokens as the rest of the site (`tailwind.config.js`). An earlier dark "Amber Noir" treatment and a later "A title isn't evidence." hero were both removed. What makes the route its own is its type and structure: an Archivo display face, a Public Sans body, and a scroll-story hero followed by hairline ledgers and gap-gridded panes rather than rounded cards. All of these choices are **provisional**; the user has said the design is not final.

The hero is a scroll story. A tall section pins its stage under the nav, and scrolling through it changes the scene instead of moving down the page. There are five steps. Each one swaps the words, moves three example result cards (a Work Pulse reading, a Situation Report and a manager playbook) to new positions, and shifts the stage background through cream, cream-subtle, forest-pale, cream-subtle and finally forest-dark. The last step, "Checked by a person. Kept from employers.", is the page's one dark scene. After it the page scrolls on normally into editorial sections. These sit in a 1180px measure, organised by 1px cream-muted rules and two-column ledgers, with flat white panes on a 2px cream-muted gutter.

Type does the heavy lifting. Archivo at 800 gives a compressed, heavy display voice at near-solid leading, and Public Sans carries the body in two ink tones. Headlines are a single colour. Motion uses one easing curve. The hero's motion is tied to scroll position, not timers. The ecosystem diagram is the only thing that loops. Under `prefers-reduced-motion` everything stops gliding, but colour changes (stage backgrounds, lit nodes) continue, because a colour change is not motion.

**Key Characteristics:**
- Cream ground, ink type, forest green as the only hue; the hero's last scene is the one forest-dark field
- A pinned five-step scroll story, driven by scroll position and navigable by step dots on desktop
- Three white example result cards, the only page objects that cast a (faint, forest-tinted) shadow
- Ledger layout below the hero: hairline rules and two-column rows, not rounded cards
- Archivo 800 display at leading 0.98–1.02 with tight negative tracking; Public Sans body
- 4px corners on actions, cards and diagram nodes; square panes; full-pill step dots
- One easing curve (0.16, 1, 0.3, 1); reduced motion swaps glides for crossfades and keeps colour change

## Colors

The palette has three families, all from the site-wide tailwind tokens: cream for grounds and structure, forest for the accent and every action, and ink for type. White is used for panes and cards.

### Primary
- **Forest Dark** (`{colors.forest-dark}`): the solid field. It fills every primary button (nav, hero, Work Pulse row, closing, mobile menu, ecosystem card), the skip link, the ecosystem "S" mark and its active line, and the stage of the story's final step. It is the step dots' border and current-dot fill, the glyph colour in a result card's icon tile, the dash marker on the "What we read" list, the secondary button's border and text, and the text of the cream on-dark primary button.
- **Forest Mid** (`{colors.forest-mid}`): the hover state of primary buttons; the hover colour of nav links and the dismiss control; the "Aligned" values and "Checked by a person" line on the result cards; and the icon colour inside flow-layout items.
- **Forest Light** (`{colors.forest-light}`): the focus ring across the page (cream-base on the dark final scene, where forest-light is too faint), and in the ecosystem the travelling packets, the warmed edges and the border of a lit node.
- **Forest Pale** (`{colors.forest-pale}`): text selection; the stage background of the Situation Report step; the result-card icon tile; the hover fill of the secondary button and the on-dark primary button; lit ecosystem nodes and items. On the forest-dark stage it is the colour of the lead, the promise list and the example note.

### Neutral
- **Cream Base** (`{colors.cream-base}`): the page ground, the story's first stage, the sticky nav once scrolled, and the mobile menu sheet. On the forest-dark stage it colours the headline, the on-dark primary button's fill, the on-dark secondary button's border and text, and the step dots.
- **Cream Subtle** (`{colors.cream-subtle}`): the stage background of the Work Pulse and Manager Decoder steps, the intake band, the ecosystem's dotted field, and the row rules inside result cards.
- **Cream Muted** (`{colors.cream-muted}`): the hairline. Every section boundary, ledger row, FAQ row and the nav's bottom edge; the 2px pane gutter; result-card borders and the underline under "Costing you"; the ecosystem's resting edges and node borders; and the scrollbar thumb.
- **Pane White** (`{colors.pane-white}`): the result cards, the "What we read / won't do" panes, the closing band, the account-deletion strip, the ecosystem card and the diagram nodes. Also the text on forest-dark buttons. At 10% alpha it is the on-dark secondary button's hover fill and the footer's rules.
- **Ink Primary** (`{colors.ink-primary}`): every headline, card titles and row values (including "Costing you"), the wordmark, FAQ questions and mobile-menu links. It is also the footer ground.
- **Ink Secondary** (`{colors.ink-secondary}`): running copy, the story leads, section intros, meta lines, result-card text and row labels, the example note, nav links at rest, and the FAQ plus icon.
- **Ink Tertiary** (`{colors.ink-tertiary}`): not a text colour here. It is used only for the dash marker on the "What we won't do" list.
- **Footer Muted** (`{colors.footer-muted}`): footer body, links, copyright and O*NET attribution on the ink-primary footer. Column heads and link hovers go white.

### Named Rules
**The One Dark Scene Rule.** Forest dark shows up as a solid fill: a whole button, the mark, or a whole scene. The story's final step is the only forest-dark field bigger than a button. Don't add a second inverted section.

**The Ink Ladder Rule.** Text uses two steps: ink-primary for headings, titles and values, and ink-secondary for everything else. Ink tertiary is kept for non-text marks. On the forest-dark stage the ladder becomes cream-base (headline) over forest-pale (lead and small text).

**The Ink-Not-Colour Status Rule.** On the result cards a problem is marked with ink and an underline ("Costing you" in ink-primary, underlined in cream-muted), not with a warning hue. Forest-mid marks what is aligned. There is no red, amber or orange on this route.

**The Gap-Not-Border Rule.** Sibling panes in a grid are white tiles on a 2px cream-muted gutter showing from behind them. They never get a border each. The standalone containers (result cards and the ecosystem card) carry a 1px cream-muted border instead.

## Typography

**Display Font:** Archivo (with Arial Narrow, system-ui fallback), loaded at 700 and 800
**Body Font:** Public Sans (with system-ui fallback), loaded at 400–700
**Label/Mono Font:** none

**Character:** A compressed, heavy grotesk set with almost no leading and negative tracking, paired with a plain, open sans. The display face makes the claims and the body face explains them. Archivo and Public Sans are specific to this route. Every other route uses Playfair Display and DM Sans (`font-display` / `font-sans`), and so does the shared intake form embedded on this page (see Components).

### Hierarchy
- **Display** (800, `clamp(2.75rem, 5.6vw, 5.2rem)`, leading 0.98, tracking −0.025em): the hero h1, "See how you actually work.". It is centred, capped at 18ch and text-balanced.
- **Display Closing** (800, `clamp(2.2rem, 5.5vw, 4rem)`, leading 1): the closing headline, capped at 16ch.
- **Headline** (800, `clamp(2rem, 4.2vw, 3.1rem)`, leading 1.02, tracking −0.02em): the story's step headlines (capped at 14ch) and every section h2. It always ends in a full stop.
- **Title Strong** (800, 1.6rem, tracking −0.01em): the three commitment heads ("Never sold."). The focused wide result card's title also steps up to 1.6rem.
- **Title** (700, 1.35rem): ledger row titles and the wordmark (800, −0.02em). The ecosystem card title is 700 at `clamp(1.35rem, 3vw, 1.6rem)`.
- **Title Small** (700, 1.15rem, leading 1.2): result-card titles and pane headings. Ecosystem list names use 1.05rem.
- **Lead** (400, `clamp(1.02rem, 1.6vw, 1.18rem)`, leading 1.6): the story's step paragraphs, capped at 42ch.
- **Body** (400, 0.95–1.02rem, leading 1.6–1.65): running copy in ink-secondary. Section intros are capped at 36–44ch, FAQ answers at 68ch, commitment copy at 60ch.
- **Body Emphasis** (600, 1.05rem): FAQ question summaries in ink-primary.
- **Label** (400–600, 0.86rem): result-card text and rows, the promise list, meta lines, pane group heads, footer column heads and ecosystem column labels. Sentence case, never letterspaced.
- **Nav** (500, 0.9rem): nav and footer links.
- **Fine** (400–600, 0.76–0.8rem): the "Example results" note, the card's "Checked by a person" line, copyright, O*NET attribution and the ecosystem flow caption.

Every headline, from the hero h1 to the pane titles, is set in a single colour: ink-primary, or cream-base on the dark stage.

### Named Rules
**The Full Stop Rule.** Display and headline copy is written as sentences and ends with a period, and ledger titles do the same.

**The No-Eyebrow Rule.** No kickers, eyebrows or uppercase tags go above headings. Meta text goes *below* the title it qualifies, in ink-secondary, in sentence case, separated by middle dots ("12 questions · free · account required").

## Layout

The page is one centred column, 1180px max, with 24px side padding at every width. The nav is a 64px sticky bar with a permanent cream-muted bottom hairline. It is transparent at the top and fills with cream-base after 24px of scroll.

**The scroll story (hero).** The section is `100vh + 4 × 70vh` tall. Its stage sticks at `top: 4rem` with a height of `100vh − 4rem`, clips its overflow, and holds the same 1180px inner measure. Scroll progress through the section maps to five equal steps.
- **Desktop (from 900px):** the step words sit in a left column 42% wide, vertically centred. The intro step is the exception: its words are centred near the top (up to 44rem wide) with the three cards in a row beneath. From step 2 on, the focused card grows (up to 1.28×) at about 68% across the stage, and the other two shrink to 0.72–0.78× at 35% opacity along the right edge. In the final scene all three cards fan together at full opacity, the outer two tilted ±5°. Step dots stack at the right edge, centred vertically.
- **Phone (below 900px):** the words sit at the top, and only the step's focused card shows, centred at 69% down. The other cards fade out, and the dots are hidden. Scrolling is the only control.
- An "Example results. Yours come from your own answers." note is centred at the bottom of the stage.

**Below the hero.** Each section starts with a 1px cream-muted rule and has 80px vertical padding, rising to 112px at `md` (768px). The commitments ledger is tighter, at 64px/80px. The recurring model is the **ledger**: a two-column grid, headline column on the left and hairline-bounded rows on the right, padded 24–32px vertically. The column ratios in use are 5:7 (how-it-reads, intake), 4:8 (FAQ), 3:5 (commitments) and 3:5:auto for rows that end in a button. On desktop the headline column is sticky (`top: 96px`), and below `md` every ledger collapses to one column. The second model is the **pane grid**: two white panes on a 2px cream-muted gutter, padded 28px, stacking below `md`.

The page's bands, in order, are: the story's stage, the cream-base editorial sections, the ecosystem section (on trial), the cream-subtle intake band (a 5:7 ledger, sticky from `lg`, 1024px), the white closing band, and the ink-primary footer (56px padding, 2:1:1:1 columns at `lg`). Spacing inside components runs on 8px multiples.

## Elevation & Depth

The page is mostly flat, with depth from tone. The story's stage changes tone per step. Below the hero, white panes and the white closing band sit on cream-base, the cream-subtle intake band sits a step down, and the ink footer sits below everything. Hover never lifts anything; buttons and links only change colour. The sticky nav is set apart by a hairline and a fill.

Two things are allowed a shadow. The hero's result cards carry a faint ambient shadow tinted forest rather than black (`0 10px 30px rgba(27,67,50,0.1)`), so they read as objects laid on the stage while it changes colour behind them. The ecosystem diagram (on trial) has a dot-grid field, edge fades, a packet glow and a pulsing ring.

### Named Rules
**The Two Exceptions Rule.** Only the hero's result cards and the ecosystem diagram carry a shadow, glow or gradient. The shadow is the single forest-tinted ambient value above. Never a black shadow, a hard offset, or a hover lift. Everywhere else a surface is distinguished by tone, a white fill or a hairline.

## Shapes

The page uses three radii, each tied to a role. Actions (buttons, the skip link), result cards and their icon tiles, ecosystem nodes, the mark and list icons have a 4px corner. Panes, ledgers, the nav, the bands, the story stage and the ecosystem card are square. The step dots are the only full pills: 10px circles with a 1.5px border, and the current one stretches to a 10 × 24px capsule. Borders are 1px, except the 2px secondary-button border and the 2px pane gutter. The FAQ marker is an inline-SVG plus of two 1.5px strokes that turns 45° into a cross. List markers are 16px horizontal hairlines, forest-dark for what Solverah reads and ink-tertiary for what it won't do.

Icons are lucide-react. The hero uses ScanText, ClipboardList, BookOpenText and Check, at 16px in card icon tiles and on the promise list, and 14px on the card check line. The ecosystem uses its own set. The FAQ plus is the only hand-drawn inline SVG left in the page body.

## Components

### Buttons
Buttons are flat rectangles with a 4px corner. On hover they change colour and nothing else. The hero's two buttons (`HeroActions`) are "Get started" and "Preview a quiz".
- **Primary:** forest-dark fill, white text, Archivo 700 at 0.98rem, padding 14px 28px. The nav version is 0.9rem with 10px 20px padding. On hover the fill goes forest-mid (150ms).
- **Secondary:** transparent, 2px forest-dark border, forest-dark text, Public Sans 600 at 0.95rem, padding 12px 24px. On hover it fills with forest-pale.
- **On the dark stage:** the colours invert. The primary is a cream-base fill with forest-dark text, going to forest-pale on hover. The secondary has a 2px cream-base border and cream-base text, with a white-at-10% hover fill.
- **Focus:** focus-visible draws a 2px forest-light outline, offset 3px.

### Scroll story (hero, signature)
- **Steps:** (1) intro, "See how you actually work.", centred, with both buttons; (2) Work Pulse, "Answer twelve questions."; (3) Situation Report, "See what your job is costing you."; (4) Manager Decoder, "Work with the manager you have."; (5) close, "Checked by a person. Kept from employers.", on forest-dark, with both on-dark buttons and a promise list of three items, each with a check (0.86rem, forest-pale).
- **Stage tone per step:** cream-base, cream-subtle, forest-pale, cream-subtle, forest-dark.
- **Words:** every step's words stay in the DOM. Inactive ones are hidden with `visibility`, so they can't take focus.
- **Step dots:** one button per step, labelled with the step name, `aria-current="step"` on the current one. A click scrolls to the middle of that step, smoothly unless reduced motion is on, when it jumps. On the dark stage the dots turn cream-base.
- **Cards region:** exposed as a single `role="img"` with a text label. The cards themselves are `aria-hidden`.

### Result cards
Three example result cards: a Work Pulse reading ("The Autonomist"), a Situation Report ("Where your job fits you") and a manager playbook ("Working with a hands-on manager").
- **Container:** white, 1px cream-muted border, 4px corner, the forest-tinted ambient shadow, padding 20px 22px. They are 272px wide, and the Work Pulse card is 400px (`min(25rem, 88vw)`).
- **Head:** a 28px forest-pale icon tile with a 16px forest-dark lucide glyph.
- **Not part of the system:** the shipped cards also print the product name beside the icon, above the title (0.76rem, 600, forest-mid). That line is a kicker, which breaks the No-Eyebrow Rule. The build carries it as a defect; don't reuse it.
- **Title:** Archivo 700 1.15rem ink-primary, stepping up to 1.6rem on the wide card.
- **Content:** a short 0.86rem ink-secondary paragraph, rows, or a bulleted list. Rows are label/value pairs between cream-subtle rules. The value is 600 ink-primary, right-aligned; "Aligned" is in forest-mid, and "Costing you" is in ink with a cream-muted underline. A 0.76rem 600 forest-mid "Checked by a person" line with a check can close a card.
- **Honesty:** the cards are demonstration content, always paired with the on-stage "Example results" note.

### Cards / Containers (panes)
- **Corner Style:** square
- **Background:** white
- **Shadow Strategy:** none
- **Border:** none; siblings sit on the parent grid's 2px cream-muted gutter
- **Internal Padding:** 28px
- Never nest a pane inside a pane.

### Ledger rows
A ledger row has a title column (Archivo 700, 1.35rem) with an optional ink-secondary meta line beneath it, a body column (0.97rem, ink-secondary), and an optional action column at the end. Rows are padded 24–32px vertically between cream-muted rules. A row for something unavailable (Work Pulse Pro) drops its title to ink-secondary and ends in a 600-weight "Not yet available" label instead of a button.

### Inputs / Fields
The landing page defines no inputs of its own. The intake band hosts the shared `IntakeForm` and `AccountModal` from `src/features/intake/components/`, which `/start` also uses. They use the same cream/forest colours, so there is no colour seam. There is a **type and shape seam**, though: the form's heading is Playfair Display (`font-display`, 600, 1.75rem) and its card is a white panel with a 12px radius, 32px padding and a cream-muted border. Both differ from this route's Archivo headings and 4px/square shapes. The seam is known, and the components are shared, so don't restyle them from this route.

### Navigation
- **Style:** 64px sticky bar with a 1px cream-muted bottom edge. It is transparent at the top and switches to cream-base after 24px of scroll (300ms). The wordmark sits at left (Archivo 800, 1.35rem, ink-primary). Three anchor links and "Sign in" follow in Public Sans 500 0.9rem ink-secondary, 32px apart, turning forest-mid on hover. The forest-dark "Get started" sits at the far right. The story stage pins directly beneath the bar.
- **Mobile (below 768px):** three 24px × 2px ink-primary bars that turn into a cross. The menu is a cream-base sheet of cream-muted-ruled rows (1rem 500 ink-primary), followed by a full-width primary button.

### FAQ disclosure
Native `details`/`summary` with the marker hidden. The summary is 1.05rem 600 ink-primary with 20px vertical padding and an 18px ink-secondary plus at the right. The answer is 0.97rem ink-secondary, capped at 68ch. Opening rotates the plus 45° over 240ms.

### Footer
Ink-primary ground with white-at-10% rules. The wordmark is white. The blurb, links, copyright and O*NET attribution are footer-muted, and links turn white on hover. Column heads are 0.86rem 600 white. The O*NET attribution is a licensing obligation and stays at fine size.

### Ecosystem section (signature, on trial)
This section is lazy-loaded with its own stylesheet. It shows one profile at the centre, connected to six instruments. **Split is the chosen layout (2026-09-28, provisional).** The card and flow layouts stay reachable with `?eco=card|split|flow|off` (default `split`), and a dev-only switcher in the corner flips between them. Record new work against the shared pieces below, not against any one variant.
- **Field:** cream-subtle with a 32px dot grid and cream-subtle fades top and bottom. It has a 564:410 aspect ratio (564:460 below 640px) and 32px padding.
- **Hub:** the "S" mark (Archivo 800, cream-base on forest-dark, 4px corner, 44px from 640px up) sits in a white 4px-cornered frame with a cream-muted border. Around it is a 2px forest-light ring at 45% alpha that pulses to 1.18× scale over 2.4s.
- **Nodes:** white squares with a 4px corner and a 1px cream-muted border, each holding a lucide icon in ink-primary. They are 32px, then 48px from 640px, then 54px from 768px. They scale in from 0.8 when the section scrolls into view (500–600ms, staggered 100ms).
- **Edges:** 1.25px cream-muted orthogonal wires with 15px-radius bends. An active edge (split layout, on list hover) overlays a 1.75px forest-dark line, and its node gets a 2px forest-dark outline offset 2px.
- **Data packets (motion):** on every edge a short forest-light dash (3.5px, round caps, faint glow) travels from the node into the hub over the first 35% of the cycle, waits, then travels back out between 50% and 85%. The edge warms to forest-light at 70% opacity while a packet is on it. The node lights (forest-pale fill, forest-light border, forest-dark icon) as the packet leaves and again as it returns, and rests in between. Each edge has its own cycle length (4.0–6.4s) and offset (0–3.4s), so the lights never fall into one beat. In the flow layout, wires run in one direction only: inputs light as their packet leaves, and outputs light as it arrives.
- **Card layout:** a 564px-max white card with a 1px cream-muted border. The field is on top, and below it is a body section (24px padding, 32px from 640px up) holding the title, body text and a primary button.
- **Split layout:** a 5:7 grid pairing a headline and a hairline-ruled list with the hub. Each list row has a 36px icon tile that lights forest-pale on hover.
- **Flow layout:** input and output columns of white bordered items (0.93rem 600 with a forest-mid icon) either side of a static mark, joined by curved wires on desktop. On mobile the wires become short vertical rules.
- **Reduced motion:** only movement stops. The packets are hidden, the ring's scale pulse stops, and nodes appear at full size without the scale-in. Node and item lighting and edge brightening keep cycling on their per-edge timings, because a colour change is not motion, so the diagram still shows traffic.

### Motion
Every transition on the page uses the single easing curve `cubic-bezier(0.16, 1, 0.3, 1)`, except simple fades and colour changes, which use `ease`.
- **Scroll story** (driven by scroll position, never by timers):
  - The stage background eases between tones over 700ms.
  - Outgoing words fade (500ms). Incoming words rise 16px and fade in (opacity 500ms, transform 600ms, after a 120ms delay).
  - Cards glide to their next position, scale and tilt over 800ms, fading over 500ms.
  - Headline and note colours shift over 500ms.
  - The current step dot stretches over 300ms.
- **Elsewhere:** the FAQ plus rotates over 240ms, colour hovers take 150ms, and the nav fill takes 300ms.
- **Ecosystem:** the only loops, as described above.
- **Reduced motion:** under `prefers-reduced-motion: reduce` (which Windows reports whenever "Animation effects" is off), nothing glides. Story cards and words jump to their new places and crossfade over 400ms, and the stage background still changes, so each step still reads as a new scene. The FAQ plus snaps. In the ecosystem, only the packets and the ring pulse stop.

The `fadeUp`/`fadeIn` animations in `tailwind.config.js` belong to other routes and aren't used here.

## Do's and Don'ts

### Do:
- **Do** use the site-wide cream/forest/ink tokens from `tailwind.config.js`. This route's identity comes from its type and structure, not its own palette.
- **Do** keep forest-dark to buttons, the mark and the story's closing scene. That scene is the only dark field (The One Dark Scene Rule).
- **Do** drive the hero from scroll position, keep every step reachable by scrolling back up, and keep inactive step words out of the focus order.
- **Do** mark status on example cards with ink and an underline, not a warning colour.
- **Do** organise content below the hero as ledgers: a headline column and a stack of hairline-ruled rows, sticky on desktop, one column below 768px.
- **Do** set text in ink-primary and ink-secondary only; ink-tertiary is for marks, not text.
- **Do** end display and headline copy with a full stop.
- **Do** use `cubic-bezier(0.16, 1, 0.3, 1)` for any new motion, and honour reduced motion by stopping movement, not colour change.
- **Do** keep the O*NET attribution in the footer at fine size; it is a licensing obligation.
- **Do** treat every choice here as provisional, and the ecosystem layout as undecided.

### Don't:
- **Don't** reintroduce the removed Amber Noir palette (near-black ground, amber accent). The user rejected it.
- **Don't** add shadows, glows or gradients beyond the result cards' forest-tinted ambient shadow and the ecosystem diagram.
- **Don't** put a pane inside a pane, or give a border to a pane that already sits in a gap grid.
- **Don't** add eyebrows, kickers, uppercase tags or letterspaced labels above headings.
- **Don't** use Playfair Display, DM Sans or the `fade-up` animations in this route's own markup; they belong to other routes.
- **Don't** round anything beyond 4px except the step dots.
- **Don't** restyle `IntakeForm` or `AccountModal` from this route; they are shared with `/start`.
