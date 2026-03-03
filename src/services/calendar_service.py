"""Google Calendar integration service."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from loguru import logger

from config.settings import settings


class GoogleCalendarService:
    """Manages Google Calendar API interactions for slot availability and event creation."""

    def __init__(self) -> None:
        self._service = None

    def _get_service(self):
        """Lazy-load the Google Calendar API service."""
        if self._service is not None:
            return self._service

        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build

            creds = Credentials.from_service_account_file(
                settings.google_calendar_credentials_path,
                scopes=["https://www.googleapis.com/auth/calendar"],
            )
            self._service = build("calendar", "v3", credentials=creds)
            return self._service
        except Exception as e:
            logger.warning(f"Google Calendar not configured: {e}")
            return None

    async def get_free_slots(
        self,
        calendar_id: str,
        date: datetime,
        slot_duration_min: int = 60,
        work_start_hour: int = 9,
        work_end_hour: int = 21,
    ) -> list[datetime]:
        """Get available time slots for a given date.

        Returns list of datetime objects representing available slot start times.
        Falls back to generating slots without calendar if API is unavailable.
        """
        import asyncio
        from datetime import timedelta

        # Конвертируем date из UTC в московское время для генерации слотов
        MOSCOW_OFFSET = timedelta(hours=3)
        date_moscow = date + MOSCOW_OFFSET

        day_start_moscow = date_moscow.replace(hour=work_start_hour, minute=0, second=0, microsecond=0)
        day_end_moscow = date_moscow.replace(hour=work_end_hour, minute=0, second=0, microsecond=0)

        # Generate all possible slots в московском времени (9:00-21:00 МСК)
        all_slots = []
        current_moscow = day_start_moscow
        while current_moscow + timedelta(minutes=slot_duration_min) <= day_end_moscow:
            all_slots.append(current_moscow)
            current_moscow += timedelta(minutes=slot_duration_min)

        service = self._get_service()
        if service is None:
            # Fallback: return all slots (no calendar filtering)
            logger.info("Calendar not configured, returning all slots")
            return all_slots

        try:
            # Query busy times from Google Calendar (в UTC)
            day_start_utc = day_start_moscow - MOSCOW_OFFSET
            day_end_utc = day_end_moscow - MOSCOW_OFFSET

            body = {
                "timeMin": day_start_utc.isoformat() + "Z",
                "timeMax": day_end_utc.isoformat() + "Z",
                "items": [{"id": calendar_id}],
            }

            result = await asyncio.to_thread(
                service.freebusy().query(body=body).execute
            )

            busy_periods = result.get("calendars", {}).get(calendar_id, {}).get(
                "busy", []
            )

            # Filter out slots that overlap with busy periods
            free_slots = []
            for slot_start_moscow in all_slots:
                slot_end_moscow = slot_start_moscow + timedelta(minutes=slot_duration_min)
                # Конвертируем в UTC для сравнения с busy periods
                slot_start_utc = slot_start_moscow - MOSCOW_OFFSET
                slot_end_utc = slot_end_moscow - MOSCOW_OFFSET
                is_free = True
                for busy in busy_periods:
                    busy_start = datetime.fromisoformat(
                        busy["start"].replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                    busy_end = datetime.fromisoformat(
                        busy["end"].replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                    if slot_start_utc < busy_end and slot_end_utc > busy_start:
                        is_free = False
                        break
                if is_free:
                    free_slots.append(slot_start_moscow)

            return free_slots

        except Exception as e:
            logger.error(f"Google Calendar API error: {e}")
            return all_slots

    async def create_event(
        self,
        calendar_id: str,
        summary: str,
        start_time: datetime,
        duration_min: int,
        description: str = "",
    ) -> Optional[str]:
        """Create a calendar event. Returns event ID or None on failure."""
        import asyncio

        service = self._get_service()
        if service is None:
            logger.info("Calendar not configured, skipping event creation")
            return None

        end_time = start_time + timedelta(minutes=duration_min)
        event = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_time.isoformat(), "timeZone": settings.timezone},
            "end": {"dateTime": end_time.isoformat(), "timeZone": settings.timezone},
            "reminders": {"useDefault": False},
        }

        try:
            result = await asyncio.to_thread(
                service.events()
                .insert(calendarId=calendar_id, body=event)
                .execute
            )
            return result.get("id")
        except Exception as e:
            logger.error(f"Failed to create calendar event: {e}")
            return None

    async def delete_event(
        self, calendar_id: str, event_id: str
    ) -> bool:
        """Delete a calendar event. Returns True on success."""
        import asyncio

        service = self._get_service()
        if service is None:
            return False

        try:
            await asyncio.to_thread(
                service.events()
                .delete(calendarId=calendar_id, eventId=event_id)
                .execute
            )
            return True
        except Exception as e:
            logger.error(f"Failed to delete calendar event: {e}")
            return False
