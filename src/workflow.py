"""
Epic MyChart scheduling workflow implementation.
Handles the multi-step workflow required to access appointment slots.
"""

import re
import json
import logging
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from urllib.parse import urlencode

from src.session import EpicSession
import config

logger = logging.getLogger(__name__)


class WorkflowError(Exception):
    """Raised when a workflow step fails."""
    pass


def epic_date_to_int(d: date) -> int:
    """
    Convert a Python date to Epic's internal date format.
    Epic dates are days since December 31, 1840.
    """
    epoch = date(
        config.EPIC_DATE_EPOCH_YEAR,
        config.EPIC_DATE_EPOCH_MONTH,
        config.EPIC_DATE_EPOCH_DAY
    )
    delta = d - epoch
    return delta.days


def int_to_epic_date(epic_int: int) -> date:
    """Convert Epic's internal date integer back to a Python date."""
    from datetime import timedelta
    epoch = date(
        config.EPIC_DATE_EPOCH_YEAR,
        config.EPIC_DATE_EPOCH_MONTH,
        config.EPIC_DATE_EPOCH_DAY
    )
    return epoch + timedelta(days=epic_int)


class EpicWorkflow:
    """
    Manages the Epic MyChart scheduling workflow.

    The workflow must be executed in order:
    1. Initialize workflow (get session tokens)
    2. Answer questionnaire questions (3 required)
    3. Validate location
    4. Get available slots
    """

    def __init__(self, session: EpicSession):
        self.session = session
        self.workflow_data: Dict[str, Any] = {}
        self.questionnaire_questions: List[Dict[str, Any]] = []
        self.current_question_index = 0

    def _build_referer(self) -> str:
        """Build the referer URL with department and visit type parameters."""
        params = {
            "dept": config.DEPARTMENT_IDS,
            "vt": config.VISIT_TYPE,
        }
        return f"{config.BASE_URL}/Scheduling/Embedded?{urlencode(params)}"

    def _extract_widget_header(self, response_text: str) -> Optional[str]:
        """Extract __widgetheader token from response."""
        # Try JSON response first
        try:
            data = json.loads(response_text)
            if "WidgetHeader" in data:
                return data["WidgetHeader"]
            if "__widgetheader" in data:
                return data["__widgetheader"]
        except json.JSONDecodeError:
            pass

        # Try regex patterns for HTML/JS responses
        patterns = [
            r'__widgetheader["\']?\s*[:=]\s*["\']([^"\']+)["\']',
            r'WidgetHeader["\']?\s*[:=]\s*["\']([^"\']+)["\']',
            r'"__widgetheader":"([^"]+)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, response_text)
            if match:
                return match.group(1)

        return None

    def _extract_tokens(self, response_text: str, token_prefix: str = "WP-") -> List[str]:
        """Extract opaque tokens (WP-24...) from response."""
        pattern = rf'({token_prefix}[A-Za-z0-9_-]+)'
        return list(set(re.findall(pattern, response_text)))

    def _extract_questionnaire_data(self, response_text: str) -> Dict[str, Any]:
        """Extract questionnaire questions and answer options from response."""
        try:
            data = json.loads(response_text)
            return data
        except json.JSONDecodeError:
            logger.warning("Could not parse questionnaire response as JSON")
            return {}

    def load_embedded_page(self) -> str:
        """
        Step 0: Load the embedded scheduling page to establish context.

        This must be called first to get cookies and initial page state.

        Returns:
            HTML content of the page
        """
        logger.info("Loading embedded scheduling page...")

        params = {
            "dept": config.DEPARTMENT_IDS,
            "vt": config.VISIT_TYPE,
        }

        response = self.session.get(
            f"/Scheduling/Embedded?dept={config.DEPARTMENT_IDS}&vt={config.VISIT_TYPE}",
            referer=config.BASE_URL,
        )

        if response.status_code != 200:
            raise WorkflowError(f"Failed to load embedded page: {response.status_code}")

        html = response.text
        logger.debug(f"Embedded page loaded, length: {len(html)}")

        # Extract widget header from the page
        widget_header = self._extract_widget_header(html)
        if widget_header:
            self.session.widget_header = widget_header
            logger.info("Extracted widget header from embedded page")

        # Extract any WP- tokens from the page
        tokens = self._extract_tokens(html)
        if tokens:
            logger.info(f"Found {len(tokens)} WP- tokens in embedded page")
            self.workflow_data["initial_tokens"] = tokens

        # Look for JSON data embedded in the page
        self._extract_embedded_json(html)

        return html

    def _extract_embedded_json(self, html: str):
        """Extract JSON data embedded in script tags."""
        # Look for various patterns of embedded JSON
        patterns = [
            r'var\s+schedulingData\s*=\s*(\{.*?\});',
            r'window\.schedulingConfig\s*=\s*(\{.*?\});',
            r'data-scheduling-config=["\'](\{.*?\})["\']',
            r'"OpenScheduling"\s*:\s*(\{.*?\})',
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    self.workflow_data.update(data)
                    logger.info(f"Extracted embedded JSON data")
                    break
                except json.JSONDecodeError:
                    continue

    def initialize_workflow(self) -> bool:
        """
        Step 1: Initialize the scheduling workflow.

        This establishes the session and retrieves initial tokens.

        Returns:
            True if initialization succeeded
        """
        logger.info("Initializing scheduling workflow...")

        # Build initial request data
        data = {
            "widgetid": config.WIDGET_ID,
            "dept": config.DEPARTMENT_IDS,
            "vt": config.VISIT_TYPE,
            "reasonforvisit": config.REASON_FOR_VISIT,
            "IsAnonymous": "true",
            "IsAuthenticatedWidget": "false",
        }

        # Include widget header if we have one from the embedded page
        if self.session.widget_header:
            data["__widgetheader"] = self.session.widget_header

        response = self.session.post(
            config.ENDPOINTS["init_workflow"],
            data=data,
            referer=self._build_referer(),
        )

        if response.status_code != 200:
            raise WorkflowError(f"Workflow init failed: {response.status_code}")

        # Extract widget header
        widget_header = self._extract_widget_header(response.text)
        if widget_header:
            self.session.widget_header = widget_header
            logger.info("Successfully extracted widget header")
        else:
            logger.warning("Could not extract widget header from response")

        # Store workflow data
        try:
            self.workflow_data = response.json()
            logger.debug(f"Workflow data keys: {list(self.workflow_data.keys())}")
        except json.JSONDecodeError:
            logger.warning("Could not parse workflow init response as JSON")
            self.workflow_data = {"raw": response.text}

        # Extract any questionnaire info from initial response
        self._parse_initial_questionnaire()

        return True

    def _parse_initial_questionnaire(self):
        """Parse questionnaire questions from workflow data."""
        # The questionnaire structure varies - we need to find questions
        # Look for common patterns in Epic responses

        if "Questions" in self.workflow_data:
            self.questionnaire_questions = self.workflow_data["Questions"]
        elif "questionnaire" in self.workflow_data:
            self.questionnaire_questions = self.workflow_data["questionnaire"].get("Questions", [])
        elif "Questionnaire" in self.workflow_data:
            q_data = self.workflow_data["Questionnaire"]
            if isinstance(q_data, dict):
                self.questionnaire_questions = q_data.get("Questions", [])

        logger.info(f"Found {len(self.questionnaire_questions)} questionnaire questions")

    def _build_questionnaire_payload(
        self,
        question_id: str,
        answer_id: str,
        question_index: int = 0
    ) -> Dict[str, str]:
        """
        Build the payload for answering a questionnaire question.

        Epic uses a complex nested structure that we flatten into form data.
        """
        payload = {
            "workflow.Type": "12",  # Scheduling workflow type
            "workflow.IsAnonymous": "true",
            "workflow.IsAuthenticatedWidget": "false",
            "workflow.SchedulingControllerParams.dept": config.DEPARTMENT_IDS,
            "workflow.SchedulingControllerParams.vt": config.VISIT_TYPE,
            f"appointmentBuilder.Appointments[0].LqfIds[{question_index}]": question_id,
            f"appointmentBuilder.Appointments[0].PatientAnswerIds[{question_index}]": answer_id,
        }

        # Add widget header if available
        if self.session.widget_header:
            payload["__widgetheader"] = self.session.widget_header

        return payload

    def answer_questionnaire(
        self,
        question_id: str,
        answer_id: str,
        question_index: int = 0
    ) -> Dict[str, Any]:
        """
        Step 2: Answer a questionnaire question.

        Args:
            question_id: The LQF ID of the question (WP-24... token)
            answer_id: The answer ID to select (WP-24... token)
            question_index: Index of this question (0, 1, 2)

        Returns:
            Response data containing next question or status
        """
        logger.info(f"Answering questionnaire question {question_index + 1}")
        logger.debug(f"Question ID: {question_id}, Answer ID: {answer_id}")

        payload = self._build_questionnaire_payload(question_id, answer_id, question_index)

        response = self.session.post(
            config.ENDPOINTS["evaluate_questionnaire"],
            data=payload,
            referer=self._build_referer(),
        )

        if response.status_code != 200:
            raise WorkflowError(
                f"Questionnaire answer failed: {response.status_code}"
            )

        # Update widget header if present in response
        new_header = self._extract_widget_header(response.text)
        if new_header:
            self.session.widget_header = new_header

        try:
            result = response.json()
            self.current_question_index = question_index + 1
            return result
        except json.JSONDecodeError:
            return {"raw": response.text}

    def advance_decision_tree(self) -> Dict[str, Any]:
        """
        Step 2a (optional): Advance the decision tree.

        Some questionnaire flows require explicit tree advancement.

        Returns:
            Response data
        """
        logger.info("Advancing decision tree...")

        payload = {
            "__widgetheader": self.session.widget_header or "",
        }

        response = self.session.post(
            config.ENDPOINTS["decision_tree_next"],
            data=payload,
            referer=self._build_referer(),
        )

        if response.status_code != 200:
            logger.warning(f"Decision tree advance returned: {response.status_code}")

        try:
            return response.json()
        except json.JSONDecodeError:
            return {"raw": response.text}

    def validate_location(self) -> bool:
        """
        Step 3: Validate patient location.

        This is required before slots can be retrieved.

        Returns:
            True if location validation passed
        """
        logger.info("Validating patient location...")

        payload = {
            "__widgetheader": self.session.widget_header or "",
            "workflow.Type": "12",
            "workflow.IsAnonymous": "true",
        }

        response = self.session.post(
            config.ENDPOINTS["evaluate_location"],
            data=payload,
            referer=self._build_referer(),
        )

        if response.status_code != 200:
            raise WorkflowError(f"Location validation failed: {response.status_code}")

        # Update widget header if present
        new_header = self._extract_widget_header(response.text)
        if new_header:
            self.session.widget_header = new_header

        logger.info("Location validation completed")
        return True

    def get_slots(self, start_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Step 4: Retrieve available appointment slots.

        Args:
            start_date: Date to start searching from (defaults to today)

        Returns:
            Dict containing slot data
        """
        if start_date is None:
            start_date = date.today()

        epic_date = epic_date_to_int(start_date)
        logger.info(f"Getting slots starting from {start_date} (Epic date: {epic_date})")

        # Build the large payload required for GetSlots
        payload = self._build_get_slots_payload(epic_date)

        response = self.session.post(
            config.ENDPOINTS["get_slots"],
            data=payload,
            referer=self._build_referer(),
        )

        if response.status_code != 200:
            raise WorkflowError(f"GetSlots failed: {response.status_code}")

        try:
            result = response.json()
            logger.info(f"GetSlots response keys: {list(result.keys())}")
            return result
        except json.JSONDecodeError:
            logger.error("Could not parse GetSlots response as JSON")
            return {"raw": response.text, "error": "JSON parse failed"}

    def _build_get_slots_payload(self, epic_date: int) -> Dict[str, str]:
        """
        Build the payload for GetSlots request.

        This is a large payload reflecting full session state.
        """
        payload = {
            "__widgetheader": self.session.widget_header or "",
            "workflow.Type": "12",
            "workflow.IsAnonymous": "true",
            "workflow.IsAuthenticatedWidget": "false",
            "workflow.SchedulingControllerParams.dept": config.DEPARTMENT_IDS,
            "workflow.SchedulingControllerParams.vt": config.VISIT_TYPE,
            "startDte": str(epic_date),
            "appointmentBuilder.Appointments[0].VisitTypeId": "",  # Will be filled by tokens
        }

        # Add any LQF IDs from questionnaire answers
        for i, q in enumerate(self.questionnaire_questions):
            if "Id" in q:
                payload[f"appointmentBuilder.Appointments[0].LqfIds[{i}]"] = q["Id"]
            if "AnswerId" in q:
                payload[f"appointmentBuilder.Appointments[0].PatientAnswerIds[{i}]"] = q["AnswerId"]

        return payload


def run_full_workflow(session: EpicSession, start_date: Optional[date] = None) -> Dict[str, Any]:
    """
    Run the complete workflow to get appointment slots.

    This is a convenience function that executes all steps.
    Note: This may need adjustment based on actual questionnaire tokens
    discovered during testing.

    Args:
        session: Active EpicSession
        start_date: Date to start slot search from

    Returns:
        Slot data from GetSlots endpoint
    """
    workflow = EpicWorkflow(session)

    # Step 0: Load embedded page to establish context
    html = workflow.load_embedded_page()

    # Step 1: Initialize workflow
    try:
        workflow.initialize_workflow()
    except WorkflowError as e:
        logger.warning(f"Workflow init issue (continuing): {e}")

    # Steps 2-2a: Questionnaire and decision tree
    # NOTE: The actual question/answer IDs need to be extracted dynamically
    # from the workflow init response. This is a placeholder that will need
    # to be adjusted based on actual API responses.

    # For now, we attempt to skip directly to GetSlots and see what happens
    # The API will tell us if questionnaire is required

    # Step 3: Location validation
    try:
        workflow.validate_location()
    except WorkflowError as e:
        logger.warning(f"Location validation issue (continuing): {e}")

    # Step 4: Get slots
    return workflow.get_slots(start_date)
