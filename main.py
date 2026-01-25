#!/usr/bin/env python3
"""
UCSF Dental School Appointment Checker

Automatically checks for new appointment availability and creates
GitHub Issues when slots become available.

Usage:
    python main.py [--debug] [--dry-run] [--browser] [--no-headless]

Environment Variables:
    GITHUB_TOKEN: GitHub personal access token with issues scope
    GITHUB_REPOSITORY: Repository in format "owner/repo"
"""

import argparse
import logging
import sys
from datetime import date

from src.slot_checker import AppointmentSlot, SlotHistory, compare_slots
from src.notifications import send_notification

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def check_appointments_api(dry_run: bool = False) -> dict:
    """
    Check appointments using direct API calls.

    Args:
        dry_run: If True, don't send notifications or update history

    Returns:
        Dict with check results
    """
    from src.session import EpicSession
    from src.workflow import run_full_workflow, WorkflowError
    from src.slot_checker import SlotParser

    logger.info("Checking appointments via API...")

    result = {
        "success": False,
        "slots_found": 0,
        "new_slots": 0,
        "notification_sent": False,
        "error": None,
        "method": "api",
    }

    try:
        with EpicSession() as session:
            response = run_full_workflow(session, start_date=date.today())
            slots = SlotParser.parse_slots(response)
            result["slots_found"] = len(slots)
            result["slots"] = slots
            result["success"] = True
    except Exception as e:
        logger.error(f"API method failed: {e}")
        result["error"] = str(e)

    return result


def check_appointments_browser(
    headless: bool = True,
    provider_type: str = "student",
    dry_run: bool = False
) -> dict:
    """
    Check appointments using browser automation.

    Args:
        headless: Run browser without visible window
        provider_type: "student" for pre-doctoral clinic, "faculty" for faculty practice
        dry_run: If True, don't send notifications or update history

    Returns:
        Dict with check results
    """
    from src.browser import check_appointments_browser as browser_check

    logger.info(f"Checking {provider_type} appointments via browser (headless={headless})...")

    result = {
        "success": False,
        "slots_found": 0,
        "new_slots": 0,
        "notification_sent": False,
        "error": None,
        "method": "browser",
        "provider_type": provider_type,
    }

    try:
        browser_result = browser_check(headless=headless, provider_type=provider_type)

        if browser_result["success"]:
            # Convert browser slots to AppointmentSlot objects
            slots = []
            for slot_data in browser_result.get("slots", []):
                slot = AppointmentSlot(
                    date=slot_data.get("date", ""),
                    time=slot_data.get("time", ""),
                    provider=slot_data.get("provider"),
                    department=slot_data.get("department"),
                )
                slots.append(slot)

            result["slots_found"] = len(slots)
            result["slots"] = slots
            result["success"] = True
        else:
            result["error"] = browser_result.get("error")
            result["screenshot"] = browser_result.get("screenshot")

    except Exception as e:
        logger.exception(f"Browser method failed: {e}")
        result["error"] = str(e)

    return result


def check_appointments(
    use_browser: bool = True,
    headless: bool = True,
    provider_type: str = "student",
    dry_run: bool = False
) -> dict:
    """
    Main function to check for appointment availability.

    Args:
        use_browser: Use browser automation (more reliable but heavier)
        headless: Run browser without visible window
        provider_type: "student" for pre-doctoral clinic, "faculty" for faculty practice
        dry_run: If True, don't send notifications or update history

    Returns:
        Dict with check results
    """
    logger.info(f"Starting {provider_type} appointment check...")

    result = {
        "success": False,
        "slots_found": 0,
        "new_slots": 0,
        "notification_sent": False,
        "error": None,
        "provider_type": provider_type,
    }

    # Try browser method first (more reliable), fall back to API
    if use_browser:
        check_result = check_appointments_browser(
            headless=headless,
            provider_type=provider_type,
            dry_run=dry_run
        )
    else:
        check_result = check_appointments_api(dry_run=dry_run)

    if not check_result["success"]:
        result["error"] = check_result.get("error", "Check failed")
        return result

    slots = check_result.get("slots", [])
    result["slots_found"] = len(slots)

    logger.info(f"Found {len(slots)} total slots")

    # Load history and compare
    history = SlotHistory()
    previous_slots = history.get_previous_slots()

    comparison = compare_slots(slots, previous_slots)
    new_slots = comparison["new"]
    result["new_slots"] = len(new_slots)

    if new_slots:
        logger.info(f"Detected {len(new_slots)} NEW appointment slots!")
        for slot in new_slots:
            logger.info(f"  - {slot.display_str()}")

        if not dry_run:
            issue_url = send_notification(new_slots)
            result["notification_sent"] = bool(issue_url)
            if issue_url:
                logger.info(f"Created notification issue: {issue_url}")
        else:
            logger.info("Dry run - skipping notification")
    else:
        logger.info("No new slots detected")

    # Update history (unless dry run)
    if not dry_run:
        history.update(slots)
    else:
        logger.info("Dry run - skipping history update")

    result["success"] = True
    return result


def main():
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Check UCSF Dental School appointment availability"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't send notifications or update history",
    )
    parser.add_argument(
        "--api",
        action="store_true",
        help="Use direct API calls instead of browser (less reliable)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Show the browser window (for debugging)",
    )
    parser.add_argument(
        "--faculty",
        action="store_true",
        help="Check faculty appointments instead of student (default: student)",
    )
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    provider_type = "faculty" if args.faculty else "student"

    result = check_appointments(
        use_browser=not args.api,
        headless=not args.no_headless,
        provider_type=provider_type,
        dry_run=args.dry_run,
    )

    # Print summary
    print("\n" + "=" * 50)
    print("APPOINTMENT CHECK SUMMARY")
    print("=" * 50)
    print(f"Provider type: {provider_type.upper()}")
    print(f"Status: {'SUCCESS' if result['success'] else 'FAILED'}")
    print(f"Total slots found: {result['slots_found']}")
    print(f"New slots: {result['new_slots']}")
    print(f"Notification sent: {result['notification_sent']}")
    if result["error"]:
        print(f"Error: {result['error']}")
    print("=" * 50)

    # Exit with error code if failed
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
