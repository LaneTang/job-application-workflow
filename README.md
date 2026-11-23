# Job Application Workflow

A Codex skill for preparing job applications with a local dashboard and a human review step before submission.

用 computer use 承担重复填表、上传已确认简历、集中收集待答题，并在本地追踪投递、测评、各轮面试和结果。适合单岗试跑、批量申请及恢复未完成申请。

## 工作方式

1. 读取最新 profile、指定简历和岗位清单，核对岗位并去重。
2. 填写可确认的信息，结合个人实际情况与完整题目判断 sponsorship。
3. 将真实缺项、开放题和需要本人决定的协议集中到看板。
4. 用户保存答案后回填并核验，准备到最终复核。
5. 默认由用户最终提交；代点提交必须在用户复核后取得该岗明确授权。
6. 保存申请入口、岗位快照、进度查询方式和凭据，后续记录招聘时间线。

**Ready to go 与已提交分别记录。** 保存答案不等于已回填；上传附件不等于已申请。等待招聘方回复超过 21 天的岗位标为 Ghost，同时保留原招聘阶段。

## 安装

需要支持本地 skills 和 computer use 的 Codex 环境。看板使用 Python 3.9+ 标准库，当前支持 macOS / Linux（文件锁使用 `fcntl`）；部分精简系统需安装 IANA 时区数据库。

```bash
git clone https://github.com/LaneTang/job-application-workflow.git ~/.agents/skills/job-application-workflow
```

如果你的环境从 `~/.codex/skills` 加载，也可安装到该目录。选择一个已被当前客户端发现的目录即可。若新 skill 未出现，重启 Codex 后重试。

## 准备独立的求职工作区

将私有资料与本仓库分开放置：

```text
my-job-search/
  profile/
    profile.md
    confirmed-resume.pdf
  applications/               # 看板自动生成
    applications.json
    README.md
```

使用 [profile 模板](examples/profile.example.md) 创建自己的 `profile/profile.md`。确认学校、实习时间、授权背景及简历版本，不确定项保留为未知。仓库不包含任何真实申请人的资料或账本。

在 Codex 中输入：

```text
使用 $job-application-workflow 处理下面的岗位。
工作区是 /absolute/path/to/my-job-search。
先读取最新 profile 和现有账本，准备到提交前交我复核。
[岗位清单与链接]
```

## 本地看板

```bash
python3 ~/.agents/skills/job-application-workflow/scripts/dashboard.py --workspace /absolute/path/to/my-job-search init
python3 ~/.agents/skills/job-application-workflow/scripts/dashboard.py --workspace /absolute/path/to/my-job-search serve --port 0
```

打开命令返回的 `http://127.0.0.1:<port>`。端口 0 会自动选择可用端口。服务只监听本机，支持填写答案、检索岗位和维护招聘时间线；停止进程后记录仍在本地。

岗位导入、回填核验、招聘事件格式及时区配置见 [记录与看板说明](references/records-and-dashboard.md)。工作流入口见 [SKILL.md](SKILL.md)。Ghost 在读取账本时重算；本 skill 不会在后台定时检查邮箱或发送通知。

## 数据与权限

申请资料保存在使用者自己的工作区。只有使用者授权的申请操作才将资料传给招聘站点。隐私声明按个人 profile 设置处理；法律协议单独复核。不要提交真实 profile、简历、邮箱正文、验证码或申请账本到本仓库。

本工具帮助组织申请流程，不保证录用、签证资格或学校批准，也不代替招聘方和学校对具体要求的确认。

## 验证

```bash
python3 -m unittest discover -s tests -v
```
