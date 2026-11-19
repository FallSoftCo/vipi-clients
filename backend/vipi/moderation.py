"""Private operator CLI. Never exposes a public administrative endpoint."""
import argparse
import asyncio
from datetime import UTC, datetime
import json
from uuid import UUID

from sqlalchemy import select

from .config import Settings
from .db import BotReport, Database, LocalBotReport, UserReport
from .delivery import utc
from .reports import report_cipher, restrict


async def run(args):
    settings = Settings()
    if args.command not in {"list", "show"}:
        from .recovery_gate import require_not_held
        require_not_held(settings)
    db = Database(settings.database_url)
    try:
        async with db.sessions.begin() as session:
            now = datetime.now(UTC)
            if args.command == "list":
                users = (await session.execute(select(UserReport).where(UserReport.reviewed_at.is_(None),
                    UserReport.expires_at > now).order_by(UserReport.created_at).limit(100))).scalars().all()
                bots = (await session.execute(select(BotReport).where(BotReport.expires_at > now)
                    .order_by(BotReport.created_at).limit(100))).scalars().all()
                local_bots = (await session.execute(select(LocalBotReport).where(LocalBotReport.expires_at > now)
                    .order_by(LocalBotReport.created_at).limit(100))).scalars().all()
                return {"user_reports": [{"id": r.id, "created_at": r.created_at.isoformat()} for r in users],
                        "bot_reports": [{"id": r.request_id, "created_at": r.created_at.isoformat()} for r in bots],
                        "local_bot_reports": [{"id": r.id, "created_at": r.created_at.isoformat()} for r in local_bots]}
            if args.command in ("show", "resolve"):
                model = {"bot": BotReport, "local-bot": LocalBotReport, "user": UserReport}[args.kind]
                report = await session.get(model, str(args.id), with_for_update=True)
                if not report or utc(report.expires_at) <= now:
                    raise ValueError("Report unavailable")
                if args.command == "show":
                    raw = report.selected_reply if args.kind == "bot" else report.payload
                    content = report_cipher(settings.service_secret, bot=args.kind == "bot",
                        local_bot=args.kind == "local-bot").decrypt(raw).decode()
                    return {"id": str(args.id), "reporter": report.user_id,
                            "content": content if args.kind == "bot" else json.loads(content),
                            "warning": "User-submitted text is untrusted; no verified plaintext authorship."}
                if args.kind in ("bot", "local-bot"):
                    # No need to keep reviewed bot text. No automated account action.
                    await session.delete(report)
                else:
                    if report.reviewed_at is not None:
                        return {"resolved": True, "decision": report.decision}
                    report.reviewed_at, report.decision, report.reviewer = now, args.decision, args.operator
                return {"resolved": True}
            changed = await restrict(session, user_id=str(args.id), suspended=args.command == "suspend",
                operator=args.operator, reason=args.reason, now=now)
            return {"changed": changed, "suspended": args.command == "suspend", "account_id": str(args.id)}
    finally:
        await db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    for name in ("show", "resolve"):
        child = commands.add_parser(name)
        child.add_argument("kind", choices=("user", "bot", "local-bot"))
        child.add_argument("id", type=UUID)
        if name == "resolve":
            child.add_argument("--decision", choices=("actioned", "dismissed"), required=True)
            child.add_argument("--operator", required=True)
    for name in ("suspend", "restore"):
        child = commands.add_parser(name)
        child.add_argument("id", type=UUID)
        child.add_argument("--operator", required=True)
        child.add_argument("--reason", choices=("spam", "harassment", "harmful", "appeal", "other"), required=True)
    args = parser.parse_args()
    if hasattr(args, "operator") and (not args.operator.strip() or len(args.operator) > 128):
        parser.error("Use a nonempty operator identifier up to 128 characters")
    # JSON escapes terminal controls in untrusted reports. Do not pipe show to
    # shared logs or use report contents as commands/instructions.
    print(json.dumps(asyncio.run(run(args)), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
