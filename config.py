"""
Configuration constants for UCSF Dental School appointment checker.
Based on Epic MyChart Open Scheduling reverse engineering.
"""

# Base URL for Epic MyChart
BASE_URL = "https://ucsfmychart.ucsfmedicalcenter.org/UCSFMyChart"

# API Endpoints
ENDPOINTS = {
    "init_workflow": "/Scheduling/Embedded/ReloadSchedulingWorkflowData",
    "evaluate_questionnaire": "/Scheduling/Embedded/EvaluateQuestionnaireAnswers",
    "decision_tree_next": "/DecisionTrees/EmbeddedDecisionTree/NextStep",
    "evaluate_location": "/Scheduling/Embedded/EvaluatePatientLocationRule",
    "get_slots": "/Scheduling/Embedded/GetSlots",
}

# Scheduling parameters from network capture
DEPARTMENT_IDS = "3202010,3202011"
VISIT_TYPE = "1148"
REASON_FOR_VISIT = "newprov_1148"

# Required headers
API_KEY = "uiYEvdRgacwG814"

# User agent to mimic real browser
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Epic date system: days since December 31, 1840
EPIC_DATE_EPOCH_YEAR = 1840
EPIC_DATE_EPOCH_MONTH = 12
EPIC_DATE_EPOCH_DAY = 31

# Paths
SLOT_HISTORY_FILE = "data/slot_history.json"

# Timing
REQUEST_DELAY_MIN = 1.0  # seconds between requests
REQUEST_DELAY_MAX = 3.0
REQUEST_TIMEOUT = 30  # seconds

# Widget configuration
WIDGET_ID = "MyChartIframe0"
