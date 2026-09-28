"""Centralized view exports for Lockdown."""

from .layout import error_page, render_shell
from .pages_judge import evaluation_form, judge_dashboard
from .pages_organizer import audit_trail, judges_roster, organizer_dashboard, submissions_list
from .pages_participant import participant_dashboard, project_form
from .pages_public import gallery, landing, project_detail, results_leaderboard, signin_form

__all__ = [
    "render_shell", "error_page",
    "landing", "gallery", "project_detail", "results_leaderboard", "signin_form",
    "judge_dashboard", "evaluation_form",
    "participant_dashboard", "project_form",
    "organizer_dashboard", "submissions_list", "judges_roster", "audit_trail",
]
