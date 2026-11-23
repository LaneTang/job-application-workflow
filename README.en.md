# Job Application Workflow

English | [简体中文](README.md)

## TL;DR

***🟡 “Use the $job-application-workflow skill and follow the workflow to help me apply to these 10 positions.”***

Just give your agent your resume and profile, and it can automate your job applications! No more digging through messy websites to find position links or filling out long, repetitive forms over and over.

With this skill, you no longer have to tell every company where you study, what your name is, when you are available for an internship, whether you can legally work in the United States, whether you are a veteran, and so on.

### This skill alone can make your career life 10 times easier!

### Reminder

This skill requires computer use / browser use capabilities. I have only tested it with GPT, where it has worked very well for me. I use the Edge browser, which **requires the ChatGPT browser extension**.

Suggested agents: ChatGPT / Claude / other agents with computer use capabilities.

## Got it. How do I get started?

Tell your agent:

```text
Please install this skill for me:
https://github.com/LaneTang/job-application-workflow

After installation, check that SKILL.md and its supporting resources are complete,
and tell me how to invoke it.
Only install the skill for now; do not run any job applications.
```

## Things you may want to know

## What is a profile?

A simple `.md` document containing your basic information, education, internship availability, work authorization, gender, self-identification information, address, willingness to work on-site, and anything else relevant.

For reference, here is the structure of my `profile.md`:

```markdown
# Job profile

## basic info
### education
### connect link
### diversity questions / Self-Identification Survey
### veteran / military / public servicer related

## immigration and internship positioning

## Job Experience

## work preferences

## compensation

## agreement

## application workflow
```

## My suggestions

Keep your resume and profile in a local folder and give the agent permission to access it, or put them in a folder the agent can already access.

Think about what information you want to provide to the AI. Draft an initial `profile.md`, then test this skill on a couple of positions and adjust it as you go.

## The idea behind this skill

Skill input: a list of relevant positions.

I want Codex to automate the following through computer use:

1. Check the application environment and known profile information. If extra information or actions are needed, such as logging in, notify me so I can handle them, then continue once resolved.
2. Automatically fill in standard application information using my profile: education, internship availability, work authorization, resume attachment, location, willingness to work on-site, and so on.
3. Identify and record questions that require my own input, such as a cover letter, why I chose the company, what I want to learn during the internship, or my favorite C++ feature (?).
4. Organize everything into a standardized table, optionally using an interactive web UI, and show it to me. Treat each individual application being filled out as a separate job object. Its basic properties include the company, company link, position, application link, number of unanswered questions, all unanswered questions in an expandable view, and a `ready to go` boolean.
5. Provide an interactive way for me to answer the questions. After I finish answering, continue using computer use to fill in the remaining fields, set `ready to go` to true, and notify me.
6. Stop at the final preview after filling everything out. Show the resume used, completed answers, remaining items to confirm, and the `ready to go` status, then ask me to review. I click the final submission button myself.

Skill output: updates to the application forms / web UI.

### Submission rules

Codex SHOULD NOT apply directly without my review. I must review the final preview for every position.

- Instructions such as “apply to this position,” “continue,” “add this one,” or “apply to five positions at once” authorize preparation and form filling. Clicking Submit, Submit application, Send application, or any other button that actually sends an application requires my explicit authorization for that specific position after I review it. Otherwise, I click it myself.
- `ready to go = true` means the materials and form are prepared and waiting for my review and submission. A submitted status must be supported by an actual success page or other clear evidence.
- A preference to agree to application privacy notices by default applies only to those notices. Final submission must still follow the per-position review rules above.
