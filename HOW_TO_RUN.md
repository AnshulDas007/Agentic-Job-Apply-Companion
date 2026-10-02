# How to Run — Agentic-JobApply-Companion

> Complete step-by-step guide to setting up, running, and using the project.

---

## Overview — How This Project Works

This project is a **semi-autonomous job application bot**. It runs on **GitHub Actions** (free, no server needed) and uses **GitHub Issues** as the review interface (you approve/reject jobs from your phone).

```
┌─────────────────────────────────────────────────────────────┐
│                    YOUR DAILY WORKFLOW                       │
│                                                             │
│  1. Bot scrapes jobs automatically (daily, GitHub Actions)  │
│  2. Bot opens GitHub Issues for qualifying jobs             │
│  3. You review Issues on your phone/browser                 │
│  4. You label "approve" or "reject"                         │
│  5. Bot auto-applies to approved Tier 1 jobs                │
│  6. Tier 2 jobs (LinkedIn/Indeed) → you apply manually      │
│     using the pre-filled details from the Issue             │
└─────────────────────────────────────────────────────────────┘
```

**You only need to do the one-time setup below. After that, everything runs automatically.**

---

## Prerequisites

Before starting, you need these accounts (all free):

| Service | Sign Up Link | What It's For | Free Tier |
|---|---|---|---|
| **Groq** | [console.groq.com](https://console.groq.com) | Resume parsing, job scoring | 14,400 req/day |
| **Google AI Studio** | [aistudio.google.com](https://aistudio.google.com) | Cover letters, legal review | 60 req/min |
| **Apify** | [apify.com](https://apify.com) | LinkedIn/Indeed/Naukri scraping | $5/mo free credit |
| **GitHub** | [github.com](https://github.com) | Hosting, Actions, Issues | Free |

> [!TIP]
> You already have your Groq and Apify keys. You need to get a Google AI API key from [aistudio.google.com](https://aistudio.google.com) → Click "Get API Key" → "Create API key in new project".

---

## PART 1: One-Time Local Setup

These steps run on your Mac, only once.

### Step 1.1: Open the Project

1. Open your IDE (e.g., VS Code, Cursor, Antigravity)
2. Open the project folder: **`/Users/Anshul/Documents/Projects/Agentic JobApply Companion`**

### Step 1.2: Open the Terminal

In your IDE, open the integrated terminal (`` Ctrl+` `` or `Cmd+` `` on Mac).

### Step 1.3: Activate the Virtual Environment

```bash
cd "/Users/Anshul/Documents/Projects/Agentic JobApply Companion"
source venv/bin/activate
```

You should see `(venv)` appear at the start of your terminal prompt. This means the Python environment is active.

### Step 1.4: Verify Dependencies

```bash
pip install -r requirements.txt
playwright install --with-deps chromium
```

This installs any missing packages and the Chromium browser for form filling.

### Step 1.5: Update Your .env File (if needed)

Your `.env` file already has most keys set. If you get a new Google AI API key, update it:

```bash
# Open .env in your editor and update the GOOGLE_AI_API_KEY line
# File location: /Users/Anshul/Documents/Projects/Agentic JobApply Companion/.env
```

> [!CAUTION]
> Never commit your `.env` file. It's already in `.gitignore`.

### Step 1.6: Parse Your Resume

This creates your candidate profile from your resume. You only do this once.

```bash
python main.py intake --resume /path/to/your/resume.pdf
```

Replace `/path/to/your/resume.pdf` with the actual path to your resume file.

**What happens:**
- The bot reads your resume (PDF or DOCX)
- Extracts your name, contact info, experience, projects, skills, education
- Asks you to fill any missing fields (phone, address, etc.)
- Saves everything to `data/candidate_profile.json`

### Step 1.7: Verify Your Profile

```bash
python main.py profile
```

This prints your parsed profile. Check that:
- ✅ Name is correct
- ✅ Email and phone are correct
- ✅ Experience entries match your resume (titles, companies, durations)
- ✅ Projects are listed separately from experience
- ✅ Skills look right

If anything is wrong, edit `data/candidate_profile.json` directly or run:
```bash
python manage_profile.py edit
```

### Step 1.8: Commit Your Profile to the Repo

The GitHub Actions workflows need your profile to run. Commit it:

```bash
git add data/candidate_profile.json
git commit -m "feat: add candidate profile"
git push origin main
```

---

## PART 2: GitHub Secrets Setup

The workflows run on GitHub's servers, so they need your API keys as **Secrets** (encrypted environment variables).

### Step 2.1: Open Your Repo Settings

1. Go to [github.com/AnshulDas007/Agentic-Job-Apply-Companion](https://github.com/AnshulDas007/Agentic-Job-Apply-Companion)
2. Click **Settings** (top-right of the repo page)
3. In the left sidebar, click **Secrets and variables** → **Actions**

### Step 2.2: Add Each Secret

Click **"New repository secret"** and add these one at a time:

| Name (exact) | Value |
|---|---|
| `GROQ_API_KEY` | Your Groq API key (from [console.groq.com](https://console.groq.com) → API Keys) |
| `GOOGLE_AI_API_KEY` | Your Google AI key (from [aistudio.google.com](https://aistudio.google.com) → Get API Key) |
| `APIFY_TOKEN` | Your Apify token (from [apify.com](https://apify.com) → Settings → Integrations) |

> [!IMPORTANT]
> The names must match **exactly** (all caps, underscores). The workflows reference them as `${{ secrets.GROQ_API_KEY }}` etc.

> [!NOTE]
> You do NOT need to add `GITHUB_TOKEN` — GitHub provides it automatically to every workflow.

---

## PART 3: Running the Pipeline

### Option A: Automatic (Recommended)

After Parts 1 and 2, the pipeline runs automatically on schedule:

| Workflow | Runs At | What It Does |
|---|---|---|
| **Daily Job Scrape and Score** | 9:00 AM UTC (2:30 PM IST) | Scrapes jobs → filters fraud → scores → opens Issues |
| **Apply to Approved Tier 1 Jobs** | 11:00 AM UTC (4:30 PM IST) | Reads `approve`-labeled Issues → applies → closes Issues |

**You don't need to do anything.** Just check your GitHub Issues tab for new jobs.

### Option B: Manual Trigger (for testing or immediate use)

1. Go to your repo on GitHub
2. Click the **Actions** tab
3. In the left sidebar, click **"Daily Job Scrape and Score"**
4. Click the **"Run workflow"** button (top right)
5. Click the green **"Run workflow"** button in the dropdown
6. Wait 2-5 minutes for it to complete

Then check the **Issues** tab — new qualifying jobs will appear as Issues.

### Option C: Run Locally (for debugging)

If you want to test the pipeline locally instead of on GitHub Actions:

```bash
cd "/Users/Anshul/Documents/Projects/Agentic JobApply Companion"
source venv/bin/activate

# Run Phase 1: Scrape and score
python run_pipeline.py scrape-and-score

# Run Phase 2: Apply to approved jobs (burn-in mode = dry run)
python run_pipeline.py apply-tier1 --burn-in
```

> [!WARNING]
> Running locally requires `GITHUB_TOKEN` and `GITHUB_REPOSITORY` in your `.env`. Add:
> ```
> GITHUB_TOKEN=your_personal_access_token_here
> GITHUB_REPOSITORY=AnshulDas007/Agentic-Job-Apply-Companion
> ```
> Get a token from [github.com/settings/tokens](https://github.com/settings/tokens) → Generate new token → Select `repo` scope.

---

## PART 4: Daily Usage — Reviewing Jobs

This is what you do every day (takes 2-5 minutes):

### Step 4.1: Open GitHub Issues

Go to [github.com/AnshulDas007/Agentic-Job-Apply-Companion/issues](https://github.com/AnshulDas007/Agentic-Job-Apply-Companion/issues)

Or use the **GitHub Mobile app** (iOS/Android) for phone-based review.

### Step 4.2: Review Each Job Issue

Each Issue looks like:

```
[Job] Backend Engineer — Acme Corp

📊 Match Score: 0.82 / 1.0
🛡️ Legitimacy: 0.90 / 1.0  
🏷️ Tier: Tier 1 (auto-apply eligible)
🔗 URL: https://boards.greenhouse.io/acme/123
📍 Location: Remote

📝 Cover Letter Draft (click to expand)
⚖️ Legal Flags: None detected

Instructions:
  - Label "approve" to auto-apply
  - Label "reject" to skip
```

### Step 4.3: Take Action

| Action | How | What Happens |
|---|---|---|
| **Approve (Tier 1)** | Add the `approve` label | Bot applies automatically on next workflow run |
| **Reject** | Add the `reject` label | Issue closed, job skipped |
| **Tier 2 (LinkedIn/Indeed)** | Read the details, apply manually | Use the cover letter draft and details provided |

**To add a label:** Click on the Issue → In the right sidebar, click "Labels" → Select `approve` or `reject`.

### Step 4.4: Check Results

After the apply workflow runs, approved Issues are automatically closed with a comment:

```
✅ Success — Application submitted via Greenhouse
```
or
```
❌ Failed — Form filling blocked (legal clause detected)
```

---

## PART 5: Useful Local Commands

These commands run on your local machine (in the project terminal):

| Command | What It Does |
|---|---|
| `python main.py profile` | View your candidate profile |
| `python main.py status` | Show pipeline statistics (jobs processed, applications, costs) |
| `python main.py intake --resume /path/to/resume.pdf` | Re-parse your resume (if you updated it) |
| `python manage_profile.py view` | View profile in detail |
| `python manage_profile.py edit` | Interactive profile editor |

---

## PART 6: Understanding the Burn-In Period

> [!IMPORTANT]
> The project starts in **burn-in mode** — the bot logs what it *would* apply to, but doesn't actually submit anything. This is a safety measure for the first 2 weeks.

**During burn-in:**
- Jobs are scraped, scored, and Issues are opened ✅
- You can approve/reject Issues ✅
- The apply workflow runs but **does NOT actually submit** — it just logs "dry run" ❌

**To disable burn-in (after you've verified everything works):**

1. Edit `.github/workflows/apply-tier1.yml`
2. Change `--burn-in` to `--no-burn-in` on this line:
   ```yaml
   run: python run_pipeline.py apply-tier1 --no-burn-in
   ```
3. Commit and push the change

---

## PART 7: Troubleshooting

### "No candidate profile found"
→ Run `python main.py intake --resume /path/to/resume.pdf` and commit `data/candidate_profile.json`

### Workflow failed on GitHub Actions
→ Go to **Actions** tab → Click the failed run → Read the logs to see what went wrong

### "GitHub token not found" (when running locally)
→ Add `GITHUB_TOKEN=your_pat_here` and `GITHUB_REPOSITORY=AnshulDas007/Agentic-Job-Apply-Companion` to your `.env`

### No Issues appearing after workflow runs
→ Check: Are secrets set? Is `data/candidate_profile.json` committed? Did the workflow pass?

### Want to change the scrape schedule?
→ Edit the `cron` line in `.github/workflows/scrape-and-score.yml`:
```yaml
schedule:
  - cron: '0 9 * * *'   # Change to your preferred time (UTC)
```

---

## File Reference

| File | Purpose | When You Touch It |
|---|---|---|
| `main.py` | Local CLI commands | Never (just run it) |
| `run_pipeline.py` | GitHub Actions entry point | Never (workflows run it) |
| `.env` | Local API keys | Once during setup |
| `.env.example` | Template showing required keys | Reference only |
| `data/candidate_profile.json` | Your parsed resume data | After running intake; edit if needed |
| `data/jobs_seen.json` | Dedup log (which jobs already processed) | Never (managed by the bot) |
| `.github/workflows/scrape-and-score.yml` | Daily scrape schedule | Only to change schedule/settings |
| `.github/workflows/apply-tier1.yml` | Daily apply schedule | Only to disable burn-in |
| `PROGRESS_TRACKER.md` | Build progress (for the developer) | Reference only |
| `README.md` | Project overview | Reference only |
