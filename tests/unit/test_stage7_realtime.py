from __future__ import annotations
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from app.api.routes import scoring as scoring_routes
from app.schemas.scoring import DeliveryCreate
from app.services.realtime import MatchConnectionManager


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.messages: list[dict] = []


    async def accept(self) -> None:
        self.accepted = True


    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)


@pytest.mark.asyncio
async def test_two_clients_receive_same_match_broadcast() -> None:
    manager = MatchConnectionManager()
    match_id = uuid4()
    client_one = FakeWebSocket()
    client_two = FakeWebSocket()

    await manager.connect(match_id, client_one)
    await manager.connect(match_id, client_two)


    payload = {
        "event_type":
            "delivery_recorded",

        "match_id": str(match_id)
    }


    await manager.broadcast(match_id, payload)


    assert client_one.accepted is True
    assert client_two.accepted is True
    assert client_one.messages == [payload]
    assert client_two.messages == [payload]


@pytest.mark.asyncio
async def test_failed_scoring_transaction_produces_no_broadcast(monkeypatch: pytest.MonkeyPatch) -> None:
    match_id = uuid4()
    failed_record = AsyncMock(side_effect=RuntimeError("database rollback"))
    publish = AsyncMock()
    monkeypatch.setattr(
        scoring_routes,
        "record_delivery",
        failed_record,

    )


    monkeypatch.setattr(
        scoring_routes,
        (
            "publish_committed_"
            "match_state"
        ),

        publish,

    )


    with pytest.raises(RuntimeError, match="database rollback"):
        await (
            scoring_routes
            .record_delivery_endpoint(
                match_id=match_id,
                payload=DeliveryCreate(runs=1),
                session=object(),

            )
        )


    publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_successful_scoring_broadcasts_after_service_returns(
    monkeypatch:pytest.MonkeyPatch) -> None:
    match_id = uuid4()
    order: list[str] = []
    scoring_state = object()


    async def committed_service(*args, **kwargs):
        order.append("service-returned")
        return scoring_state


    async def publish(*args, **kwargs):
        order.append("broadcast")

    
    monkeypatch.setattr(
        scoring_routes,
        "record_delivery",
        committed_service,

    )
    monkeypatch.setattr(
        scoring_routes,

        (
            "publish_committed_"
            "match_state"
        ),
        publish,

    )


    result = (
        await scoring_routes
        .record_delivery_endpoint(
            match_id=match_id,
            payload=DeliveryCreate(runs=1),
            session=object()
        )
    )

    assert result is scoring_state
    assert order == ["service-returned", "broadcast"]