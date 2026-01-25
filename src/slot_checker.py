"""
Slot parsing and comparison logic.
Tracks appointment availability over time and detects new openings.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, asdict

import config

logger = logging.getLogger(__name__)


@dataclass
class AppointmentSlot:
    """Represents a single appointment slot."""
    date: str  # ISO format date
    time: str  # Time string
    provider: Optional[str] = None
    department: Optional[str] = None
    department_id: Optional[str] = None
    slot_id: Optional[str] = None  # Unique identifier if available

    def __hash__(self):
        return hash((self.date, self.time, self.department_id))

    def __eq__(self, other):
        if not isinstance(other, AppointmentSlot):
            return False
        return (self.date, self.time, self.department_id) == (
            other.date, other.time, other.department_id
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppointmentSlot":
        return cls(**data)

    def display_str(self) -> str:
        """Human-readable representation."""
        parts = [f"{self.date} at {self.time}"]
        if self.provider:
            parts.append(f"with {self.provider}")
        if self.department:
            parts.append(f"at {self.department}")
        return " ".join(parts)


class SlotParser:
    """Parses appointment slots from Epic API responses."""

    @staticmethod
    def parse_slots(response_data: Dict[str, Any]) -> List[AppointmentSlot]:
        """
        Parse appointment slots from GetSlots response.

        The structure of Epic's response can vary, so we try multiple patterns.

        Args:
            response_data: JSON response from GetSlots endpoint

        Returns:
            List of AppointmentSlot objects
        """
        slots = []

        # Common patterns in Epic responses
        slot_containers = [
            response_data.get("Slots", []),
            response_data.get("AvailableSlots", []),
            response_data.get("slots", []),
            response_data.get("Days", []),
            response_data.get("AllDays", []),
        ]

        # Flatten nested structures
        for container in slot_containers:
            if not container:
                continue

            if isinstance(container, list):
                for item in container:
                    parsed = SlotParser._parse_slot_item(item)
                    if parsed:
                        slots.extend(parsed)

        # Also check for slots nested under providers/departments
        providers = response_data.get("Providers", []) or response_data.get("providers", [])
        for provider in providers:
            provider_name = provider.get("Name") or provider.get("DisplayName")
            provider_slots = provider.get("Slots", []) or provider.get("AvailableSlots", [])
            for slot_data in provider_slots:
                parsed = SlotParser._parse_single_slot(slot_data, provider=provider_name)
                if parsed:
                    slots.append(parsed)

        # Check departments structure
        departments = response_data.get("Departments", []) or response_data.get("departments", [])
        for dept in departments:
            dept_name = dept.get("Name") or dept.get("DisplayName")
            dept_id = dept.get("Id") or dept.get("DepartmentId")
            dept_slots = dept.get("Slots", []) or dept.get("AvailableSlots", [])
            for slot_data in dept_slots:
                parsed = SlotParser._parse_single_slot(
                    slot_data, department=dept_name, department_id=dept_id
                )
                if parsed:
                    slots.append(parsed)

        logger.info(f"Parsed {len(slots)} appointment slots")
        return slots

    @staticmethod
    def _parse_slot_item(item: Any) -> List[AppointmentSlot]:
        """Parse a single item which might contain one or more slots."""
        slots = []

        if isinstance(item, dict):
            # Check if this is a day container with slots
            day_date = item.get("Date") or item.get("date")
            day_slots = item.get("Slots", []) or item.get("slots", [])

            if day_date and day_slots:
                for slot in day_slots:
                    parsed = SlotParser._parse_single_slot(slot, date_override=day_date)
                    if parsed:
                        slots.append(parsed)
            else:
                # Try to parse as a single slot
                parsed = SlotParser._parse_single_slot(item)
                if parsed:
                    slots.append(parsed)

        return slots

    @staticmethod
    def _parse_single_slot(
        data: Dict[str, Any],
        date_override: Optional[str] = None,
        provider: Optional[str] = None,
        department: Optional[str] = None,
        department_id: Optional[str] = None,
    ) -> Optional[AppointmentSlot]:
        """Parse a single slot dictionary into an AppointmentSlot."""
        try:
            # Extract date
            slot_date = date_override
            if not slot_date:
                slot_date = (
                    data.get("Date") or
                    data.get("date") or
                    data.get("AppointmentDate") or
                    data.get("StartDate")
                )

            # Extract time
            slot_time = (
                data.get("Time") or
                data.get("time") or
                data.get("StartTime") or
                data.get("DisplayTime")
            )

            if not slot_date or not slot_time:
                return None

            # Normalize date format
            if isinstance(slot_date, int):
                # Epic integer date
                from src.workflow import int_to_epic_date
                slot_date = int_to_epic_date(slot_date).isoformat()

            return AppointmentSlot(
                date=str(slot_date),
                time=str(slot_time),
                provider=provider or data.get("ProviderName") or data.get("Provider"),
                department=department or data.get("DepartmentName") or data.get("Department"),
                department_id=department_id or data.get("DepartmentId") or data.get("DeptId"),
                slot_id=data.get("Id") or data.get("SlotId"),
            )
        except Exception as e:
            logger.warning(f"Failed to parse slot: {e}")
            return None


class SlotHistory:
    """Manages historical slot data for comparison."""

    def __init__(self, history_file: str = config.SLOT_HISTORY_FILE):
        self.history_file = Path(history_file)
        self.history_file.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Dict[str, Any]:
        """Load history from file."""
        if not self.history_file.exists():
            return {"last_check": None, "slots": [], "checks": []}

        try:
            with open(self.history_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Could not load history: {e}")
            return {"last_check": None, "slots": [], "checks": []}

    def save(self, data: Dict[str, Any]):
        """Save history to file."""
        with open(self.history_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def get_previous_slots(self) -> Set[AppointmentSlot]:
        """Get slots from previous check."""
        history = self.load()
        return {
            AppointmentSlot.from_dict(s)
            for s in history.get("slots", [])
        }

    def update(
        self,
        current_slots: List[AppointmentSlot],
        raw_response: Optional[Dict[str, Any]] = None
    ):
        """
        Update history with new slot data.

        Args:
            current_slots: List of currently available slots
            raw_response: Optional raw API response for debugging
        """
        history = self.load()

        check_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "slot_count": len(current_slots),
        }

        # Keep last 100 checks
        checks = history.get("checks", [])
        checks.append(check_record)
        checks = checks[-100:]

        history.update({
            "last_check": datetime.utcnow().isoformat(),
            "slots": [s.to_dict() for s in current_slots],
            "checks": checks,
        })

        # Optionally store raw response for debugging
        if raw_response:
            history["last_raw_response"] = raw_response

        self.save(history)
        logger.info(f"Updated history with {len(current_slots)} slots")


def compare_slots(
    current: List[AppointmentSlot],
    previous: Set[AppointmentSlot]
) -> Dict[str, List[AppointmentSlot]]:
    """
    Compare current slots against previous to find changes.

    Returns:
        Dict with 'new', 'removed', and 'unchanged' slot lists
    """
    current_set = set(current)

    new_slots = [s for s in current if s not in previous]
    removed_slots = [s for s in previous if s not in current_set]
    unchanged_slots = [s for s in current if s in previous]

    logger.info(
        f"Slot comparison: {len(new_slots)} new, "
        f"{len(removed_slots)} removed, {len(unchanged_slots)} unchanged"
    )

    return {
        "new": new_slots,
        "removed": removed_slots,
        "unchanged": unchanged_slots,
    }
