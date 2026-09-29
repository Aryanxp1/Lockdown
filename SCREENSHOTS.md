# Lockdown — Screenshot catalog & visual guide

The [README](README.md) contains a [visual tour](README.md#-visual-tour) with nine primary interface screenshots demonstrating the core workflows across all platform roles (public visitor, organizer, judge, and participant).

Every screenshot captures actual rendered portal state using fixture data seeded via `docker compose up`.

---

## 1. Verified screenshot catalog

All images are committed in the repository at standard resolution with dark-first styling and high-contrast UI borders.

| Figure | Image file | Route | Role / Auth | Key elements displayed |
| :---: | --- | --- | --- | --- |
| **1** | `homepage_thick_borders.png` | `/` | Anonymous | Event title, live statistics, six-stage competition rail, recent submissions |
| **2** | `assests/gallery.png` | `/gallery` | Anonymous | Track filter pills, search input, sort controls, paginated submission cards |
| **3** | `assests/organizer_overview.png` | `/organizer/events/evt_01` | Organizer | Competition controls, headline numbers, judge counts, stage actions |
| **4** | `assests/judge_dashboard.png` | `/judge` | Judge | Personal assignment queue, progress bar, completed and pending reviews |
| **5** | `assests/judge_form.png` | `/judge/evaluate/{id}` | Judge | Weighted rubric criteria, 1–5 scoring rows, draft autosave status, feedback |
| **6** | `assests/judge_caliberation.png` | `/organizer/judges` | Organizer | Judge scoring distributions, mean, standard deviation, and severity labels |
| **7** | `assests/results_published.png` | `/results` | Anonymous | Final leaderboard, raw vs. normalized z-scores, rank badges, prize tags |
| **8** | `assests/audit_trial.png` | `/organizer/events/evt_01/audit` | Organizer | Synchronous append-only log with action timestamps, actors, and events |
| **9** | `assests/participant_workspace.png` | `/participant` | Participant | Team roster, submission status, deadline countdown, issued certificates |

---

## 2. Capture environment & reproduction

To reproduce or update these captures in a local environment:

```bash
# 1. Start the platform with demo accounts and test fixtures
docker compose up -d

# 2. Wait for health check
docker compose ps
```

### Seeded test roles & credentials

All demo accounts share the password `dogfood-demo-2026`:

| Role | Email | Best for |
| --- | --- | --- |
| **Organizer** | `organizer@dogfood.test` | Figures 3, 6, 8 |
| **Judge** | `tomas.varga@example.org` | Figures 4, 5 |
| **Participant** | `priya1@example.org` | Figure 9 |
| **Public** | *(None)* | Figures 1, 2, 7 |

> **Fast login shortcut:** When running locally with `PORTAL_FAST_LOGIN=1`, the navigation bar includes a quick account switcher to jump between roles without re-authenticating.

---

## 3. Image specifications

- **Aspect / Viewport:** `1440 × 900` or `1600 × 1000` desktop viewport.
- **Theme:** Native dark-first monochrome theme with crimson accents and `#4a4e5a` structured borders.
- **Format:** PNG with lossless compression.
- **Chrome:** Window chrome excluded (full page content or clean viewports).
- **Privacy:** 100% synthetic fixture data (`fixtures.json`). No personal data or live secrets.

---

## 4. Hero artwork

The hero banner at the top of the README is an offline SVG asset:
`assests/lockdown-readme-hero (1).svg` (1400 × 760, self-contained SVG without external fonts or remote CDN calls).

---

## 5. Related documentation

- [README.md](README.md) — The visual tour embedding these screenshots.
- [FEATURES.md](FEATURES.md) — Comprehensive route and feature inventory.
- [JUDGING.md](JUDGING.md) — Mathematical specification of scoring in Figures 5, 6, and 7.
- [TESTING.md](TESTING.md) — Automated test verification accompanying the visual pass.
