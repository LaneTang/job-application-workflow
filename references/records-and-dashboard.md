# 岗位记录与交互看板

默认数据位于工作区 `applications/applications.json`。看板使用 Python 标准库，只监听本机。以下变量需在运行时设为实际路径。

每次脚本写入账本会同步生成 `applications/README.md`，可直接在文件中浏览岗位目录和查询入口。JSON 是维护源，索引按记录重新生成。

```bash
python3 "$SKILL_DIR/scripts/dashboard.py" --workspace "$WORKSPACE" init
python3 "$SKILL_DIR/scripts/dashboard.py" --workspace "$WORKSPACE" upsert --patch /absolute/path/job-patch.json
python3 "$SKILL_DIR/scripts/dashboard.py" --workspace "$WORKSPACE" serve --port 0
```

`serve` 打印实际 localhost URL。保留进程，在浏览器打开并交付用户。复用有效看板，使用新端口恢复已结束的服务。用户保存后回到当前对话说“继续回填”，Codex 读取本地 JSON 接续。

`upsert` 接收一个岗位补丁或岗位补丁列表，按 `id` 合并。只传实际改动字段。题目按 `id` 合并，省略的题目及答案保持原状。后台更新不传旧 `answer` 或 `status` 快照，避免覆盖看板中较新的答案。

写入补丁后，刷新看板以显示最新核验状态。用户正在编辑时先让其保存，避免丢失输入。

示例使用虚构数据，实际运行时填入核验结果。

```json
{
  "id": "greenhouse/example/123",
  "company": "Example Robotics",
  "company_url": "https://example.com",
  "role": "Robotics Intern",
  "jd_url": "https://example.com/jobs/123",
  "apply_url": "https://example.com/jobs/123/apply",
  "state": "waiting_for_user",
  "location": "Example City",
  "checked_at": "2026-11-21T15:00:00-05:00",
  "resume_path": "/absolute/path/confirmed-resume.pdf",
  "fields": [
    {"label": "First name", "value": "Example", "source": "profile/profile.md", "verified": true}
  ],
  "questions": [
    {
      "id": "start-date",
      "text": "When can you start?",
      "required": true,
      "kind": "missing_profile",
      "options": [],
      "limit": null,
      "answer": "",
      "status": "awaiting_answer",
      "source_url": "https://example.com/jobs/123/apply"
    }
  ],
  "blockers": [],
  "notes": [],
  "verification": {
    "required_fields_complete": false,
    "attachments_verified": true,
    "final_review_reached": false
  },
  "submission_evidence": null
}
```

## 状态约定

- `id` 优先由 ATS、招聘方和岗位 ID 组成。无法识别时使用已核验的规范化申请 URL。
- `state` 可用 `queued`、`checking`、`filling`、`waiting_for_user`、`ready_for_review`、`submitted`、`closed`、`needs_review`、`blocked`、`invited`、`assessment`、`interviewing`、`offer`、`accepted`、`declined`、`rejected`、`withdrawn`。
- 题目 `status` 可用 `awaiting_answer`、`answered`、`applied`、`skipped`。`skipped` 适用于用户允许跳过的非必填题。
- `kind` 用 `open_ended`、`missing_profile`、`eligibility`、`agreement` 或 `other`。
- `fields` 保存字段、来源与核验状态。密码、OTP 和验证码不写入账本。
- `blockers` 保存真实未解依赖。普通最终复核本身不作为 blocker。
- `notes` 记录下拉映射、日期粒度、非必填留空、ASAP 差异及解析产生的待确认值。
- `submission_evidence` 为 `{ "kind": "success_page 或 user_confirmation", "url": "...", "observed_at": "...", "text": "成功提示或用户确认" }`，仅在实际提交后记录。
- `pending_question_count` 包含尚未回填的题，已回答但待回填仍算 pending。
- `ready_to_go` 要求 `state=ready_for_review`、三个 verification 值全部为 true、没有 blocker，所有必填题均为 `applied`。

看板保存答案只修改对应题目，设为 `answered`，清除该岗旧 ready。清空答案则改为 `awaiting_answer`。页面刷新不会覆盖尚未保存的编辑。

变更字段或题目会清除 ready 并回到 `filling`，再次核验后通过单独补丁恢复 `verification` 和 `ready_for_review`。已提交岗位保留证据。

状态文件使用文件锁与原子替换写入，每次基于最新文件合并。浏览器回填题目时带上 `expected_answer`，脚本只在答案仍一致时将其设为 `applied`，防止并行编辑时将旧答案误记为已回填。

题目回填后的补丁示例为 `{"id":"greenhouse/example/123","questions":[{"id":"start-date","status":"applied","expected_answer":"用户最近保存的答案"}]}`。全部核验完成后，再单独更新 `state`、`checked_at` 和三个 `verification` 标记。

## 长期状态追踪

- `identifiers` 保存 ATS 名、招聘方、岗位 ID 及已核对的其他编号，便于从新链接识别重复岗位。
- `posting_status` 记录职位开放、关闭、链接失效、开放状态待核对等事实。申请进入面试或拒绝时更新 `state`，职位页面关闭本身不能推导拒信。
- `job_details` 保存当时已知的岗位摘要、地点、实习时段、到岗方式、薪资、关键要求及资格差异。字段未知时留空并注明缺项。页面可能下架，故保留该快照与来源。
- `resume_path` 和可选的 `resume_sha256` 标识实际使用的文件版本，`draft_evidence` 可保存草稿截图路径和观察日期。
- `tracking` 保存已核对的查询 URL、门户操作路径及邮件搜索关键词。候选人门户未识别时使用确认邮件或招聘人员联系查询的具体说明，不能编造门户链接。
- `status_source` 保存 `{ "kind": "success_page / user_confirmation / handoff_report / live_page / supplied_list", "label": "可供用户阅读的来源", "reference": "URL、本地文件或对话说明" }`。
- 确认邮件可使用 `kind=confirmation_email`。保存 message ID、原邮件显示链接、接收时间及与岗位有关的简短摘要到 `confirmation_emails`，省略登录令牌、个性化重定向链接和无关正文。普通职位推荐邮件不构成投递证据。
- 邮件只确认公司收件而未列具体岗位时，记录 `status_confidence=company_confirmed_role_unverified`，保留岗位对应关系待核对的说明。已连接原投递邮箱时，可只读检索已知公司和岗位的确认邮件补充记录。
- `status_confidence=imported_unverified` 标明仅来自历史交接的状态。已提交的交接记录允许使用 `submission_evidence.kind=handoff_report`，同时保留该标记和导入日期。后续实际核验后更新凭据并设为 `verified`。
- `history` 由脚本自动追加记录新建、字段或状态变化、用户保存答案的事件。`history[].at` 表示本地记录变更时间，实际事件日期来自证据的 `observed_at` 或 `checked_at`，不能相互代替。
- 对只有公司名称的备选，不伪造岗位对象。可在 `applications/README.md` 记录待定位候选，找到具体岗位后再建立对象。

## 招聘进展与 Ghost

- 用户可在已投岗位的「招聘时间线」中添加进展。Codex 从用户报告、招聘方邮件或候选人门户核实后，用同一个事件接口写入。填写实际发生日期，来源写简短且可追溯的标签，不保存邮件正文、会议链接中的访问令牌或凭据。
- 事件类型包括 `interview_invited`、`interview_scheduled`、`interview_completed`、`assessment_invited`、`assessment_completed`、`employer_reply`、`action_requested`、`candidate_replied`、`offer`、`accepted`、`declined`、`rejected`、`withdrawn`。面试事件可带任意正整数 `round`，轮次未知时留空。安排面试须填写 `scheduled_for`。日期使用账本时区的 `YYYY-MM-DD`。
- 每次写入保留原投递凭据和已有事件，重复提交同一事件只留一份。先补录旧事件时按实际日期进入时间线。后补的旧阶段不会替换较新的阶段。使用「已回复招聘方」记录完成招聘方要求后的等待起点。自动回执和单方面催问不作为招聘方回复事件。
- 等待招聘方时，从已知投递日期、最近一次实质进展、面试结束或候选人按要求回复之日计时。已安排的面试在安排日期过后开始计时，完成日期已知时以完成事件为准。待本人行动期间和未来已有面试安排期间暂停计时。收到 Offer、拒信、撤回或决定接受、婉拒 Offer 后停止计时。
- 超过 21 个日历日才标为 Ghost，第 21 天仍为等待。起点未知时显示待补充。Ghost 是随日期重新计算的标记，独立于原招聘阶段。添加新进展后会清除过期标记并按最新事件重新计算。看板和本地 Markdown 索引在读取账本时刷新。招聘事件在 `recruiting_events` 中持久保存，Ghost 在界面和索引按日计算。

用 `python3 "$SKILL_DIR/scripts/dashboard.py" --workspace "$WORKSPACE" record-event --event /absolute/path/event.json` 写入确认过的招聘进展。例如：

```json
{
  "job_id": "greenhouse/example/123",
  "kind": "interview_completed",
  "round": 2,
  "date": "2026-11-21",
  "source": "用户确认",
  "note": "技术面已结束，等下一步"
}
```

## 配置时区

新账本未指定时区时使用 UTC。使用者可在停止服务后，为 `applications/applications.json` 顶层设置 IANA `timezone`，例如 `Europe/London` 或 `America/New_York`，再重启服务。不要覆盖已有岗位数据。Ghost 标记在读取账本时按该时区重算。

## English dashboard filters

The dashboard UI is in English; user-entered questions, notes and source evidence retain their original language. Filters appear in this order: All, need refill, something wrong, ready to go, submitted, rejected, ghost, interview invited, done interview, more round, offered.

Each job belongs to exactly one filter besides All. Rejected and offered outcomes take precedence, followed by Ghost, interview progress, submitted, unresolved preparation issues, ready to go and missing answers. `need refill` contains only jobs with unanswered required questions and no separate blocking issue; `something wrong` contains other incomplete or blocked applications. `submitted` excludes the separately classified recruiting stages and outcomes; assessments remain here with an Assessment comment. `done interview` denotes a completed first or unspecified round; `more round` denotes a known round greater than one, with the round number and event shown in the row comment and timeline. Offers include accepted or declined offers; original events remain in the timeline. Closed and withdrawn records retain their specific state in comments. No underlying application state or evidence is rewritten by filtering.

Run `node tests/test_dashboard_filters.cjs` to validate frontend syntax and classification alongside the Python tests.

## Submission answer history

The dashboard shows each job’s recorded submission date and an Application answers overlay. When submission is first recorded with evidence, the store automatically preserves `submission_snapshot` (questions, standard fields, notes, resume version and capture time). Later record edits do not replace this snapshot; ordinary patches cannot overwrite it. Legacy applications without a snapshot show available local records with an explicit historical-completeness notice. Missing or redacted values are never reconstructed from the current profile.

## Preparation issues

`need refill` contains only applications missing required answers. Other incomplete applications appear under `something wrong`. An optional `application_issue` object records `kind` (`verification`, `technical`, `deferred`, or `mismatch`), `reason`, `action` (the recommended next step), and optional `retry_after`. This is a preparation issue, not an employer rejection or a decision to withdraw. It prevents ready-to-go status. Submitted and recruiting stages take precedence over old preparation issues. Resolve the issue explicitly with `application_issue: null` after checking the dependency, then reverify readiness.
