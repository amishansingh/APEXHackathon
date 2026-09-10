# Cosmic Mart — Visual Style Guide

*For use when creating presentations, slide decks, or supporting materials.*

---

## Concept

The aesthetic is an **antique celestial atlas rendered as a star chart** — deep navy
backgrounds, warm brass constellation lines, and cream ink. Everything feels measured and
precise: small uppercase labels, generous spacing, no decorative clutter. The goal is
gravitas without opacity; a first-time viewer should find it legible and trustworthy, not
styled for its own sake.

---

## Colour palette

| Role | Name | Hex | Use |
|---|---|---|---|
| Page background | Navy | `#0d1a35` | Slide backgrounds, full bleeds |
| Raised surface | Navy raised | `#152447` | Cards, panels, content blocks |
| Deep surface | Navy deep | `#1c2c53` | Decision cards, nested panels |
| Primary text | Cream | `#f2ead0` | All body copy, headings, data |
| Muted text | Cream soft | `#a89e83` | Captions, labels, secondary info |
| Accent | Brass | `#d9a659` | Highlights, icons, label text, borders |
| Accent bright | Brass bright | `#ecc07f` | Hover states, emphasis |
| Success / approve | Sage | `#7db287` | Positive verdicts, green signals |
| Warning / flag | Amber | `#c4873a` | Flagged items, caution states |
| Danger / block | Rust | `#e07a4e` | Negative verdicts, critical alerts |
| Pure white | Star | `#ffffff` | Checkmarks, isolated highlights only |

**Background gradients.** The dashboard uses two soft nebula washes over the navy base:
- A brass-tinted ellipse at top-left (~22%, 18%) at 11% opacity
- A cool-blue ellipse at bottom-right (~78%, 82%) at 6% opacity
- A dark vignette ring at the edges

For slides: a solid `#0d1a35` background with a very subtle radial brass glow in one corner
is sufficient. Avoid heavy gradients that compete with content.

**Translucent surfaces.** Borders and hairlines use `rgba(242,234,208, 0.16)` — cream at
16% opacity. Use this for dividers and card outlines rather than a solid colour.

---

## Typography

### Typefaces

| Role | Family | Notes |
|---|---|---|
| Display / headings | **Iowan Old Style**, Palatino Linotype, Book Antiqua, Georgia | Serif, used in italic weight for all major headings |
| Body / data / labels | System sans-serif | ui-sans-serif, Segoe UI, Roboto — whatever the viewer's OS provides |

In presentations, use a **classic serif** (Garamond, Palatino, EB Garamond, or Times New
Roman) for headings and a clean **neutral sans-serif** (Calibri, Inter, Helvetica Neue) for
body text.

### Scale and style

| Element | Size | Weight | Style | Colour |
|---|---|---|---|---|
| Brand / slide title | 26 px / ~36 pt | Regular (400) | Italic serif | Cream `#f2ead0` |
| Section heading (h2) | 22 px / ~28 pt | Regular (400) | Italic serif | Cream |
| Subheading / label | 10–11 px / ~13 pt | Regular | ALL CAPS, 2–3 px letter-spacing | Brass `#d9a659` |
| Body copy | 14–15 px / ~18 pt | Regular | Normal | Cream |
| Caption / metadata | 11–12 px / ~14 pt | Regular | Normal | Cream soft `#a89e83` |
| CTA button text | 13 px / ~16 pt | Semibold (600) | Italic, ALL CAPS, 1.5 px tracking | Navy on brass fill |

**Key rule:** section headings are always italic serif. Labels and category tags are always
ALL CAPS sans-serif with wide letter-spacing. Never swap these roles.

---

## Iconography and sigils

Each agent type has a small SVG sigil (icon). In the dashboard these are rendered in cream
at 22 × 22 px. In slides, use the same icons at larger sizes if available, or substitute
with simple geometric line icons in brass or cream. Never use filled / solid icons — the
aesthetic is line-drawn.

| Agent | Description |
|---|---|
| Holiday calendar | Circle with curved crescent |
| Weather watch | Cloud |
| Social media | Overlapping circles / signal rings |
| Economy tracker | Bar chart / trend line |
| Local news | Folded page |

If you don't have the exact SVGs, a simple brass-coloured outline icon in a matching style
is fine. Consistency of weight matters more than exact shape.

---

## Spacing and layout

- **Content margins:** 44 px horizontal on desktop; comfortable breathing room is preferred
  over density.
- **Card padding:** 20–24 px internally.
- **Section spacing:** 48–60 px between major sections.
- **Borders:** 1 px hairline, translucent cream (`rgba(242,234,208,0.16)`). Dashed borders
  (6 px dash) for secondary / "filtered" areas.
- **Border radius:** 2–3 px. The aesthetic is nearly square — no pill shapes except on
  status badges.

For slides: use generous margins and white space. One idea per slide. Never fill the slide.

---

## UI components (for reference or replication)

### Status badges / pills

Three states, used for tradeoff verdicts:

| Verdict | Background | Text colour | Label |
|---|---|---|---|
| Approve | Sage green (translucent) | `#7db287` | *Approved* |
| Flag | Amber (translucent) | `#c4873a` | *Needs review* |
| Block | Rust (translucent) | `#e07a4e` | *Blocked* |

Pills have 2 px border-radius, small uppercase sans-serif text, no bold.

### Cards

Two-layer surface system:
- **Outer card:** `#152447` (navy raised), 1 px hairline border
- **Nested panel / decision card:** `#1c2c53` (navy deep)
- **Top accent line:** 2 px solid brass `#d9a659`

A brass top border on a card signals a data panel or drawer. Use this in slides to
demarcate tables or detail blocks.

### Labels and category chips

Small all-caps sans-serif text on a translucent navy background (`rgba(242,234,208,0.09)`),
1 px hairline border, 2 px border-radius. Brass text colour. Letter-spacing ~1.5–2.5 px.

### Section ornament

Section headings are preceded by `✦` (U+2726, Black Four Pointed Star) in brass, at about
half the heading font size. Use this sparingly — once per major section, not on sub-items.

### Dividers

Horizontal rules between data rows: 1 px, `rgba(242,234,208,0.16)`.
Between major sections: a brass line or a dashed cream hairline works.

---

## Dos and don'ts

**Do:**
- Use deep navy as the slide background — it matches the dashboard exactly
- Write headings in italic serif
- Use ALL CAPS with wide tracking for labels, categories, and agent names
- Lead with the world event → scoped products → recommendation narrative when presenting
- Reference the confirmed figures: **$7.84B pre-tax loss**, **77% of revenue from gadgets**
- Show the tension: conflicting signals, widened forecast ranges, divergence flagged for review
- Use sage green / rust as signal colours for approve / block outcomes

**Don't:**
- Use white or light backgrounds — they break the visual language entirely
- Use bold serif headings — all headings are regular weight, italic
- Invent statistics, testimonials, customer logos, or deployment claims
- Use rounded or pill-shaped design elements (except status badges)
- Use the word "Manoeuvres" — the correct spelling throughout is **Maneuvers**
- Imply the system is running in production anywhere

---

## Slide background recipe (for PowerPoint / Keynote / Google Slides)

1. **Base fill:** solid `#0d1a35`
2. **Optional glow:** radial gradient from `rgba(217,166,89,0.08)` centred at top-left,
   fading to transparent by 40% of the slide width
3. **Logo / wordmark:** *Cosmic Mart* in italic Palatino / Garamond, "CELESTIAL INVENTORY
   ATLAS" in brass ALL CAPS below it, letter-spacing ~3 px
4. **Dividers:** 1 px lines in `rgba(242,234,208,0.16)`
5. **Accent colour:** brass `#d9a659` for highlights, icons, and active labels only —
   not for large filled areas

---

## Voice and framing

- **Tone:** precise, calm, evidence-led. Never hype.
- **Framing:** lead with the problem ($7.84B loss, inventory misalignment), then show how
  each agent step makes the reasoning visible and auditable.
- **The differentiators to name:**
  - Conflict is preserved, not averaged — when signals disagree, the range widens and both
    are named
  - The human gate is total, not a threshold — every recommendation is reviewed before
    execution, not just the expensive or uncertain ones
- **Audience assumption:** no supply-chain background. Every label and claim must be
  legible cold.
