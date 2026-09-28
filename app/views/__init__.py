"""Centralized view exports for Lockdown."""

from .layout import error_page, render_shell
from .pages_events import (event_directory, event_page, results_directory,
                           results_scope_note)
from .pages_judge import evaluation_form, judge_dashboard
from .pages_manage import (event_assignments_page, event_form, event_judges_page,
                           event_overview, event_results_page, event_reviews_page,
                           event_roster_page, event_settings_page, event_stages_page,
                           manage_home)
from .pages_organizer import audit_trail, judges_roster, submissions_list
from .pages_participant import participant_dashboard, project_form
from .pages_public import gallery, landing, project_detail, results_leaderboard, signin_form

__all__ = [
    "render_shell", "error_page",
    "landing", "gallery", "project_detail", "results_leaderboard", "signin_form",
    "event_directory", "event_page", "results_directory", "results_scope_note",
    "manage_home", "event_form", "event_overview", "event_stages_page",
    "event_roster_page", "event_assignments_page", "event_reviews_page",
    "event_settings_page", "event_judges_page", "event_results_page",
    "judge_dashboard", "evaluation_form",
    "participant_dashboard", "project_form",
    "submissions_list", "judges_roster", "audit_trail",
]
