# Lockdown — screenshot capture guide

The [README](README.md) has a [visual tour](README.md#-visual-tour) with twelve
figure slots. One is filled; eleven are reserved, each with its filename written
into the caption beside it. This document is the checklist that fills them.

The rule for every shot: **a judge should be able to read the purpose of the page
without you explaining it.** If a screenshot needs a caption to be understood, take
it again with the state that makes it obvious.

---

## 1. Bring up a portal worth photographing

```bash
docker compose up -d          # seeds 3 hackathons, 48 projects, 129 evaluations
docker compose ps             # wait for "healthy"
```

The seed is already a good story, so nothing has to be built by hand:

| Event | id / slug | Seeded state | Good for |
| --- | --- | --- | --- |
| **Sample Hack 2026** | `evt_01` / `sample-hack-2026` | Closed window, judged, **published**, certificates issued, advancements decided | Figures 1, 3, 10, 12 |
| **Autumn Practice Sprint** | `evt_practice` / `autumn-practice-sprint` | Live: submissions open, judging open, **unpublished**, includes a draft project and an evaluation draft | Figures 5, 7, 8, 9 |
| **Zero Dependency 2026** | `evt_zero_dep` / `zero-dependency-2026` | Live, barely judged, its own tracks and rubric weights | Figure 4 |

Sign in with a demo account (password `dogfood-demo-2026`):

| Role | Email | Use it for |
| --- | --- | --- |
| Organizer | `organizer@dogfood.test` | Figures 6, 9, 10, 11 |
| Judge | `tomas.varga@example.org` | Figures 7, 8 |
| Participant | `priya1@example.org` | Figure 12 |
| Nobody | — | Figures 1, 2, 3, 4, 5 |

> **Faster option, demo boxes only.** With `PORTAL_FAST_LOGIN=1` set, the header
> shows a one-click account switcher, which is much quicker than typing
> credentials between shots:
>
> ```powershell
> $env:PORTAL_FAST_LOGIN='1'; docker compose up -d
> ```
>
> Sessions created this way are labelled `demo`, and the flag must be unset again
> before the portal is exposed to anyone you do not trust ([SECURITY.md](SECURITY.md) §12).

If you want an audit trail with more than the four rows a fresh boot creates, do a
few real actions first: sign in and out once per role, open an evaluation, publish
a revision, export the CSV.

---

## 2. Capture settings

| Setting | Value | Why |
| --- | --- | --- |
| Viewport | `1440 × 900` (or `1600 × 1000`) | Wide enough for the gallery grid and the stage rail without wasted horizontal space |
| Device pixel ratio | `2` if your tool supports it | Text stays crisp when GitHub scales the image down |
| Theme | The portal's own dark theme — no browser or OS dark-mode overrides | A light-mode browser chrome around a dark page looks broken |
| Browser chrome | Excluded — capture the page, not the window | The address bar carries no information a judge needs |
| Width | **Identical for every shot** | Figures are rendered at `width="100%"`, so consistent width means consistent scale |
| Format | PNG | Text and flat UI colours compress badly in JPEG |
| File size | Under ~400 KB each | Keeps the repository light; `pngquant`/`oxipng` are optional |
| Crop | Crop dead space at the bottom, keep the top navigation visible | The nav is how a reader orients within the tour |
| Personal data | None. Fixture emails, fixture names and synthetic projects only | The demo data is already synthetic; keep it that way |

Two capture traps worth knowing:

* The portal sends `Cache-Control: no-store` on pages, so a screenshot tool that
  waits for a cache hit will wait forever. Wait for the visible "loading" state to
  clear instead, or capture after a short settle delay.
* Evaluation pages autosave drafts via `fetch`. Wait for the autosave indicator to
  settle before capturing, or the shot will show a spinner.

---

## 3. The twelve slots

Paths are relative to the repository root, exactly as the README references them.
Figure 1 is already supplied; the other eleven are reserved.

| Figure | File | Route | Sign in as | What must be visible |
| :---: | --- | --- | --- | --- |
| **1** | `homepage_thick_borders.png` *(supplied, repo root)* | `/` | nobody | Event identity, stat tiles, the stage pipeline, recent submissions |
| **2** | `assests/screenshots/gallery.png` | `/gallery` | nobody | Track filters, search box, sort control, pagination, project cards with track and team |
| **3** | `assests/screenshots/project_detail.png` | `/gallery/{project_id}` | nobody | Open a card from the gallery instead of typing an id: title, team roster, version history, comment thread with votes |
| **4** | `assests/screenshots/events_directory.png` | `/events` | nobody | Three cover cards with distinct names — the "one install, many hackathons" claim |
| **5** | `assests/screenshots/event_cover.png` | `/events/sample-hack-2026` | nobody | Stage timeline showing open, closed and upcoming states, plus tracks and the prize table |
| **6** | `assests/screenshots/organizer_overview.png` | `/organizer/events/evt_01` | organizer | Event state, headline numbers, organizers, judges, next actions |
| **7** | `assests/screenshots/judge_dashboard.png` | `/judge` | judge A | The assignment queue with progress, and only this judge's work |
| **8** | `assests/screenshots/evaluation_form.png` | `/judge/evaluate/{project_id}` | judge A | Click through from the queue in figure 7: weighted criteria, 1–5 score rows, draft state |
| **9** | `assests/screenshots/judge_calibration.png` | `/organizer/judges` | organizer | Per-judge mean, standard deviation and severity label — the inputs the z-score engine consumes |
| **10** | `assests/screenshots/results_published.png` | `/results` | nobody | Ranked table with raw and normalized means, review counts and the flags column |
| **11** | `assests/screenshots/audit_trail.png` | `/organizer/events/evt_01/audit` | organizer | Rows with action, actor, outcome and timestamp; use the filter so the event scoping is visible |
| **12** | `assests/screenshots/participant_workspace.png` | `/participant` | participant | Team, submission with its deadline state, and the issued certificate card |

Two variations worth having, if you want the tour to make a stronger point:

* **The embargo.** `/events/autumn-practice-sprint/results` is unpublished, so it
  renders the embargo panel with an **empty** table instead of standings. It is a
  good companion to figure 10 and the visual form of the claim that the embargo
  lives in the handler.
* **The draft project.** The practice event contains a draft submission, so figure 5
  or 6 can show the "draft" state next to submitted work.

---

## 4. Putting a shot into the README

Each reserved slot is an HTML comment followed by its caption:

```html
<!-- <img src="assests/screenshots/gallery.png" alt="Public project gallery with track filters" width="100%"> -->
*Figure 2 — Public gallery (`/gallery`) — slot: `assests/screenshots/gallery.png`.*
```

To fill it:

1. Create the folder once, if it does not exist yet:

   ```powershell
   New-Item -ItemType Directory -Force assests\screenshots
   ```

   ```bash
   mkdir -p assests/screenshots
   ```

2. Save the file under the exact name in the table above.
3. Uncomment the `<img>` line, wrap it in a centred paragraph, and change the caption
   so it describes the figure instead of naming the slot:

   ```html
   <p align="center">
     <img src="assests/screenshots/gallery.png" alt="Public project gallery with track filters" width="100%">
   </p>

   *Figure 2 — Public gallery (`/gallery`): track filters, search and pagination.*
   ```

`<img width="100%">` inside a centred paragraph is the markup figure 1 already uses,
so the tour stays visually consistent. Change nothing else when adding an image: the
slot comments, the caption order and the anchor links are what the tour depends on.

---

## 5. The hero banner

The banner at the top of the README is a self-contained SVG, committed as
`assests/lockdown-readme-hero (1).svg` (1400 × 760, no external fonts, no external
references — it keeps the project's offline rule).

It is embedded on line 2:

```html
<p align="center">
  <img src="assests/lockdown-readme-hero%20(1).svg" alt="Lockdown — Run. Judge. Ship. Competition and judging infrastructure." width="100%">
</p>
```

Three notes:

* The **space in the filename has to be percent-encoded** as `%20` in the `src`,
  which is why the path looks unusual. Nothing else needs to change: the file sits
  beside the markdown, so the relative path resolves.
* Optional tidy-up: rename it to `assests/lockdown-readme-hero.svg` and update that
  one `src` value. It makes the path readable in a diff and removes a space from a
  URL. The rename is cosmetic; the banner renders either way.
* The SVG contains SMIL animations (the rotating point cloud and the dashed arcs).
  Where a renderer supports them the banner moves; where it does not, the same frame
  is the static composition. The markdown depends on neither outcome.

---

## 6. Verification checklist

Walk this list before committing images:

- [ ] Every `src` in the README points at a file that exists, with matching case —
      `assests/` is spelled that way on purpose, and paths are case-sensitive on
      Linux.
- [ ] Any path containing a space is percent-encoded.
- [ ] Every `<img>` has an `alt` attribute that describes the page, not the filename.
- [ ] All figures render at the same width, so the tour reads as one document.
- [ ] The caption numbers still run 1…12 in order.
- [ ] The `#-visual-tour` anchor and the README's navigation links still resolve.
- [ ] No screenshot exceeds ~400 KB, and none contains real names, real emails or
      anything that is not fixture data.
- [ ] The screenshots folder is committed; the capture tool's own output directory
      (`.playwright-mcp/`) is not — it is already in `.gitignore`.

---

## 7. Related documents

| Document | Why it is relevant here |
| --- | --- |
| [README.md](README.md) | The tour these images fill, and the captions they belong to |
| [FEATURES.md](FEATURES.md) | Every route, so each figure can be traced to the feature it shows |
| [JUDGING.md](JUDGING.md) | What the numbers in figures 8, 9 and 10 actually mean |
| [TESTING.md](TESTING.md) | The automated verification; screenshots are the manual, visual pass |
| [SECURITY.md](SECURITY.md) | Why `PORTAL_FAST_LOGIN` is acceptable for capture and not for deployment |


