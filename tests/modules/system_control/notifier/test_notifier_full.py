from __future__ import annotations

import asyncio
from datetime import datetime, time
import logging
from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx

from modules.system_control.notifier import config_loader, xNotifierService
from modules.system_control.notifier.api import router as notifier_router
from modules.system_control.notifier.services import senders
from modules.system_control.notifier.services.command_router import CommandRouter
from modules.system_control.notifier.services.telegram_bot import (
    QuietHours,
    TelegramBot,
    build_telegram_bot,
)


def test_config_loader_safe_env_parsing_and_clean_defaults(monkeypatch, caplog) -> None:
    monkeypatch.setenv("NOTIFIER_ALLOWED_USER_IDS", "101, not-an-id, 202")
    monkeypatch.setenv("NOTIFIER_ALLOW_PUBLIC", "true")
    monkeypatch.setenv("NOTIFIER_HOST", "127.0.0.1")

    caplog.set_level(logging.WARNING, logger="notifier.config")
    cfg = config_loader.load_config(None)

    assert "whatsapp_web" not in cfg
    assert cfg["server"]["host"] == "127.0.0.1"
    assert cfg["telegram"]["allowed_user_ids"] == [101, 202]
    assert cfg["telegram"]["allow_public"] is True
    assert any("invalid user id" in rec.message for rec in caplog.records)


def test_command_router_executes_commands_and_captures_single_snap() -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/health":
            return httpx.Response(200, json={"ok": True, "camera": {"ok": True}})
        if request.url.path == "/vlm/track":
            return httpx.Response(200, json={"ok": True})
        if request.url.path == "/camera/snap":
            return httpx.Response(
                200,
                content=b"\xff\xd8\xffJPEG",
                headers={"content-type": "image/jpeg"},
            )
        return httpx.Response(404)

    async def _run() -> None:
        transport = httpx.MockTransport(handler)
        router = CommandRouter("http://gateway.local", timeout=2.0)

        async with httpx.AsyncClient(transport=transport) as client:
            status_res = await router.handle(client, "/status", user_id=7, chat_id="12")
            assert status_res is not None
            assert "Durum ok" in (status_res.text or "")

            pt_res = await router.handle(client, "/pt 15 -10", user_id=7, chat_id="12")
            assert pt_res is not None and pt_res.text == "Pan/tilt ok"

            snap_res = await router.handle(client, "/snap", user_id=7, chat_id="12")
            assert snap_res is not None
            assert snap_res.photo == b"\xff\xd8\xffJPEG"
            assert snap_res.photo_caption == "📸 Snapshot"

    asyncio.run(_run())
    assert calls.count(("GET", "/camera/snap")) == 1


def test_telegram_bot_default_deny_quiet_hours_and_dynamic_help(monkeypatch) -> None:
    sent_texts: list[tuple[str, str]] = []
    router = CommandRouter("http://gateway.local", timeout=2.0)

    # 1) Default-deny when allowed_user_ids is empty and allow_public=False
    bot_denied = build_telegram_bot(
        {
            "telegram": {"bot_token": "tok", "chat_id": "10", "allowed_user_ids": [], "allow_public": False},
            "quiet_hours": {"enabled": False},
            "gateway": {"base_url": "http://gateway.local"},
        }
    )
    assert bot_denied is not None

    async def _rec_denied(text: str, *, chat_id: str | None = None) -> bool:
        sent_texts.append((str(chat_id), text))
        return True

    async def _run() -> None:
        monkeypatch.setattr(bot_denied, "send", _rec_denied)
        await bot_denied._handle_update({"message": {"from": {"id": 999}, "chat": {"id": 10}, "text": "/ping"}})
        assert sent_texts == []

        # 2) Explicit allow_public=True permits incoming command & /help uses CommandRouter
        bot_public = TelegramBot(
            "tok",
            "10",
            allowed_user_ids=[],
            allow_public=True,
            quiet_hours=QuietHours.from_config({"enabled": False, "start": "bad", "end": "08:00"}),
            command_router=router,
        )
        monkeypatch.setattr(bot_public, "send", _rec_denied)

        await bot_public._handle_update({"message": {"from": {"id": 999}, "chat": {"id": 10}, "text": "/help"}})
        assert len(sent_texts) == 1
        assert "/status" in sent_texts[0][1]
        assert "/snap" in sent_texts[0][1]

        # 3) Quiet hours midnight wrap + silent ignore (never send "Quiet hours are active.")
        qh = QuietHours.from_config({"enabled": True, "start": "23:00", "end": "08:00"})
        assert qh.is_quiet_now(datetime(2026, 11, 16, 23, 30)) is True
        assert qh.is_quiet_now(datetime(2026, 11, 16, 7, 59)) is True
        assert qh.is_quiet_now(datetime(2026, 11, 16, 12, 0)) is False

        bot_quiet = TelegramBot(
            "tok",
            "10",
            allowed_user_ids=[42],
            quiet_hours=QuietHours(True, time(0, 0), time(23, 59)),
            command_router=router,
        )
        monkeypatch.setattr(bot_quiet, "send", _rec_denied)
        sent_texts.clear()
        await bot_quiet._handle_update({"message": {"from": {"id": 42}, "chat": {"id": 10}, "text": "/ping"}})
        assert sent_texts == []

    asyncio.run(_run())


def test_senders_reuses_client_and_redacts_token_warning(monkeypatch, caplog) -> None:
    def fail_transport(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"boom {request.url}", request=request)

    shared = httpx.Client(transport=httpx.MockTransport(fail_transport))
    senders.close_senders()
    monkeypatch.setattr(senders, "_SYNC_CLIENT", shared)
    caplog.set_level(logging.WARNING, logger="notifier.senders")

    ok = senders.send_telegram("SECRET_TG_TOKEN", "10", "hello")
    assert ok is False
    assert any("***" in rec.message and "SECRET_TG_TOKEN" not in rec.message for rec in caplog.records)
    senders.close_senders()
    assert shared.is_closed


def test_notifier_lifespan_always_stops_bot_and_closes_senders(monkeypatch) -> None:
    events: list[str] = []

    class FakeBot:
        async def start(self) -> None:
            events.append("start")

        async def stop(self) -> None:
            events.append("stop")

    monkeypatch.setattr(
        xNotifierService,
        "load_config",
        lambda _p=None: {
            "server": {"host": "127.0.0.1", "port": 8096},
            "telegram": {"polling": {"enabled": False}},
        },
    )
    monkeypatch.setattr(xNotifierService, "build_telegram_bot", lambda _cfg: FakeBot())
    monkeypatch.setattr(xNotifierService, "close_senders", lambda: events.append("close_senders"))

    app = xNotifierService.create_app()
    with TestClient(app) as client:
        assert client.get("/notify/healthz").status_code == 200

    assert events == ["stop", "close_senders"]


def test_notifier_discord_quiet_hours_and_send_priority_debounce(monkeypatch) -> None:
    delivered: list[tuple[str, str]] = []

    async def _fake_tg(cfg, bot, text, *, chat_id=None) -> bool:
        delivered.append(("telegram", text))
        return True

    async def _fake_dc(cfg, text) -> bool:
        delivered.append(("discord", text))
        return True

    monkeypatch.setattr(notifier_router, "_dispatch_telegram", _fake_tg)
    monkeypatch.setattr(notifier_router, "_dispatch_discord", _fake_dc)

    cfg = {
        "telegram": {"bot_token": "tok", "chat_id": "10"},
        "discord": {"webhook": "https://discord.example/hook"},
        "quiet_hours": {"enabled": True, "start": "00:00", "end": "23:59"},
        "send": {"cooldown_sec": 30.0},
    }
    app = FastAPI()
    app.include_router(notifier_router.get_router(cfg, bot=None))
    client = TestClient(app)

    # Discord respects quiet hours
    dc_quiet = client.post("/notify/discord", json={"text": "ping"})
    assert dc_quiet.status_code == 200
    assert dc_quiet.json() == {"ok": False, "reason": "quiet_hours"}

    # Normal priority respects quiet hours
    normal_quiet = client.post("/notify/send", json={"text": "normal alert"})
    assert normal_quiet.status_code == 200
    assert normal_quiet.json()["reason"] == "quiet_hours"

    # Critical bypasses quiet hours and fans out to both telegram & discord
    crit = client.post(
        "/notify/send",
        json={"text": "cpu overheat", "priority": "critical", "title": "Thermal"},
    )
    assert crit.status_code == 200
    crit_body = crit.json()
    assert crit_body["ok"] is True
    assert crit_body["results"] == {"telegram": True, "discord": True}
    assert ("telegram", "[Thermal] cpu overheat") in delivered
    assert ("discord", "[Thermal] cpu overheat") in delivered

    # Repeated identical message within cooldown_sec is debounced
    dup = client.post(
        "/notify/send",
        json={"text": "cpu overheat", "priority": "critical", "title": "Thermal"},
    )
    assert dup.status_code == 200
    assert dup.json()["reason"] == "debounced"

    # Invalid payload fails validation cleanly
    bad = client.post("/notify/send", json={"text": "x", "priority": "urgent"})
    assert bad.status_code == 422
