"""Unit tests for ItineraryParser."""

from __future__ import annotations

import base64
from typing import Any

from src.itinerary_parser import Itinerary, ItineraryParser


def _make_message(
    msg_id: str = "m1",
    from_addr: str = "booking@airline.com",
    subject: str = "Flight Confirmation",
    body_text: str = "Your PNR: ABC123 Flight AA 1234 JFK to LAX on 2026-05-01",
) -> dict[str, Any]:
    return {
        "id": msg_id,
        "threadId": "t1",
        "payload": {
            "headers": [
                {"name": "From", "value": from_addr},
                {"name": "To", "value": "jpastore79@gmail.com"},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Wed, 01 Apr 2026 10:00:00 -0400"},
            ],
            "mimeType": "text/plain",
            "body": {"data": base64.urlsafe_b64encode(body_text.encode()).decode()},
        },
    }


class TestFlightDetection:
    def test_airline_sender_classified_as_flight(self) -> None:
        parser = ItineraryParser()
        msg = _make_message(from_addr="noreply@delta.com", subject="Your Flight Booking")
        itinerary = parser.parse_messages([msg])
        assert len(itinerary.trips) == 1
        assert itinerary.trips[0].type == "flight"

    def test_airways_sender_classified_as_flight(self) -> None:
        parser = ItineraryParser()
        msg = _make_message(from_addr="confirm@philippineairways.com", subject="E-Ticket")
        itinerary = parser.parse_messages([msg])
        assert len(itinerary.trips) == 1
        assert itinerary.trips[0].type == "flight"

    def test_american_airlines_classified_as_flight(self) -> None:
        parser = ItineraryParser()
        msg = _make_message(from_addr="noreply@aa.com", subject="American Airlines Confirmation")
        itinerary = parser.parse_messages([msg])
        assert len(itinerary.trips) == 1
        assert itinerary.trips[0].type == "flight"


class TestHotelDetection:
    def test_hotel_sender_classified_as_hotel(self) -> None:
        parser = ItineraryParser()
        msg = _make_message(
            from_addr="reservations@marriott.com",
            subject="Hotel Reservation Confirmed",
            body_text="Check-in: 2026-05-01 Check-out: 2026-05-04 Booking #: HTL-9999",
        )
        itinerary = parser.parse_messages([msg])
        assert len(itinerary.trips) == 1
        assert itinerary.trips[0].type == "hotel"

    def test_airbnb_sender_classified_as_hotel(self) -> None:
        parser = ItineraryParser()
        msg = _make_message(
            from_addr="automated@airbnb.com",
            subject="Your reservation is confirmed",
            body_text="Check-in: 2026-06-10 Check-out: 2026-06-15 Confirmation #: AIRXYZ",
        )
        itinerary = parser.parse_messages([msg])
        assert len(itinerary.trips) == 1
        assert itinerary.trips[0].type == "hotel"

    def test_agoda_sender_classified_as_hotel(self) -> None:
        parser = ItineraryParser()
        msg = _make_message(
            from_addr="noreply@agoda.com",
            subject="Booking Confirmation",
            body_text="Booking #: AGD-5678 2026-07-01",
        )
        itinerary = parser.parse_messages([msg])
        assert len(itinerary.trips) == 1
        assert itinerary.trips[0].type == "hotel"


class TestCarRentalDetection:
    def test_hertz_sender_classified_as_car_rental(self) -> None:
        parser = ItineraryParser()
        msg = _make_message(
            from_addr="rentals@hertz.com",
            subject="Car Rental Confirmation",
            body_text="Confirmation #: HERTZ-1234 Pickup: 2026-05-01",
        )
        itinerary = parser.parse_messages([msg])
        assert len(itinerary.trips) == 1
        assert itinerary.trips[0].type == "car_rental"

    def test_enterprise_sender_classified_as_car_rental(self) -> None:
        parser = ItineraryParser()
        msg = _make_message(
            from_addr="confirm@enterprise.com",
            subject="Rental Booking",
            body_text="Reservation #: ENT-5555 2026-05-02",
        )
        itinerary = parser.parse_messages([msg])
        assert len(itinerary.trips) == 1
        assert itinerary.trips[0].type == "car_rental"


class TestUnknownType:
    def test_unrecognized_sender_skipped(self) -> None:
        parser = ItineraryParser()
        msg = _make_message(
            from_addr="newsletter@randomshop.com",
            subject="Weekly deals",
            body_text="Check out our sale this week!",
        )
        itinerary = parser.parse_messages([msg])
        assert len(itinerary.trips) == 0

    def test_personal_email_skipped(self) -> None:
        parser = ItineraryParser()
        msg = _make_message(
            from_addr="friend@gmail.com",
            subject="Hey there",
            body_text="How are you doing?",
        )
        itinerary = parser.parse_messages([msg])
        assert len(itinerary.trips) == 0


class TestConfirmationExtraction:
    def test_pnr_format_extracted(self) -> None:
        parser = ItineraryParser()
        msg = _make_message(
            from_addr="confirm@united.com",
            subject="Flight Confirmation",
            body_text="Your PNR: XYZ789 Flight UA 100 ORD to SFO on 2026-05-10",
        )
        itinerary = parser.parse_messages([msg])
        assert itinerary.trips[0].confirmation_number == "XYZ789"

    def test_booking_number_format_extracted(self) -> None:
        parser = ItineraryParser()
        msg = _make_message(
            from_addr="noreply@agoda.com",
            subject="Booking Confirmed",
            body_text="Booking #: BK-99887 Check-in: 2026-06-01",
        )
        itinerary = parser.parse_messages([msg])
        assert itinerary.trips[0].confirmation_number == "BK-99887"

    def test_itinerary_number_format_extracted(self) -> None:
        parser = ItineraryParser()
        msg = _make_message(
            from_addr="tickets@expedia.com",
            subject="Your Itinerary",
            body_text="Itinerary #: 112233445 Departs 2026-07-04",
        )
        itinerary = parser.parse_messages([msg])
        assert itinerary.trips[0].confirmation_number == "112233445"

    def test_no_confirmation_number_returns_none(self) -> None:
        parser = ItineraryParser()
        msg = _make_message(
            from_addr="info@southwest.com",
            subject="Your Trip Details",
            body_text="Flight WN 500 departs 2026-05-15 from DAL to HOU",
        )
        itinerary = parser.parse_messages([msg])
        assert itinerary.trips[0].confirmation_number is None


class TestDeduplication:
    def test_duplicate_confirmation_numbers_deduplicated(self) -> None:
        parser = ItineraryParser()
        msg1 = _make_message(
            msg_id="m1",
            from_addr="confirm@delta.com",
            subject="Flight Confirmation",
            body_text="PNR: ABC123 Flight DL 200 JFK to LAX on 2026-05-01",
        )
        msg2 = _make_message(
            msg_id="m2",
            from_addr="confirm@delta.com",
            subject="Flight Reminder",
            body_text="PNR: ABC123 Flight DL 200 departs tomorrow 2026-05-01",
        )
        itinerary = parser.parse_messages([msg1, msg2])
        assert len(itinerary.trips) == 1
        assert itinerary.trips[0].source_message_id == "m1"

    def test_different_confirmation_numbers_both_kept(self) -> None:
        parser = ItineraryParser()
        msg1 = _make_message(
            msg_id="m1",
            from_addr="confirm@delta.com",
            subject="Flight 1",
            body_text="PNR: AAA111 Flight DL 100 on 2026-05-01",
        )
        msg2 = _make_message(
            msg_id="m2",
            from_addr="confirm@delta.com",
            subject="Flight 2",
            body_text="PNR: BBB222 Flight DL 200 on 2026-06-01",
        )
        itinerary = parser.parse_messages([msg1, msg2])
        assert len(itinerary.trips) == 2

    def test_no_confirmation_number_always_kept(self) -> None:
        parser = ItineraryParser()
        msg1 = _make_message(
            msg_id="m1",
            from_addr="info@jetblue.com",
            subject="Your Flight",
            body_text="Flight B6 100 departs 2026-05-01",
        )
        msg2 = _make_message(
            msg_id="m2",
            from_addr="info@jetblue.com",
            subject="Your Return Flight",
            body_text="Flight B6 200 departs 2026-05-10",
        )
        itinerary = parser.parse_messages([msg1, msg2])
        assert len(itinerary.trips) == 2


class TestEmptyInput:
    def test_empty_messages_list_returns_empty_itinerary(self) -> None:
        parser = ItineraryParser()
        itinerary = parser.parse_messages([])
        assert isinstance(itinerary, Itinerary)
        assert itinerary.trips == []

    def test_all_unknown_senders_returns_empty_itinerary(self) -> None:
        parser = ItineraryParser()
        messages = [
            _make_message(msg_id=f"m{i}", from_addr="spam@random.com", subject="Promo")
            for i in range(3)
        ]
        itinerary = parser.parse_messages(messages)
        assert itinerary.trips == []


class TestGracefulDegradation:
    def test_message_with_missing_body_still_parsed(self) -> None:
        parser = ItineraryParser()
        msg: dict[str, Any] = {
            "id": "m1",
            "threadId": "t1",
            "payload": {
                "headers": [
                    {"name": "From", "value": "confirm@hertz.com"},
                    {"name": "Subject", "value": "Car Rental Confirmation"},
                ],
                "body": {},
            },
        }
        itinerary = parser.parse_messages([msg])
        assert len(itinerary.trips) == 1
        assert itinerary.trips[0].type == "car_rental"

    def test_message_with_no_payload_gracefully_skipped(self) -> None:
        parser = ItineraryParser()
        msg: dict[str, Any] = {"id": "m1", "threadId": "t1"}
        itinerary = parser.parse_messages([msg])
        assert itinerary.trips == []
