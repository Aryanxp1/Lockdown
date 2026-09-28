"""Scoring, cross-judge normalization and pairwise ratings.

Everything here is pure: given rows from the database it returns numbers, and
it is the single implementation used by the organizer dashboard, the CSV
export, the public results page and the normalization proof script. There is no
second code path that could disagree with it.

Methodology (the long form lives in JUDGING.md):

  1. A criterion score is an integer from the rubric, 1 to 5.
  2. A review's *raw* score is the rubric-weighted average of its criteria,
     mapped onto 0-100 so that reviewers and organizers can talk about the same
     numbers on every event: raw = (weighted - min) / (max - min) * 100.
  3. Judges are normalised against themselves, not against the field, because
     we have no absolute standard. For each judge with at least MIN_SAMPLE
     completed reviews and non-degenerate spread, z = (raw - judge_mean) /
     judge_sd, then normalized = TARGET_MEAN + TARGET_SD * z, clamped to 0-100.
  4. Judges who cannot be normalised (too few reviews, or every score identical)
     keep their raw score and are flagged, never silently rescaled. A judge who
     gave eleven projects the identical score has told us nothing about the
     relative order, so invention would be worse than honesty.
  5. A project's published score is the mean of the normalized scores of its
     completed reviews, with coverage reported. Missing reviews are never
     imputed as zero.
"""

from __future__ import annotations

import math

from . import db, util

MIN_SAMPLE = 3
MIN_SD = 2.0
TARGET_MEAN = 75.0
TARGET_SD = 12.0

FLAG_LABELS = {
    "insufficient_sample": "too few completed reviews to normalise",
    "zero_variance": "every score identical, cannot normalise",
    "provisional": "fewer reviews than the event requires",
    "no_reviews": "no completed reviews yet",
    "duplicate": "superseded duplicate submission",
    "raw_only": "raw score used unchanged",
}


def flag_labels(flags) -> list[str]:
    return [FLAG_LABELS.get(flag, flag) for flag in flags]


# --- rubrics ------------------------------------------------------------

def active_rubric(event_id: str):
    return db.one("""SELECT * FROM rubrics WHERE event_id = ? AND is_active = 1
                      ORDER BY created_at DESC LIMIT 1""", (event_id,))


def rubric_criteria(rubric_id: str) -> list[dict]:
    if not rubric_id:
        return []
    rows = db.query("SELECT * FROM rubric_criteria WHERE rubric_id = ? ORDER BY seq, key",
                    (rubric_id,))
    return [dict(row) for row in rows]


def criteria_for_event(event_id: str) -> list[dict]:
    rubric = active_rubric(event_id)
    return rubric_criteria(rubric["id"]) if rubric else []


def normalise_weights(criteria) -> list[dict]:
    """Make the weights sum to 1 so a rubric edit cannot silently rescale."""
    total = sum(max(0.0, float(item["weight"])) for item in criteria)
    result = []
    for item in criteria:
        copy = dict(item)
        copy["weight"] = (max(0.0, float(item["weight"])) / total) if total else 0.0
        result.append(copy)
    return result


def weighted_raw(scores: dict, criteria) -> float | None:
    """Rubric-weighted average mapped to 0-100. None when nothing was scored."""
    weighted_sum, weight_total = 0.0, 0.0
    for item in criteria:
        value = scores.get(item["key"])
        if value is None:
            continue
        weight = max(0.0, float(item["weight"]))
        weighted_sum += float(value) * weight
        weight_total += weight
    if weight_total <= 0:
        return None
    low = min(float(item["min_score"]) for item in criteria)
    high = max(float(item["max_score"]) for item in criteria)
    if high <= low:
        return None
    average = weighted_sum / weight_total
    return round(util.clamp((average - low) / (high - low) * 100.0, 0.0, 100.0), 2)


def scores_from_rows(rows) -> dict:
    return {row["criterion_key"]: row["value"] for row in rows}


# --- data access --------------------------------------------------------

REVIEW_QUERY = """
SELECT r.*, p.title AS project_title, p.track_id, p.team_id, p.fixture_id,
       p.status AS project_status, p.superseded_by, p.submitted_at AS project_submitted_at,
       t.name AS team_name, tr.name AS track_name,
       u.name AS judge_name, u.email AS judge_email, u.id AS judge_id
  FROM reviews r
  JOIN projects p ON p.id = r.project_id
  JOIN teams t ON t.id = p.team_id
  LEFT JOIN tracks tr ON tr.id = p.track_id
  JOIN users u ON u.id = r.judge_user_id
 WHERE r.event_id = ?
"""


def load_reviews(event_id: str, *, include_drafts: bool = False, judge_id: str = "",
                 project_id: str = "") -> list[dict]:
    sql, params = REVIEW_QUERY, [event_id]
    if not include_drafts:
        sql += " AND r.status IN ('submitted','finalized')"
    if judge_id:
        sql += " AND r.judge_user_id = ?"
        params.append(judge_id)
    if project_id:
        sql += " AND r.project_id = ?"
        params.append(project_id)
    sql += " ORDER BY p.title, u.name"
    rows = [dict(row) for row in db.query(sql, params)]
    if not rows:
        return []
    ids = tuple(row["id"] for row in rows)
    placeholders = ", ".join("?" for _ in ids)
    score_rows = db.query(
        "SELECT * FROM review_scores WHERE review_id IN (%s) ORDER BY criterion_key"
        % placeholders, list(ids))
    grouped = util.group_by(score_rows, "review_id")
    for row in rows:
        row["scores"] = scores_from_rows(grouped.get(row["id"], []))
    return rows



# --- normalization ------------------------------------------------------

def judge_statistics(reviews) -> dict:
    """Per-judge mean and spread of raw scores, plus severity labelling."""
    grouped = util.group_by(reviews, "judge_user_id")
    stats = {}
    for judge_id, rows in grouped.items():
        values = [row["raw"] for row in rows if row.get("raw") is not None]
        if not values:
            stats[judge_id] = {"n": 0, "mean": None, "sd": None,
                               "flags": ["insufficient_sample"]}
            continue
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        sd = math.sqrt(variance)
        flags = []
        if len(values) < MIN_SAMPLE:
            flags.append("insufficient_sample")
        if sd < MIN_SD:
            flags.append("zero_variance")
        stats[judge_id] = {"n": len(values), "mean": round(mean, 2), "sd": round(sd, 2),
                           "min": round(min(values), 2), "max": round(max(values), 2),
                           "flags": flags}
    present = [row["mean"] for row in stats.values() if row["mean"] is not None]
    event_mean = round(sum(present) / len(present), 2) if present else None
    for stats_row in stats.values():
        if stats_row["mean"] is None or event_mean is None:
            stats_row["severity"] = "unknown"
            stats_row["delta"] = None
            continue
        delta = round(stats_row["mean"] - event_mean, 2)
        stats_row["delta"] = delta
        if "insufficient_sample" in stats_row["flags"]:
            stats_row["severity"] = "unrated"
        elif delta >= 6:
            stats_row["severity"] = "generous"
        elif delta <= -6:
            stats_row["severity"] = "harsh"
        else:
            stats_row["severity"] = "centred"
    return {"judges": stats, "event_mean": event_mean, "event_n": len(reviews)}


def attach_raw(reviews, criteria) -> list[dict]:
    """Fill in `raw` on each review: the stored value when present, else computed."""
    for row in reviews:
        raw = row.get("weighted_raw")
        if raw is None:
            raw = weighted_raw(row.get("scores", {}), criteria)
        row["raw"] = raw
        row.setdefault("flags", [])
    return reviews


def normalize(reviews, criteria) -> dict:
    """Attach raw and normalized scores. Returns the full scoring model."""
    rows = attach_raw(reviews, criteria)
    stats = judge_statistics(rows)
    for row in rows:
        judge_stats = stats["judges"].get(row["judge_user_id"], {})
        raw = row["raw"]
        if raw is None:
            row["normalized"] = None
            row["norm_method"] = "none"
            row["z"] = None
            row["flags"] = ["no_reviews"]
            continue
        sd = judge_stats.get("sd")
        n = judge_stats.get("n") or 0
        if judge_stats.get("mean") is None or sd is None or sd < MIN_SD or n < MIN_SAMPLE:
            row["normalized"] = raw
            row["norm_method"] = "raw_fallback"
            row["z"] = None
            row["flags"] = sorted(set(list(judge_stats.get("flags", [])) + ["raw_only"]))
        else:
            z = (raw - judge_stats["mean"]) / sd
            row["z"] = round(z, 4)
            row["normalized"] = round(util.clamp(TARGET_MEAN + TARGET_SD * z, 0.0, 100.0), 2)
            row["norm_method"] = "zscore_judge"
            row["flags"] = []
    return {
        "reviews": rows,
        "judges": stats["judges"],
        "event_mean": stats["event_mean"],
        "parameters": {"target_mean": TARGET_MEAN, "target_sd": TARGET_SD,
                       "min_sample": MIN_SAMPLE, "min_sd": MIN_SD},
        "formula": "normalized = clamp(75 + 12 * (raw - judge_mean) / judge_sd, 0, 100)",
    }


def rollup(reviews, criteria, *, target_reviews: int = 3) -> list[dict]:
    """Aggregate normalized reviews per project. Missing reviews are not zeros."""
    model = normalize(reviews, criteria)
    grouped = util.group_by(model["reviews"], "project_id")
    projects = []
    for project_id, rows in grouped.items():
        normalized = [row["normalized"] for row in rows if row["normalized"] is not None]
        raw_values = [row["raw"] for row in rows if row["raw"] is not None]
        first = rows[0]
        flags = set()
        for row in rows:
            flags.update(row["flags"])
        if len(normalized) < target_reviews:
            flags.add("provisional")
        projects.append({
            "project_id": project_id,
            "title": first["project_title"],
            "team_id": first["team_id"],
            "team_name": first["team_name"],
            "track_id": first["track_id"],
            "track_name": first["track_name"] or "--",
            "fixture_id": first["fixture_id"],
            "project_status": first["project_status"],
            "review_count": len(normalized),
            "coverage": round(len(normalized) / target_reviews, 2) if target_reviews else 0,
            "raw_mean": round(sum(raw_values) / len(raw_values), 2) if raw_values else None,
            "normalized_mean": round(sum(normalized) / len(normalized), 2) if normalized else None,
            "judges": [{"review_id": row["id"], "judge_id": row["judge_id"],
                        "judge_name": row["judge_name"], "raw": row["raw"],
                        "normalized": row["normalized"], "method": row["norm_method"],
                        "z": row.get("z"), "flags": row["flags"], "comment": row["comment"],
                        "status": row["status"],
                        "submitted_at": row["submitted_at"] or row["updated_at"]}
                       for row in rows],
            "flags": sorted(flags),
            "flag_labels": flag_labels(sorted(flags)),
            "superseded_by": first.get("superseded_by"),
        })
    projects.sort(key=lambda item: (
        item["normalized_mean"] is None,
        -(item["normalized_mean"] or 0),
        item["title"],
    ))
    for index, project in enumerate(projects, start=1):
        project["rank"] = index
    return projects


def scoreboard(event, *, include_drafts: bool = False) -> dict:
    """The one place results are computed: pages, API, CSV and publish all use it."""
    criteria = normalise_weights(criteria_for_event(event["id"]))
    reviews = load_reviews(event["id"], include_drafts=include_drafts)
    model = normalize(reviews, criteria)
    projects = rollup(reviews, criteria, target_reviews=event["target_reviews"] or 3)

    vote_counts = {row["project_id"]: row["count"] for row in db.query(
        "SELECT project_id, COUNT(*) AS count FROM votes WHERE event_id = ? GROUP BY project_id",
        (event["id"],))}
    comment_counts = {row["project_id"]: row["count"] for row in db.query(
        """SELECT p.id AS project_id, COUNT(c.id) AS count
             FROM projects p LEFT JOIN comments c ON c.project_id = p.id AND c.is_hidden = 0
            WHERE p.event_id = ? GROUP BY p.id""", (event["id"],))}
    for project in projects:
        project["votes"] = vote_counts.get(project["project_id"], 0)
        project["comments"] = comment_counts.get(project["project_id"], 0)
    ranked = [project for project in projects if not project["superseded_by"]]
    for index, project in enumerate(ranked, start=1):
        project["published_rank"] = index
    return {"criteria": criteria, "reviews": model["reviews"], "judges": model["judges"],
            "event_mean": model["event_mean"], "parameters": model["parameters"],
            "formula": model["formula"], "projects": projects, "ranked": ranked}


# --- pairwise / Bradley-Terry ------------------------------------------

def bradley_terry(comparisons, *, iterations: int = 200, priors: float = 1.0) -> dict:
    """Fit Bradley-Terry strengths from pairwise wins. Pure and deterministic.

    `comparisons` is an iterable of (winner_id, loser_id). Ties are not modelled
    because the portal only records a winner. One virtual win and one virtual
    loss per competitor keeps an unbeaten project away from infinity.
    """
    pairs = [(winner, loser) for winner, loser in comparisons if winner and loser]
    contenders = sorted({pid for pair in pairs for pid in pair})
    if not contenders:
        return {}
    wins = {pid: priors for pid in contenders}
    played = {pid: 2.0 * priors for pid in contenders}
    for winner, loser in pairs:
        if winner == loser:
            continue
        wins[winner] = wins.get(winner, priors) + 1.0
        played[winner] = played.get(winner, 2.0 * priors) + 1.0
        played[loser] = played.get(loser, 2.0 * priors) + 1.0
    strength = {pid: 1.0 for pid in contenders}
    for _ in range(iterations):
        updated = {}
        for pid in contenders:
            denominator = 0.0
            for other in contenders:
                if other == pid:
                    continue
                total = played[other]
                if total <= 0:
                    continue
                denominator += total / (strength[pid] + strength[other])
            updated[pid] = wins[pid] / denominator if denominator > 0 else wins[pid]
        total = sum(updated.values()) or 1.0
        strength = {pid: value * len(contenders) / total for pid, value in updated.items()}
    ordered = sorted(strength.items(), key=lambda item: (-item[1], item[0]))
    return {pid: round(value, 4) for pid, value in ordered}


def load_comparisons(event_id: str):
    return [dict(row) for row in db.query(
        "SELECT * FROM pairwise_comparisons WHERE event_id = ? ORDER BY created_at",
        (event_id,))]

