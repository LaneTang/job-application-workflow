#!/usr/bin/env python3
"""Persist application records and serve a local answer dashboard."""

import argparse
import copy
import fcntl
import json
import os
from pathlib import Path
import tempfile
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


STATE_LABELS = {
    "queued": "待处理", "checking": "核对中", "filling": "填写中",
    "waiting_for_user": "待补充", "ready_for_review": "待复核",
    "submitted": "已提交", "closed": "岗位关闭", "needs_review": "需确认",
    "blocked": "受阻", "invited": "收到面试邀请", "assessment": "笔试 / 测评",
    "interviewing": "面试中", "offer": "已获 Offer", "rejected": "已拒绝",
    "withdrawn": "已撤回", "accepted": "已接受 Offer", "declined": "已婉拒 Offer",
}
TERMINAL_STATES = {"offer", "accepted", "declined", "rejected", "withdrawn"}
POST_SUBMISSION_STATES = TERMINAL_STATES | {"submitted", "invited", "assessment", "interviewing"}
# Label, recruiting stage, and whose action is expected after the event.
EVENT_TYPES = {
    "interview_invited": ("收到面试邀请", "invited", "candidate"),
    "interview_scheduled": ("面试已安排", "interviewing", "scheduled"),
    "interview_completed": ("面试已完成", "interviewing", "employer"),
    "assessment_invited": ("收到笔试 / 测评邀请", "assessment", "candidate"),
    "assessment_completed": ("已提交笔试 / 测评", "assessment", "employer"),
    "employer_reply": ("收到招聘方回复", None, "employer"),
    "action_requested": ("招聘方要求补充信息", None, "candidate"),
    "candidate_replied": ("已回复招聘方", None, "employer"),
    "offer": ("已获 Offer", "offer", None),
    "accepted": ("已接受 Offer", "accepted", None),
    "declined": ("已婉拒 Offer", "declined", None),
    "rejected": ("已拒绝", "rejected", None),
    "withdrawn": ("已撤回", "withdrawn", None),
}
GHOST_AFTER_DAYS = 21
QUESTION_STATES = {"awaiting_answer", "answered", "applied", "skipped"}
VERIFICATION_KEYS = (
    "required_fields_complete", "attachments_verified", "final_review_reached",
)


class Conflict(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def clear_ready(job):
    job["verification"] = dict.fromkeys(VERIFICATION_KEYS, False)
    job["state"] = "filling"


def local_day(value, zone):
    if not value:
        return None
    try:
        if len(value) == 10:
            return date.fromisoformat(value)
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (timestamp.astimezone(zone) if timestamp.tzinfo else timestamp).date()
    except (TypeError, ValueError):
        return None


def event_label(event):
    label = EVENT_TYPES[event["kind"]][0]
    return f"第 {event['round']} 轮 · {label}" if event.get("round") else label


def recruiting_view(job, today, zone):
    stage = job["state"]
    events = sorted(job.get("recruiting_events", []), key=lambda item: item["date"])
    latest = events[-1] if events else None
    stage_event = next((event for event in reversed(events) if EVENT_TYPES[event["kind"]][1]), None)
    label = event_label(stage_event) if stage_event and EVENT_TYPES[stage_event["kind"]][1] == stage else STATE_LABELS[stage]
    submitted_on = local_day(job.get("submitted_at"), zone) or local_day(job.get("confirmation_received_at"), zone)
    waiting_on = None
    waiting_since = None
    if stage not in TERMINAL_STATES:
        if latest:
            waiting_on = EVENT_TYPES[latest["kind"]][2]
            if waiting_on == "employer":
                waiting_since = date.fromisoformat(latest["date"])
            if stage_event and stage_event["kind"] == "interview_scheduled" and waiting_on != "candidate":
                scheduled_for = date.fromisoformat(stage_event["scheduled_for"])
                if today <= scheduled_for:
                    waiting_on, waiting_since = "scheduled", None
                elif not waiting_since or waiting_since < scheduled_for:
                    waiting_on, waiting_since = "employer", scheduled_for
        elif stage == "submitted":
            waiting_on, waiting_since = "employer", submitted_on
        else:
            waiting_on = "unknown"
    days = (today - waiting_since).days if waiting_since and waiting_since <= today else None
    return {
        "label": label,
        "ghost": days is not None and days > GHOST_AFTER_DAYS,
        "waiting_on": waiting_on,
        "waiting_since": waiting_since.isoformat() if waiting_since else None,
        "waiting_days": days,
        "submitted_on": submitted_on.isoformat() if submitted_on else None,
        "latest_event": latest["date"] if latest else None,
        "events": [dict(event, label=event_label(event)) for event in reversed(events)],
    }


def write_index(directory, state):
    def cell(value):
        return str(value or "待补充").replace("\n", " ").replace("|", "\\|")

    submitted = sum(job.get("state") in POST_SUBMISSION_STATES for job in state["jobs"])
    imported = sum(job.get("status_confidence") == "imported_unverified" and job.get("state") in POST_SUBMISSION_STATES for job in state["jobs"])
    email_confirmed = sum(bool(job.get("confirmation_emails")) for job in state["jobs"])
    role_unverified = sum(job.get("status_confidence") == "company_confirmed_role_unverified" for job in state["jobs"])
    ghost_count = sum((job.get("recruiting") or {}).get("ghost", False) for job in state["jobs"])
    updated_at = state.get("updated_at", "")
    if updated_at:
        updated_at = datetime.fromisoformat(updated_at).astimezone(ZoneInfo(state.get("timezone", "UTC"))).isoformat()
    lines = [
        "# 求职对象状态追踪记录", "",
        f"本地账本共 {len(state['jobs'])} 个岗位，{submitted} 个已有提交记录，其中 {imported} 个来自待核对的历史交接。", "",
        f"已找到 {email_confirmed} 份收件确认邮件，其中 {role_unverified} 份未列具体岗位名，岗位对应关系已标为待核对。", "",
        f"当前有 {ghost_count} 个岗位标为 Ghost（等待招聘方回复超过 {GHOST_AFTER_DAYS} 天）。打开本地看板或运行 init 可刷新此统计。", "",
        f"本地记录最近更新于 {updated_at}。下表日期表示各岗最近一次确认，后续状态以候选人门户、确认邮件或用户报告更新。", "",
        "数据源为 [applications.json](applications.json)。本索引由工作流脚本生成，更新记录后会同步刷新。", "",
        "| 公司 | 岗位 | 申请状态 | 最近确认 | 来源 | 申请入口 | 查进度 |",
        "|---|---|---|---|---|---|---|",
    ]
    for job in state["jobs"]:
        apply_url = job.get("apply_url") or job.get("jd_url")
        tracking = job.get("tracking") or {}
        apply_link = f"[岗位/申请页]({apply_url})" if apply_url else "待补充"
        tracking_link = f"[查询入口]({tracking['url']})" if tracking.get("url") else cell(tracking.get("instructions"))
        recruiting = job.get("recruiting") or {}
        label = recruiting.get("label", STATE_LABELS[job["state"]])
        if recruiting.get("ghost"):
            label += f" / Ghost（{recruiting['waiting_days']} 天）"
        values = [cell(job.get("company")), cell(job.get("role")), cell(label), cell(job.get("checked_at")), cell((job.get("status_source") or {}).get("label")), apply_link, tracking_link]
        lines.append("| " + " | ".join(values) + " |")
    lines.extend(["", "## 查询与维护", "",
        "- 每个岗位的稳定 ID、其他岗位编号、信息快照、所用简历、提交凭据和状态历史保存在 JSON，并在交互看板中展开查看。",
        "- 新清单先核对平台、招聘方及岗位 ID，重复岗位复用原记录。",
        "- 申请页和查询进度入口分别保存。已失效的申请链接仍保留，方便回溯原岗位。",
        "- 交接导入的已提交状态标为待核对。缺少精确岗位链接或编号的历史记录在备注中标明。",
        "- 日期只有年月时保留原粒度。记录新建时间与实际投递日期分别保存。",
        "- 招聘时间线保存邀请、各轮面试和结果的实际日期。Ghost 保留原阶段，招聘方有新进展后会重新计算。",
        "- Ready to go 表示等待用户逐岗复核和提交。", "",
    ])
    if state.get("candidate_notes"):
        lines.extend(["## 尚待定位的公司备选", ""])
        lines.extend("- " + cell(note) for note in state["candidate_notes"])
        lines.append("")
    path = directory / "README.md"
    content = "\n".join(lines)
    if path.exists() and path.read_text() == content:
        return
    descriptor, name = tempfile.mkstemp(dir=directory, prefix=".index-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(content)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def summarize(job):
    if job.get("state", "queued") not in STATE_LABELS:
        raise ValueError("Unknown job state")
    questions = job.get("questions", [])
    identifiers = [question["id"] for question in questions]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Duplicate question IDs")
    for question in questions:
        if question.get("status", "awaiting_answer") not in QUESTION_STATES:
            raise ValueError("Unknown question state")
        if not isinstance(question.get("answer", ""), str):
            raise ValueError("Question answers must be strings")
    job["pending_question_count"] = sum(
        question.get("status") not in {"applied", "skipped"}
        for question in questions
    )
    job["ready_to_go"] = (
        job.get("state") == "ready_for_review"
        and all(job.get("verification", {}).get(key) is True for key in VERIFICATION_KEYS)
        and not job.get("blockers")
        and all(
            not question.get("required", True) or question.get("status") == "applied"
            for question in questions
        )
    )
    if job.get("state") == "submitted":
        evidence = job.get("submission_evidence") or {}
        if not evidence.get("text") or not evidence.get("observed_at"):
            raise ValueError("Submitted records require timestamped evidence")
    return job


def merge_job(existing, patch):
    patch = copy.deepcopy(patch)
    if not isinstance(patch.get("id"), str) or not patch["id"]:
        raise ValueError("Every job needs a non-empty string id")
    if {"recruiting", "recruiting_events"} & patch.keys():
        raise ValueError("Use record-event to add recruiting progress")
    job = copy.deepcopy(existing or {
        "id": patch["id"], "state": "queued", "questions": [],
        "fields": [], "blockers": [], "notes": [],
        "verification": dict.fromkeys(VERIFICATION_KEYS, False),
    })
    incoming_questions = patch.pop("questions", [])
    old_content = copy.deepcopy({key: job.get(key) for key in (
        "fields", "questions", "blockers", "resume_path", "apply_url",
    )})
    for question_patch in incoming_questions:
        question_patch = copy.deepcopy(question_patch)
        identifier = question_patch.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("Every question needs a non-empty string id")
        question = next((item for item in job["questions"] if item["id"] == identifier), None)
        expected = question_patch.pop("expected_answer", None)
        if question is not None and question_patch.get("status") == "applied":
            if expected is None or expected != question.get("answer", ""):
                raise Conflict("Answer changed. Read the latest record before confirming ATS fill.")
        if question is None:
            question = {"id": identifier, "answer": "", "status": "awaiting_answer"}
            job["questions"].append(question)
        previous_answer = question.get("answer", "")
        question.update(question_patch)
        if previous_answer != question.get("answer", "") and "status" not in question_patch:
            question["status"] = "answered" if question["answer"].strip() else "awaiting_answer"
    job.update(patch)
    changed = any(job.get(key) != value for key, value in old_content.items())
    if existing and changed and existing.get("state") not in POST_SUBMISSION_STATES:
        clear_ready(job)
    if existing and existing.get("state") in POST_SUBMISSION_STATES and job.get("state") not in POST_SUBMISSION_STATES:
        raise Conflict("A submitted record cannot be reopened through an ordinary update")
    timestamp = now()
    changed_fields = sorted(
        key for key in set(job) - {"history", "updated_at", "ready_to_go", "pending_question_count"}
        if existing is None or job.get(key) != existing.get(key)
    )
    history = copy.deepcopy((existing or {}).get("history", []))
    if changed_fields:
        history.append({
            "at": timestamp,
            "event": "record_created" if existing is None else "record_updated",
            "from_state": (existing or {}).get("state"),
            "to_state": job.get("state"),
            "changed_fields": changed_fields,
        })
    job["history"] = history
    job["updated_at"] = timestamp
    return summarize(job)


class Store:
    def __init__(self, workspace):
        self.directory = Path(workspace).resolve() / "applications"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "applications.json"

    def transact(self, operation=None):
        with (self.directory / ".applications.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = json.loads(self.path.read_text()) if self.path.exists() else {
                "schema_version": 1, "jobs": [],
            }
            if state.get("schema_version") != 1 or not isinstance(state.get("jobs"), list):
                raise ValueError("Unsupported application record format")
            identifiers = [job["id"] for job in state["jobs"]]
            if len(identifiers) != len(set(identifiers)):
                raise ValueError("Duplicate job IDs in stored records")
            if operation:
                operation(state)
            for job in state["jobs"]:
                job.setdefault("state", "queued")
                summarize(job)
            if operation or not self.path.exists():
                state["updated_at"] = now()
                descriptor, name = tempfile.mkstemp(dir=self.directory, prefix=".applications-", suffix=".tmp")
                try:
                    with os.fdopen(descriptor, "w") as stream:
                        json.dump(state, stream, ensure_ascii=False, indent=2)
                        stream.write("\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(name, self.path)
                finally:
                    if os.path.exists(name):
                        os.unlink(name)
            zone = ZoneInfo(state.get("timezone", "UTC"))
            today = datetime.now(zone).date()
            state["today"] = today.isoformat()
            state["recruiting_event_types"] = {kind: values[0] for kind, values in EVENT_TYPES.items()}
            for job in state["jobs"]:
                if job["state"] in POST_SUBMISSION_STATES:
                    job["recruiting"] = recruiting_view(job, today, zone)
            write_index(self.directory, state)
            return state

    def upsert(self, patches):
        if isinstance(patches, dict):
            patches = [patches]
        if not isinstance(patches, list):
            raise ValueError("Patch must be a job object or list of job objects")

        def apply(state):
            for patch in patches:
                index = next((i for i, job in enumerate(state["jobs"]) if job["id"] == patch.get("id")), None)
                existing = state["jobs"][index] if index is not None else None
                job = merge_job(existing, patch)
                if index is None:
                    state["jobs"].append(job)
                else:
                    state["jobs"][index] = job
        return self.transact(apply)

    def record_event(self, payload):
        kind = payload.get("kind")
        if not isinstance(kind, str) or kind not in EVENT_TYPES:
            raise ValueError("请选择有效的招聘事件。")

        def event_date(key):
            value = payload.get(key)
            day = local_day(value, timezone.utc)
            if not day or day.isoformat() != value:
                raise ValueError("请选择有效的日期。")
            return day

        occurred = event_date("date")
        event = {"kind": kind, "date": occurred.isoformat()}
        round_number = payload.get("round")
        if round_number is not None:
            if not kind.startswith("interview_") or type(round_number) is not int or round_number < 1:
                raise ValueError("面试轮次须为正整数。")
            event["round"] = round_number
        if kind == "interview_scheduled":
            scheduled = event_date("scheduled_for")
            if scheduled < occurred:
                raise ValueError("面试安排日期不能早于记录的事件日期。")
            event["scheduled_for"] = scheduled.isoformat()
        for key, limit in (("note", 2000), ("source", 500)):
            value = payload.get(key, "")
            if not isinstance(value, str) or len(value) > limit:
                raise ValueError("备注或来源超出长度限制。")
            if value.strip():
                event[key] = value.strip()
        event.setdefault("source", "用户记录")

        def apply(state):
            job = next((item for item in state["jobs"] if item["id"] == payload.get("job_id")), None)
            if not job or job.get("state") not in POST_SUBMISSION_STATES:
                raise Conflict("请先确认该岗位已提交申请。")
            zone = ZoneInfo(state.get("timezone", "UTC"))
            submitted_on = local_day(job.get("submitted_at"), zone) or local_day(job.get("confirmation_received_at"), zone)
            if occurred > datetime.now(zone).date() or submitted_on and occurred < submitted_on:
                raise ValueError("事件日期须在投递日期和今天之间。")
            events = job.setdefault("recruiting_events", [])
            if any(all(item.get(key) == event.get(key) for key in ("kind", "date", "round", "scheduled_for", "note", "source")) for item in events):
                return
            stage_date = max((item["date"] for item in events if EVENT_TYPES[item["kind"]][1]), default="")
            previous = job["state"]
            next_stage = EVENT_TYPES[kind][1]
            timestamp = now()
            events.append(dict(event, recorded_at=timestamp))
            if next_stage and event["date"] >= stage_date and (
                previous not in TERMINAL_STATES or next_stage in TERMINAL_STATES
            ):
                job.update(state=next_stage, checked_at=timestamp, status_source={
                    "kind": "recruiting_event", "label": event["source"],
                })
            job["updated_at"] = timestamp
            job.setdefault("history", []).append({
                "at": timestamp, "event": "recruiting_event_recorded", "from_state": previous,
                "to_state": job["state"], "changed_fields": ["recruiting_events"],
            })

        return self.transact(apply)

    def answer(self, payload):
        def apply(state):
            job = next((item for item in state["jobs"] if item["id"] == payload.get("job_id")), None)
            if job is None:
                raise ValueError("Job no longer exists")
            if job.get("state") in POST_SUBMISSION_STATES:
                raise Conflict("This application is already submitted")
            changed = False
            for update in payload.get("answers", []):
                question = next((item for item in job["questions"] if item["id"] == update.get("id")), None)
                if question is None:
                    raise Conflict("Question changed. Refresh the dashboard.")
                answer = update.get("answer")
                if not isinstance(answer, str):
                    raise ValueError("Answers must be text")
                if question.get("answer", "") != update.get("expected_answer", ""):
                    raise Conflict("An answer changed elsewhere. Your edits remain on this page.")
                if answer != question.get("answer", ""):
                    question.update(answer=answer, status="answered" if answer.strip() else "awaiting_answer", answered_at=now())
                    changed = True
            if changed:
                previous_state = job.get("state")
                clear_ready(job)
                job["state"] = "waiting_for_user"
                job["updated_at"] = now()
                job.setdefault("history", []).append({
                    "at": job["updated_at"], "event": "answers_saved",
                    "from_state": previous_state, "to_state": job["state"],
                    "changed_fields": ["questions"],
                })
        return self.transact(apply)


def serve(store, port):
    html = (Path(__file__).resolve().parent.parent / "assets" / "dashboard.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, data, content_type="application/json; charset=utf-8"):
            body = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, dict) else data
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self):
            if not self.valid_host():
                return self.respond(403, {"error": "Local access only"})
            route = urlsplit(self.path).path
            if route == "/":
                return self.respond(200, html, "text/html; charset=utf-8")
            if route == "/api/state":
                try:
                    return self.respond(200, store.transact())
                except (OSError, ValueError) as error:
                    return self.respond(500, {"error": str(error)})
            self.respond(404, {"error": "Not found"})

        def do_POST(self):
            origin = f"http://127.0.0.1:{self.server.server_port}"
            if not self.valid_host() or self.headers.get("Origin") not in {None, origin}:
                return self.respond(403, {"error": "Local access only"})
            endpoints = {"/api/answers": store.answer, "/api/recruiting-events": store.record_event}
            if self.path not in endpoints or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.respond(400, {"error": "Expected a dashboard JSON request"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 1_000_000:
                    raise ValueError("Invalid request size")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("Expected a JSON object")
                self.respond(200, endpoints[self.path](payload))
            except Conflict as error:
                self.respond(409, {"error": str(error)})
            except (ValueError, TypeError, KeyError) as error:
                self.respond(400, {"error": str(error)})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    update = commands.add_parser("upsert")
    update.add_argument("--patch", type=Path, required=True)
    event = commands.add_parser("record-event")
    event.add_argument("--event", type=Path, required=True)
    web = commands.add_parser("serve")
    web.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    store = Store(args.workspace)
    try:
        if args.command == "upsert":
            state = store.upsert(json.loads(args.patch.read_text()))
            print(json.dumps({"jobs": len(state["jobs"]), "path": str(store.path)}, ensure_ascii=False))
        elif args.command == "record-event":
            payload = json.loads(args.event.read_text())
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object")
            store.record_event(payload)
            print(store.path)
        elif args.command == "serve":
            store.transact()
            serve(store, args.port)
        else:
            store.transact()
            print(store.path)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
