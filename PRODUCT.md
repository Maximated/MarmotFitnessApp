# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Max, the sole real user. He is the developer and the trainee: a self-taught
programmer building this app for his own daily gym training, and the person
who actually trains with it every day. No other real accounts are in active
use. The sharing feature (a public link to a routine or a single day, with an
optional "copy to my account" for a logged-in viewer) exists so Max can hand a
routine to someone else outside the app - it does not mean other people
currently train inside his instance.

## Product Purpose

A self-hosted gym-tracking app: log workouts with a full history of dates,
weights, reps, and per-set comments; follow structured multi-day training
programs ("routines") that schedule themselves day by day in a repeating
cycle; track a per-exercise weight target that progresses over time; see
progress charts per exercise. It was explicitly started as a personal
"learn to program from scratch, step by step" project as much as a real
daily-use tool - both remain true today.

## Positioning

Not a commercial product, and not meant to become one: its exercise catalog
(~1,300+ exercises with GIFs) is imported from a dataset licensed for
personal/educational use only, not commercial use - a legal constraint on
scope, not a stylistic preference. Its edge over an off-the-shelf fitness app
is that it is shaped directly around Max's own real training edge cases as
they come up (recovering a missed session without disturbing the program's
schedule, treating superset sets differently in progress charts, a
lazy-start rule so browsing or preparing a day is never mistaken for
starting it) rather than a generic one-size-fits-all flow.

## Operating Context

Used mobile-first, standing at the gym, mid-workout - often between sets,
one-handed, sometimes sweaty. It needs to be glanceable and fast, not
something to browse leisurely. Runs as an installable PWA with Web Push
(rest-timer and inactivity notifications) and is offline-reliant, which is
why fonts and other static assets are self-hosted rather than pulled from a
CDN. Deployed self-hosted behind BunkerWeb on a real server, pulling a
Docker image published by GitHub Actions on every push to `main`; local
development runs the same stack via Docker Compose. Auth supports Google
OAuth and email/password login.

## Capabilities and Constraints

- Backend: FastAPI + SQLAlchemy + PostgreSQL + Alembic migrations. Frontend:
  server-rendered Jinja2 templates, no JS framework or bundler (vanilla JS
  and CSS only).
- The exercise catalog's license (personal/educational, non-commercial)
  bounds the whole product to personal use - not resale, not a multi-tenant
  commercial deployment.
- A program is a repeating cycle of day templates, each made of blocks of
  exercises. The schedule only ever advances when a day is genuinely
  finished - never from merely viewing, preparing, or starting one.
- Routines can be authored by hand in the UI or imported wholesale from
  JSON, including AI-authored JSON.
- A single day or a whole program can be shared as a public link (no login
  required to view); a logged-in viewer can copy it into their own account
  as an independent copy.

## Evidence on Hand

A real, growing personal workout history and a real exercise catalog under
Max's own account. There are no other users, customers, testimonials, or
commercial evidence, and none should ever be implied or fabricated anywhere
in the product.

## Product Principles

1. Passive viewing, browsing, or preparing never counts as "doing" - only an
   explicit, deliberate action starts or finishes a workout day.
2. Exceptional/manual actions (recovering a missed day, repeating an old
   one) must never corrupt or silently reinterpret real training history.
3. Design for fast, one-handed, mid-set glances - not leisurely browsing.
4. A personal-use tool by design and by license, not a product to monetize
   or scale to tenants.
5. Prefer editing this real, live codebase directly and verifying with
   disposable test data over speculative abstraction.

## Brand Commitments

Product name: "Marmot Fitness App" / "Marmot". All UI copy is written in
Spanish, in a direct, casual, first-person-plural voice ("puedes...",
"vamos a..."). No logo, mascot artwork, or other bound visual asset exists
yet.

## Accessibility & Inclusion

No specific requirement beyond ordinary good practice (contrast, touch
target size, respecting reduced-motion).
