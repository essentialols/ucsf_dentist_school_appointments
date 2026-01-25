"""
GitHub Issues notification system.
Creates issues when new appointment slots are detected.
"""

import os
import logging
from datetime import datetime
from typing import List, Optional

import httpx

from src.slot_checker import AppointmentSlot

logger = logging.getLogger(__name__)


class GitHubNotifier:
    """Sends notifications via GitHub Issues."""

    def __init__(
        self,
        repo: Optional[str] = None,
        token: Optional[str] = None,
    ):
        """
        Initialize GitHub notifier.

        Args:
            repo: Repository in format "owner/repo"
            token: GitHub personal access token with issues scope
        """
        self.repo = repo or os.environ.get("GITHUB_REPOSITORY")
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.api_base = "https://api.github.com"

        if not self.repo:
            logger.warning("GITHUB_REPOSITORY not set - notifications disabled")
        if not self.token:
            logger.warning("GITHUB_TOKEN not set - notifications disabled")

    def _get_headers(self) -> dict:
        """Get headers for GitHub API requests."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def notify_new_slots(self, slots: List[AppointmentSlot]) -> Optional[str]:
        """
        Create a GitHub Issue for new appointment slots.

        Args:
            slots: List of newly available appointment slots

        Returns:
            Issue URL if created successfully, None otherwise
        """
        if not self.repo or not self.token:
            logger.warning("Cannot create issue: missing repo or token")
            return None

        if not slots:
            logger.info("No slots to notify about")
            return None

        # Build issue title
        slot_count = len(slots)
        earliest_date = min(s.date for s in slots)
        title = f"🦷 {slot_count} New Dental Appointment(s) Available - {earliest_date}"

        # Build issue body
        body = self._build_issue_body(slots)

        # Create the issue
        url = f"{self.api_base}/repos/{self.repo}/issues"

        try:
            with httpx.Client() as client:
                response = client.post(
                    url,
                    headers=self._get_headers(),
                    json={
                        "title": title,
                        "body": body,
                        "labels": ["appointment-alert"],
                    },
                    timeout=30,
                )

                if response.status_code == 201:
                    issue_data = response.json()
                    issue_url = issue_data.get("html_url")
                    logger.info(f"Created issue: {issue_url}")
                    return issue_url
                else:
                    logger.error(
                        f"Failed to create issue: {response.status_code} - {response.text}"
                    )
                    return None

        except Exception as e:
            logger.error(f"Error creating GitHub issue: {e}")
            return None

    def _build_issue_body(self, slots: List[AppointmentSlot]) -> str:
        """Build the markdown body for the issue."""
        lines = [
            "## New Appointment Slots Detected",
            "",
            f"**Detected at:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
            "",
            "### Available Slots",
            "",
        ]

        # Group slots by date
        slots_by_date: dict = {}
        for slot in slots:
            if slot.date not in slots_by_date:
                slots_by_date[slot.date] = []
            slots_by_date[slot.date].append(slot)

        for date in sorted(slots_by_date.keys()):
            lines.append(f"#### {date}")
            for slot in sorted(slots_by_date[date], key=lambda s: s.time):
                details = [f"**{slot.time}**"]
                if slot.provider:
                    details.append(f"Provider: {slot.provider}")
                if slot.department:
                    details.append(f"Dept: {slot.department}")
                lines.append(f"- {' | '.join(details)}")
            lines.append("")

        lines.extend([
            "---",
            "",
            "### Quick Links",
            "",
            "[Book Appointment](https://ucsfmychart.ucsfmedicalcenter.org/UCSFMyChart/Scheduling/Embedded)"
            f"?dept=3202010,3202011&vt=1148",
            "",
            "---",
            "*This issue was automatically created by the appointment checker.*",
        ])

        return "\n".join(lines)

    def ensure_label_exists(self) -> bool:
        """Ensure the appointment-alert label exists in the repo."""
        if not self.repo or not self.token:
            return False

        url = f"{self.api_base}/repos/{self.repo}/labels"

        try:
            with httpx.Client() as client:
                # Check if label exists
                response = client.get(
                    f"{url}/appointment-alert",
                    headers=self._get_headers(),
                    timeout=30,
                )

                if response.status_code == 200:
                    return True

                # Create label if it doesn't exist
                if response.status_code == 404:
                    create_response = client.post(
                        url,
                        headers=self._get_headers(),
                        json={
                            "name": "appointment-alert",
                            "color": "d73a4a",  # Red
                            "description": "New dental appointment availability",
                        },
                        timeout=30,
                    )
                    return create_response.status_code == 201

                return False

        except Exception as e:
            logger.warning(f"Could not ensure label exists: {e}")
            return False


def send_notification(slots: List[AppointmentSlot]) -> Optional[str]:
    """
    Convenience function to send notification for new slots.

    Args:
        slots: List of new appointment slots

    Returns:
        Issue URL if created, None otherwise
    """
    notifier = GitHubNotifier()
    notifier.ensure_label_exists()
    return notifier.notify_new_slots(slots)
