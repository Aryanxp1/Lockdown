# Lockdown — judging & scoring

Lockdown implements a deterministic scoring engine that evaluates submissions,
calibrates for judge harshness and generosity using cross-judge z-score
normalization, and freezes final rankings for public release.

This document details the mathematical models, formulas, edge-case fallbacks,
and the exact step-by-step arithmetic from a real evaluation in the dataset.

---

## 1. Rubric model & weighted raw scores

### Criteria configuration
Events define an active rubric composed of weighted criteria (`app/scoring.py:58`).
Weights are normalized so they sum to `1.0`:

$$\text{effective\_weight}_i = \frac{w_i}{\sum_{k} w_k}$$

The official 2026 hackathon rubric (`rub_default`) defines three criteria on an
integer scale of 1 to 5:

| Criterion | Key | Range | Raw Weight | Effective Weight |
| --- | --- | :---: | :---: | :---: |
| Functionality | `functionality` | 1..5 | 0.40 | 0.40 |
| Build Quality | `quality` | 1..5 | 0.30 | 0.30 |
| Innovation | `innovation` | 1..5 | 0.30 | 0.30 |

### Raw score formula
A judge assigns integer ratings $v_i \in [1, 5]$. The weighted average on the
original rubric scale is:

$$\bar{v} = \sum_{i} \left( v_i \times \text{effective\_weight}_i \right)$$

This is mapped linearly to a percentage scale of 0 to 100:

$$\text{raw} = \frac{\bar{v} - \min}{\max - \min} \times 100 = \frac{\bar{v} - 1}{5 - 1} \times 100$$

*(Reference: `app/scoring.py:83`)*

---

## 2. Cross-judge normalization (z-score)

### Why normalize?
In hackathons with distributed judging rosters, different judges exhibit
systematic bias: some judges consistently give 90s, while others cap their top
scores at 65. If a project happens to draw three harsh judges, its raw average
will be penalized.

Lockdown normalizes scores across a judge's portfolio to rescale their
distribution to a common mean and standard deviation:
* **Target mean ($\mu_T$):** `75.0`
* **Target standard deviation ($\sigma_T$):** `12.0`
* **Minimum sample size ($N_{\min}$):** `3` evaluations
* **Minimum standard deviation ($\sigma_{\min}$):** `2.0`

### Per-judge baseline
For a judge who has submitted $N$ reviews with raw scores $r_1, r_2, \dots, r_N$:

$$\mu_J = \frac{1}{N} \sum_{k=1}^{N} r_k$$

$$\sigma_J = \sqrt{\frac{1}{N} \sum_{k=1}^{N} (r_k - \mu_J)^2}$$

*(Reference: `app/scoring.py:126`)*

### Normalization formula
When $N \ge 3$ and $\sigma_J \ge 2.0$, each raw score $r$ is mapped via its
standard score $z$:

$$z = \frac{r - \mu_J}{\sigma_J}$$

$$\text{normalized} = \text{clamp}\left(\mu_T + (\sigma_T \times z), 0, 100\right) = \text{clamp}\left(75 + (12 \times z), 0, 100\right)$$

The review record stores `norm_method = 'zscore_judge'`.

### Fallback & flags
If $N < 3$ or $\sigma_J < 2.0$, z-scoring cannot reliably calculate the
judge's variance. The engine falls back to the uncalibrated score:
* $\text{normalized} = r$
* `norm_method = 'raw_fallback'`
* Flags assigned:
  * `insufficient_sample` if $N < 3$
  * `zero_variance` if $\sigma_J < 2.0$

Across the 126 seeded reviews in `evt_01`, 109 are successfully calibrated via
`zscore_judge` and 17 use `raw_fallback`.

---

## 3. Verified worked example

Below is the step-by-step arithmetic computed by the portal engine for
review `rev_fx_016` (evaluating *Dry Compass* by judge `usr_jdg_24`):

### Judge profile (`usr_jdg_24`)
* Total completed reviews: $N = 11$
* Judge mean score: $\mu_J = 58.64$
* Judge standard deviation: $\sigma_J = 15.28$
* Severity classification: `centred` (mean within $\pm 6.0$ points of event target)

### Review inputs (`rev_fx_016`)
* Functionality ($w = 0.40$): $2.0$
* Build Quality ($w = 0.30$): $3.0$
* Innovation ($w = 0.30$): $5.0$

### Step 1: Weighted raw score
$$\bar{v} = (2.0 \times 0.40) + (3.0 \times 0.30) + (5.0 \times 0.30) = 0.80 + 0.90 + 1.50 = 3.20$$

$$\text{raw} = \frac{3.20 - 1.0}{4.0} \times 100 = 0.55 \times 100 = 55.00$$

### Step 2: Z-score calculation
Because $N = 11 \ge 3$ and $\sigma_J = 15.28 \ge 2.0$, normalisation proceeds:

$$z = \frac{55.00 - 58.64}{15.28} = \frac{-3.64}{15.28} \approx -0.2382$$

### Step 3: Rescaling to target distribution
$$\text{normalized} = 75.0 + (12.0 \times -0.2382) = 75.0 - 2.8584 = 72.14$$

The review is assigned `normalized = 72.14` with `norm_method = 'zscore_judge'`.

---

## 4. Project rollup & ranking

### Scoreboard calculation
`scoring.scoreboard(event)` (`app/scoring.py:317`) computes the final project
standings:
1. **Normalized project mean:** Arithmetic mean of all normalized reviews
   submitted for the project.
2. **Raw project mean:** Arithmetic mean of raw uncalibrated scores (stored for
   comparison and transparency).
3. **Coverage:**
   $$\text{coverage} = \frac{\text{completed\_reviews}}{\text{target\_reviews}}$$
   Projects with coverage $< 1.0$ receive the `provisional` flag.
4. **Exclusions:**
   * Unsubmitted drafts are ignored.
   * Superseded duplicates (e.g. `prj_07` replaced by `prj_41`) are excluded.
5. **Ranking order:** Projects are sorted primarily by `normalized_mean` descending.

### Official event top 3 standings:
| Rank | Project Title | Raw Mean | Normalized Mean | Reviews | Coverage | Flags |
| :---: | --- | :---: | :---: | :---: | :---: | :---: |
| **#1** | **Iron Switch** | 84.17 | **90.36** | 3 | 1.00 | None |
| **#2** | **Slow Trail** | 75.83 | **86.35** | 3 | 1.00 | None |
| **#3** | **Salt Ledger** | 84.38 | **85.93** | 4 | 1.33 | None |


---

## 5. Review lifecycle & cryptographic integrity

1. **Assignment:** Organizers pair judges to submissions in `assignments`.
2. **Drafting & Autosave:** Judges enter ratings. Partial progress is saved as
   `draft` in `reviews` and appends a snapshot to `review_revisions`.
3. **Submission & Normalization:** When submitted:
   * Status transitions to `finalized`.
   * A cryptographic HMAC-SHA256 signature is calculated over the score payload
     using the server's `portal_secret` (`app/security.py:68`) and saved in `reviews.signature`.
   * `scoring.refresh_normalization(event_id)` recalculates normalization
     parameters across all finalized evaluations for the event.

---

## 6. Embargo & results publication

* **Embargo rules:** Individual evaluation scores, rankings, and judge identities
  remain hidden from participants and the public while judging is open or until
  an organizer explicitly publishes results.
* **Publication freeze (`result_publications`):** When published via
  `POST /organizer/publish`, the current leaderboard is written into a
  frozen JSON snapshot along with an immutable SHA-256 checksum.
* **CSV Exports:** The CSV endpoint (`GET /api/export.csv`) serves the frozen
  snapshot if one exists, ensuring published rankings remain stable even if
  underlying data changes.

