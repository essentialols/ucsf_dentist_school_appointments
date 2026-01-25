"""
Playwright-based browser automation for Epic MyChart scheduling.
Uses a headless browser to navigate the scheduling workflow.
"""

import logging
import re
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from playwright.sync_api import sync_playwright, Page, Browser, TimeoutError as PlaywrightTimeout

import config

logger = logging.getLogger(__name__)


class SchedulingBrowser:
    """Automates the UCSF MyChart scheduling page using Playwright."""

    # The correct entry point with the proper questionnaire flow
    SCHEDULING_PAGE_URL = "https://schedule.ucsfmedicalcenter.org/dentistry/"

    # Direct iframe URL (fallback)
    IFRAME_URL = (
        "https://ucsfmychart.ucsfmedicalcenter.org/ucsfmychart/openscheduling/embedded"
        "?apikey=uiYEvdRgacwG814&widgetid=MyChartIframe0&dept=3202010,3202011&vt=1148"
    )

    # Questionnaire options
    REASON_FOR_VISIT = "Dental exams"  # First dropdown selection

    # Provider type selection (appears as togglebutton options)
    PROVIDER_TYPE_STUDENT = "Student"
    PROVIDER_TYPE_FACULTY = "Faculty"

    # Default questionnaire answers
    DEFAULT_ANSWERS = {
        "age": "Yes",           # Is patient 15+ years old?
        "insurance": "Self Pay", # Insurance type
    }

    def __init__(self, headless: bool = True, provider_type: str = "student"):
        """
        Initialize browser automation.

        Args:
            headless: Run browser without visible window
            provider_type: "student" for pre-doctoral clinic, "faculty" for faculty practice
        """
        self.headless = headless
        self.provider_type = provider_type.lower()
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.iframe = None  # Will be set if page uses iframe

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def start(self):
        """Start the browser."""
        logger.info("Starting Playwright browser...")
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        self.page = self.browser.new_page(
            user_agent=config.USER_AGENT,
            viewport={'width': 1280, 'height': 900}
        )
        self.page.set_extra_http_headers({
            'Accept-Language': 'en-US,en;q=0.9',
        })
        logger.info("Browser started successfully")

    def close(self):
        """Close the browser."""
        if self.page:
            self.page.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        logger.info("Browser closed")

    def wait_for_load(self, timeout: int = 15000):
        """Wait for page to finish loading."""
        try:
            self.page.wait_for_load_state('networkidle', timeout=timeout)
        except PlaywrightTimeout:
            logger.warning("Timeout waiting for network idle")

    def _click_label_option(self, text: str) -> bool:
        """Click a toggle button label by text."""
        ctx = self._get_context()
        label = ctx.locator(f"label.togglebutton:has-text('{text}')")
        if label.count() > 0:
            label.first.click()
            time.sleep(0.5)
            return True
        return False

    def _click_continue(self) -> bool:
        """Click the continue button if enabled."""
        ctx = self._get_context()
        continue_btn = ctx.locator("#scheduling-continue:not([disabled]), #next-step:not([disabled]), button:has-text('Continue'):not([disabled])")
        try:
            continue_btn.first.click(timeout=5000)
            self.wait_for_load()
            time.sleep(1)
            return True
        except:
            return False

    def _get_page_content(self) -> str:
        """Get text content of the main scheduling area."""
        ctx = self._get_context()
        try:
            # For iframe context, get all text
            if self.iframe:
                return ctx.locator("body").inner_text(timeout=5000)
            else:
                main = self.page.query_selector("main, #scheduling-workflow-container")
                return main.inner_text() if main else self.page.inner_text("body")
        except:
            return ""

    def navigate_to_scheduling(self) -> bool:
        """Navigate to the scheduling page and handle iframe."""
        logger.info(f"Navigating to {self.SCHEDULING_PAGE_URL}")
        try:
            self.page.goto(self.SCHEDULING_PAGE_URL, wait_until='domcontentloaded')
            self.wait_for_load()
            time.sleep(2)

            # Check if there's an iframe and switch to it
            iframe = self.page.frame_locator("iframe").first
            if iframe:
                logger.info("Found iframe, switching context")
                self.iframe = iframe
            else:
                logger.info("No iframe found, using main page")
                self.iframe = None

            logger.info(f"Page loaded: {self.page.title()[:50]}")
            return True
        except Exception as e:
            logger.error(f"Failed to navigate: {e}")
            return False

    def _get_context(self):
        """Get the current context (iframe or page)."""
        return self.iframe if self.iframe else self.page

    def select_reason_for_visit(self) -> bool:
        """Select 'Dental exams' from the reason for visit dropdown."""
        logger.info(f"Selecting reason for visit: {self.REASON_FOR_VISIT}")
        try:
            ctx = self._get_context()

            # First, try standard select element
            try:
                select = ctx.locator("select").first
                if select.count() > 0:
                    # Get all options and find the one matching our reason
                    select.select_option(label=self.REASON_FOR_VISIT)
                    time.sleep(1)
                    logger.info(f"Selected {self.REASON_FOR_VISIT} from standard dropdown")
                    return True
            except Exception as e:
                logger.debug(f"Standard select failed: {e}")

            # Try clicking the dropdown to open it, then selecting
            try:
                # Click on the dropdown div to open it
                dropdown_trigger = ctx.locator(".dropdown, [role='combobox'], .select-wrapper").first
                if dropdown_trigger.count() > 0:
                    dropdown_trigger.click()
                    time.sleep(0.5)

                    # Now click on the option
                    option = ctx.get_by_text(self.REASON_FOR_VISIT, exact=True)
                    if option.count() > 0:
                        option.first.click()
                        time.sleep(1)
                        logger.info(f"Selected {self.REASON_FOR_VISIT} from custom dropdown")
                        return True
            except Exception as e:
                logger.debug(f"Custom dropdown failed: {e}")

            # Try clicking directly on text (might be visible option list)
            option = ctx.get_by_text(self.REASON_FOR_VISIT, exact=True)
            if option.count() > 0:
                option.first.click()
                time.sleep(1)
                logger.info(f"Clicked on {self.REASON_FOR_VISIT}")
                return True

            logger.warning("Could not find reason for visit dropdown")
            return False
        except Exception as e:
            logger.error(f"Error selecting reason for visit: {e}")
            return False

    def select_provider_type(self) -> bool:
        """Select Student or Faculty provider type."""
        if self.provider_type == "student":
            selection = self.PROVIDER_TYPE_STUDENT
            logger.info(f"Selecting STUDENT provider type")
        else:
            selection = self.PROVIDER_TYPE_FACULTY
            logger.info(f"Selecting FACULTY provider type")

        try:
            ctx = self._get_context()

            # Look for togglebutton label with the provider type
            label = ctx.locator(f"label.togglebutton:has-text('{selection}')")
            if label.count() > 0:
                label.first.click()
                time.sleep(0.5)
                logger.info(f"Selected provider type: {selection}")
                return True

            # Try direct text click
            element = ctx.get_by_text(selection, exact=True)
            if element.count() > 0:
                element.first.click()
                time.sleep(0.5)
                logger.info(f"Clicked provider type: {selection}")
                return True

            logger.warning(f"Could not find provider type option: {selection}")
            return False
        except Exception as e:
            logger.error(f"Error selecting provider type: {e}")
            return False

    def answer_questionnaire(self) -> bool:
        """Answer the pre-scheduling questionnaire."""
        logger.info("Answering questionnaire...")
        ctx = self._get_context()

        max_questions = 10
        for q_num in range(1, max_questions + 1):
            time.sleep(1)  # Allow page to update
            content = self._get_page_content()

            logger.debug(f"Step {q_num} content: {content[:300]}")

            # Check if we've reached the slots page
            if "Select a time" in content:
                logger.info("Reached appointment slots page")
                return True

            # Check for no availability message
            if "no available times" in content.lower() or "no availability" in content.lower():
                logger.info("No appointments available (this is expected for student clinic)")
                return True

            # Check for "call us" dead end
            if "call us" in content.lower() or "next steps" in content.lower():
                logger.warning("Hit dead end - questionnaire requires phone call")
                return False

            # Log the page content for debugging
            questions = [l.strip() for l in content.split('\n') if '?' in l and len(l) < 150]
            if questions:
                logger.info(f"Q{q_num}: {questions[0]}")

            # Handle different question types

            # Reason for visit dropdown (first question)
            if "reason for visit" in content.lower():
                logger.info("Found reason for visit question")
                try:
                    select = ctx.locator("select").first
                    if select.count() > 0:
                        # Select "Dental exams" by label
                        select.select_option(label=self.REASON_FOR_VISIT)
                        logger.info(f"Selected {self.REASON_FOR_VISIT}")
                        time.sleep(0.5)
                        self._click_continue()
                        continue
                except Exception as e:
                    logger.debug(f"Dropdown selection error: {e}")

            # Provider type question (Student/Faculty/Resident)
            if "student" in content and "faculty" in content:
                logger.info("Found provider type question")
                if self.select_provider_type():
                    self._click_continue()
                    continue

            # Age question
            if "age" in content.lower() or "years old" in content.lower() or "15" in content:
                logger.info("Answering age question: Yes")
                if self._click_label_option(self.DEFAULT_ANSWERS["age"]):
                    self._click_continue()
                    continue

            # Insurance question
            if "insurance" in content.lower() or "self pay" in content.lower():
                logger.info(f"Answering insurance question: {self.DEFAULT_ANSWERS['insurance']}")
                if self._click_label_option(self.DEFAULT_ANSWERS["insurance"]):
                    self._click_continue()
                    continue

            # If there's a dropdown that hasn't been handled, try to select appropriate option
            try:
                select = ctx.locator("select").first
                if select.count() > 0:
                    # Try to select "Dental exams" or "Cleanings" if available
                    try:
                        select.select_option(label=self.REASON_FOR_VISIT)
                        logger.info(f"Selected {self.REASON_FOR_VISIT} from dropdown")
                    except:
                        # Fall back to first non-empty option
                        select.select_option(index=1)
                        logger.info("Selected first dropdown option")
                    time.sleep(0.5)
                    self._click_continue()
                    continue
            except:
                pass

            # Try clicking Student toggle button
            try:
                student_label = ctx.locator("label.togglebutton:has-text('Student')")
                if student_label.count() > 0:
                    student_label.first.click()
                    logger.info("Clicked Student toggle button")
                    time.sleep(0.5)
                    self._click_continue()
                    continue
            except:
                pass

            # Try clicking any toggle button if nothing else worked
            try:
                labels = ctx.locator("label.togglebutton").all()
                if labels:
                    labels[0].click()
                    logger.info("Clicked first available toggle button")
                    time.sleep(0.5)
                    self._click_continue()
                    continue
            except:
                pass

            # Check if we're stuck
            logger.warning(f"Could not determine question type on step {q_num}")
            if not self._click_continue():
                logger.warning("No progress made, breaking loop")
                break

        return True

    def extract_slots(self) -> List[Dict[str, Any]]:
        """Extract available appointment slots from the page."""
        logger.info("Extracting appointment slots...")
        slots = []

        try:
            time.sleep(2)  # Allow page to fully render
            content = self._get_page_content()

            logger.debug(f"Page content preview: {content[:500]}")

            # Check for no availability message (but only if it's the main message)
            if "no available times are found" in content.lower():
                logger.info("No appointment slots available")
                return []

            # Check if we're on the slots page (look for date patterns or AM/PM times)
            has_time_slots = re.search(r'\d{1,2}:\d{2}\s*(?:AM|PM)', content)
            has_date = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s*\d{4}', content)

            if not has_time_slots and not has_date:
                logger.warning("Not on slots page")
                logger.debug(f"Content: {content[:1000]}")
                return []

            logger.info("Found appointment time slots on page")

            # Parse slots from content
            # Actual format: "8:30 AM\non Wednesday August 5, 2026 at UCSF Dental Center... with Ramneek Rai."
            # Pattern groups: time, day_name, month, day, year, location, provider
            slot_pattern = r'(\d{1,2}:\d{2}\s*(?:AM|PM))\s*\non\s+(\w+)\s+(\w+)\s+(\d{1,2}),\s*(\d{4})\s+at\s+([^.]+?)\s+with\s+([^.]+)\.'

            matches = re.findall(slot_pattern, content, re.IGNORECASE | re.MULTILINE)
            logger.debug(f"Pattern matches: {len(matches)}")

            for match in matches:
                time_str = match[0]
                day_name = match[1]
                month = match[2]
                day = match[3]
                year = match[4]
                location = match[5]
                provider = match[6]

                date_str = f"{month} {day}, {year}"

                slot = {
                    "date": date_str,
                    "time": time_str.strip(),
                    "provider": provider.strip() if provider else None,
                    "department": location.strip() if location else None,
                    "day_of_week": day_name,
                    "provider_type": self.provider_type,
                }
                slots.append(slot)
                logger.debug(f"Found slot: {date_str} {time_str} with {provider}")

            # Deduplicate
            seen = set()
            unique_slots = []
            for slot in slots:
                key = (slot["date"], slot["time"], slot.get("provider", ""))
                if key not in seen:
                    seen.add(key)
                    unique_slots.append(slot)

            logger.info(f"Extracted {len(unique_slots)} appointment slots")
            return unique_slots

        except Exception as e:
            logger.error(f"Error extracting slots: {e}")
            return []

    def take_screenshot(self, filename: str = "data/debug_screenshot.png"):
        """Take a screenshot for debugging."""
        try:
            import os
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            self.page.screenshot(path=filename, full_page=True)
            logger.info(f"Screenshot saved to {filename}")
        except Exception as e:
            logger.warning(f"Could not save screenshot: {e}")


def check_appointments_browser(
    headless: bool = True,
    provider_type: str = "student"
) -> Dict[str, Any]:
    """
    Check for appointments using browser automation.

    Uses the correct entry point at schedule.ucsfmedicalcenter.org/dentistry/
    which embeds the scheduling widget with the proper questionnaire flow.

    Args:
        headless: Run browser without visible window
        provider_type: "student" for pre-doctoral clinic, "faculty" for faculty practice

    Returns:
        Dict with slot data and status
    """
    result = {
        "success": False,
        "slots": [],
        "error": None,
        "screenshot": None,
        "provider_type": provider_type,
    }

    try:
        with SchedulingBrowser(headless=headless, provider_type=provider_type) as browser:
            # Step 1: Navigate to scheduling page (handles iframe)
            if not browser.navigate_to_scheduling():
                result["error"] = "Failed to navigate to scheduling page"
                browser.take_screenshot("data/error_navigate.png")
                result["screenshot"] = "data/error_navigate.png"
                return result

            browser.take_screenshot("data/step1_navigate.png")

            # Step 2: Select reason for visit from dropdown
            if not browser.select_reason_for_visit():
                browser.take_screenshot("data/error_reason.png")
                result["screenshot"] = "data/error_reason.png"
                # Continue anyway - might not need this step
                logger.warning("Could not select reason for visit, continuing...")

            browser.take_screenshot("data/step2_reason.png")

            # Step 3: Answer questionnaire (includes provider type, age, insurance)
            browser.answer_questionnaire()

            browser.take_screenshot("data/step3_questionnaire.png")

            # Step 4: Extract slots
            slots = browser.extract_slots()

            # Take final screenshot
            browser.take_screenshot("data/last_check.png")
            result["screenshot"] = "data/last_check.png"

            result["success"] = True
            result["slots"] = slots

            logger.info(f"Check complete: {len(slots)} {provider_type} slots found")

    except Exception as e:
        logger.exception(f"Browser automation error: {e}")
        result["error"] = str(e)

    return result
