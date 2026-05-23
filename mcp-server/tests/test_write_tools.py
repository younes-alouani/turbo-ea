"""Unit tests for the artifact-import write tools.

These mirror the patterns in ``test_server.py`` — fake the auth token, mock
the ``TurboEAClient`` HTTP shim, invoke the tool function directly, and
assert (a) the right path and JSON body were forwarded and (b) the JSON
response flows back through ``_fmt``.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from turbo_ea_mcp import server


@pytest.fixture
def fake_token(monkeypatch):
    """Pretend a user is logged in so tool auth checks pass."""
    monkeypatch.setattr(server, "_stdio_token", "test-token")
    yield "test-token"


def _patched_post(payload):
    mock = AsyncMock(return_value=payload)
    return patch.object(server.TurboEAClient, "post", mock), mock


def _patched_put(payload):
    mock = AsyncMock(return_value=payload)
    return patch.object(server.TurboEAClient, "put", mock), mock


def _patched_get(payload):
    mock = AsyncMock(return_value=payload)
    return patch.object(server.TurboEAClient, "get", mock), mock


def _parse(s: str) -> dict | list:
    return json.loads(s)


# ── create_cards_bulk ──────────────────────────────────────────────────────


class TestCreateCardsBulk:
    @pytest.mark.asyncio
    async def test_dry_run_default(self, fake_token):
        patcher, mock = _patched_post(
            {
                "results": [
                    {"row_index": 0, "status": "created", "id": "card-1"},
                ],
                "created": 1,
                "failed": 0,
                "dry_run": True,
            }
        )
        with patcher:
            out = await server.create_cards_bulk(
                cards=[{"row_index": 0, "type": "Application", "name": "Test App"}]
            )
        mock.assert_awaited_once()
        args, kwargs = mock.call_args
        assert args[0] == "/cards/bulk-create"
        assert kwargs["json"]["dry_run"] is True
        assert _parse(out)["dry_run"] is True

    @pytest.mark.asyncio
    async def test_commit(self, fake_token):
        patcher, mock = _patched_post(
            {"results": [], "created": 0, "failed": 0, "dry_run": False}
        )
        with patcher:
            await server.create_cards_bulk(
                cards=[{"row_index": 0, "type": "Application", "name": "X"}],
                dry_run=False,
            )
        _, kwargs = mock.call_args
        assert kwargs["json"]["dry_run"] is False
        assert kwargs["json"]["cards"][0]["name"] == "X"

    @pytest.mark.asyncio
    async def test_single_row(self, fake_token):
        patcher, mock = _patched_post({"results": [], "created": 0, "failed": 0})
        with patcher:
            await server.create_cards_bulk(
                cards=[
                    {
                        "row_index": 7,
                        "type": "Application",
                        "name": "Single",
                        "attributes": {"businessCriticality": "high"},
                    }
                ],
                dry_run=False,
            )
        _, kwargs = mock.call_args
        cards = kwargs["json"]["cards"]
        assert len(cards) == 1
        assert cards[0]["attributes"] == {"businessCriticality": "high"}

    @pytest.mark.asyncio
    async def test_backend_validation_error_surfaces(self, fake_token):
        # Backend reports per-row failure for unknown type — the tool just
        # passes the payload through.
        patcher, mock = _patched_post(
            {
                "results": [
                    {
                        "row_index": 0,
                        "status": "failed",
                        "error": "Unknown card type: App",
                    }
                ],
                "created": 0,
                "failed": 1,
                "dry_run": True,
            }
        )
        with patcher:
            out = await server.create_cards_bulk(
                cards=[{"row_index": 0, "type": "App", "name": "Bad"}]
            )
        data = _parse(out)
        assert data["failed"] == 1
        assert "Unknown card type" in data["results"][0]["error"]


# ── resolve_card_refs ──────────────────────────────────────────────────────


class TestResolveCardRefs:
    @pytest.mark.asyncio
    async def test_pass_through(self, fake_token):
        patcher, mock = _patched_post(
            {
                "results": [
                    {
                        "row": 0,
                        "column": "parent",
                        "status": "resolved",
                        "id": "card-9",
                    }
                ]
            }
        )
        with patcher:
            out = await server.resolve_card_refs(
                refs=[
                    {
                        "row": 0,
                        "column": "parent",
                        "type": "BusinessCapability",
                        "ref": "Sales / CRM",
                    }
                ]
            )
        mock.assert_awaited_once()
        args, kwargs = mock.call_args
        assert args[0] == "/cards/resolve-refs"
        assert kwargs["json"]["refs"][0]["ref"] == "Sales / CRM"
        assert _parse(out)["results"][0]["id"] == "card-9"


# ── upsert_relations_bulk ──────────────────────────────────────────────────


class TestUpsertRelationsBulk:
    @pytest.mark.asyncio
    async def test_upsert_dry_run(self, fake_token):
        patcher, mock = _patched_post(
            {
                "results": [{"row_index": 0, "status": "upserted", "relation_id": "r1"}],
                "upserted": 1,
                "deleted": 0,
                "failed": 0,
                "dry_run": True,
            }
        )
        with patcher:
            out = await server.upsert_relations_bulk(
                operations=[
                    {
                        "row_index": 0,
                        "type": "uses",
                        "source": {"id": "src-uuid"},
                        "target": {"id": "tgt-uuid"},
                    }
                ]
            )
        _, kwargs = mock.call_args
        assert kwargs["json"]["dry_run"] is True
        assert _parse(out)["upserted"] == 1

    @pytest.mark.asyncio
    async def test_delete(self, fake_token):
        patcher, mock = _patched_post(
            {
                "results": [{"row_index": 0, "status": "deleted"}],
                "upserted": 0,
                "deleted": 1,
                "failed": 0,
                "dry_run": False,
            }
        )
        with patcher:
            await server.upsert_relations_bulk(
                operations=[
                    {
                        "row_index": 0,
                        "action": "delete",
                        "type": "uses",
                        "source": {"id": "s"},
                        "target": {"id": "t"},
                    }
                ],
                dry_run=False,
            )
        _, kwargs = mock.call_args
        assert kwargs["json"]["operations"][0]["action"] == "delete"

    @pytest.mark.asyncio
    async def test_type_mismatch_surfaces(self, fake_token):
        # Backend rejects per-row when source.type doesn't match the
        # relation type's expected source.
        patcher, mock = _patched_post(
            {
                "results": [
                    {
                        "row_index": 0,
                        "status": "failed",
                        "error": "Source type 'X' does not match relation type's expected source 'Application'",
                    }
                ],
                "upserted": 0,
                "deleted": 0,
                "failed": 1,
                "dry_run": True,
            }
        )
        with patcher:
            out = await server.upsert_relations_bulk(
                operations=[
                    {
                        "row_index": 0,
                        "type": "uses",
                        "source": {"type": "X", "name": "Bad", "parent_path": []},
                        "target": {"id": "t"},
                    }
                ]
            )
        assert "does not match" in _parse(out)["results"][0]["error"]


# ── create_diagram ─────────────────────────────────────────────────────────


class TestCreateDiagram:
    @pytest.mark.asyncio
    async def test_dry_run_short_circuits(self, fake_token):
        # Dry-run never calls the backend.
        patcher, mock = _patched_post({"id": "should-not-be-called"})
        xml = '<mxGraphModel><object cardId="11111111-2222-3333-4444-555555555555"/></mxGraphModel>'
        with patcher:
            out = await server.create_diagram(name="My Diag", drawio_xml=xml)
        mock.assert_not_called()
        data = _parse(out)
        assert data["dry_run"] is True
        assert data["would_create"]["extracted_card_refs_from_xml"] == [
            "11111111-2222-3333-4444-555555555555"
        ]

    @pytest.mark.asyncio
    async def test_commit_passes_xml(self, fake_token):
        patcher, mock = _patched_post({"id": "diag-1", "name": "My Diag"})
        xml = "<mxGraphModel/>"
        with patcher:
            await server.create_diagram(
                name="My Diag",
                drawio_xml=xml,
                description="…",
                linked_card_ids=["c1"],
                dry_run=False,
            )
        args, kwargs = mock.call_args
        assert args[0] == "/diagrams"
        assert kwargs["json"]["data"]["xml"] == xml
        assert kwargs["json"]["card_ids"] == ["c1"]
        assert kwargs["json"]["type"] == "free_draw"


# ── import_bpmn ────────────────────────────────────────────────────────────


class TestImportBpmn:
    @pytest.mark.asyncio
    async def test_find_existing_then_save_dry_run(self, fake_token, monkeypatch):
        get_payloads = iter(
            [
                {
                    "items": [
                        {"id": "bp-1", "name": "Order to Cash", "parent_id": None}
                    ],
                    "total": 1,
                }
            ]
        )
        get_mock = AsyncMock(side_effect=lambda *a, **kw: next(get_payloads))
        put_mock = AsyncMock(
            return_value={"version": 2, "element_count": 7, "dry_run": True}
        )
        post_mock = AsyncMock()  # must not be called (existing card)
        with (
            patch.object(server.TurboEAClient, "get", get_mock),
            patch.object(server.TurboEAClient, "put", put_mock),
            patch.object(server.TurboEAClient, "post", post_mock),
        ):
            out = await server.import_bpmn(
                business_process_name="Order to Cash",
                bpmn_xml="<bpmn:definitions/>",
            )
        post_mock.assert_not_called()
        put_args, put_kwargs = put_mock.call_args
        assert put_args[0] == "/bpm/processes/bp-1/diagram"
        assert put_kwargs["json"]["dry_run"] is True
        data = _parse(out)
        assert data["business_process_id"] == "bp-1"
        assert data["diagram_result"]["element_count"] == 7

    @pytest.mark.asyncio
    async def test_create_new_dry_run_skips_diagram_step(self, fake_token):
        # No matching BusinessProcess card — in dry-run, we preview the
        # would-be card create but skip step 3 (no card_id to attach to).
        get_mock = AsyncMock(return_value={"items": [], "total": 0})
        post_mock = AsyncMock(
            return_value={
                "results": [
                    {"row_index": 0, "status": "created", "id": "would-be-id"}
                ],
                "created": 1,
                "failed": 0,
                "dry_run": True,
            }
        )
        put_mock = AsyncMock()  # must not be called
        with (
            patch.object(server.TurboEAClient, "get", get_mock),
            patch.object(server.TurboEAClient, "post", post_mock),
            patch.object(server.TurboEAClient, "put", put_mock),
        ):
            out = await server.import_bpmn(
                business_process_name="Brand New Process",
                bpmn_xml="<bpmn:definitions/>",
            )
        put_mock.assert_not_called()
        data = _parse(out)
        assert data["dry_run"] is True
        assert data["would_create_business_process"] is True

    @pytest.mark.asyncio
    async def test_multi_match_refuses(self, fake_token):
        get_mock = AsyncMock(
            return_value={
                "items": [
                    {"id": "bp-a", "name": "Order to Cash", "parent_id": "p1"},
                    {"id": "bp-b", "name": "Order to Cash", "parent_id": "p2"},
                ],
                "total": 2,
            }
        )
        with patch.object(server.TurboEAClient, "get", get_mock):
            out = await server.import_bpmn(
                business_process_name="Order to Cash",
                bpmn_xml="<bpmn:definitions/>",
            )
        data = _parse(out)
        assert data["error"] == "ambiguous_business_process"
        assert len(data["candidates"]) == 2

    @pytest.mark.asyncio
    async def test_commit_create_then_save(self, fake_token):
        get_mock = AsyncMock(return_value={"items": [], "total": 0})
        post_mock = AsyncMock(
            return_value={
                "results": [
                    {"row_index": 0, "status": "created", "id": "new-bp-id"}
                ],
                "created": 1,
                "failed": 0,
                "dry_run": False,
            }
        )
        put_mock = AsyncMock(
            return_value={"version": 1, "element_count": 5, "dry_run": False}
        )
        with (
            patch.object(server.TurboEAClient, "get", get_mock),
            patch.object(server.TurboEAClient, "post", post_mock),
            patch.object(server.TurboEAClient, "put", put_mock),
        ):
            out = await server.import_bpmn(
                business_process_name="Brand New Process",
                bpmn_xml="<bpmn:definitions/>",
                dry_run=False,
            )
        # Both steps fired.
        post_mock.assert_awaited_once()
        put_mock.assert_awaited_once()
        put_args, _ = put_mock.call_args
        assert put_args[0] == "/bpm/processes/new-bp-id/diagram"
        data = _parse(out)
        assert data["business_process_id"] == "new-bp-id"
        assert data["business_process_created"] is True


# ── Unauthenticated paths ──────────────────────────────────────────────────


class TestUnauthenticatedWrites:
    def test_create_cards_bulk_requires_auth(self, monkeypatch):
        monkeypatch.setattr(server, "_stdio_token", None)
        out = asyncio.run(
            server.create_cards_bulk(
                cards=[{"row_index": 0, "type": "Application", "name": "X"}]
            )
        )
        assert "Not authenticated" in out

    def test_resolve_card_refs_requires_auth(self, monkeypatch):
        monkeypatch.setattr(server, "_stdio_token", None)
        out = asyncio.run(server.resolve_card_refs(refs=[]))
        assert "Not authenticated" in out

    def test_upsert_relations_bulk_requires_auth(self, monkeypatch):
        monkeypatch.setattr(server, "_stdio_token", None)
        out = asyncio.run(
            server.upsert_relations_bulk(
                operations=[
                    {
                        "row_index": 0,
                        "type": "uses",
                        "source": {"id": "s"},
                        "target": {"id": "t"},
                    }
                ]
            )
        )
        assert "Not authenticated" in out

    def test_create_diagram_requires_auth(self, monkeypatch):
        monkeypatch.setattr(server, "_stdio_token", None)
        out = asyncio.run(server.create_diagram(name="X", drawio_xml="<x/>"))
        assert "Not authenticated" in out

    def test_import_bpmn_requires_auth(self, monkeypatch):
        monkeypatch.setattr(server, "_stdio_token", None)
        out = asyncio.run(
            server.import_bpmn(
                business_process_name="X",
                bpmn_xml="<bpmn:definitions/>",
            )
        )
        assert "Not authenticated" in out
