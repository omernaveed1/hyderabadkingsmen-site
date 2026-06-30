# Go-live checklist — hyderabadkingsmen.com on Cloudflare Pages

> One sitting, ~90 minutes. End state: hyderabadkingsmen.com serves real articles, llms.txt is at the root, Cloudflare auto-deploys every time you push to GitHub. Free, no hosting bill.

## What you'll create

- A GitHub account (free) + one repo
- A Cloudflare account (free) + one Pages project
- One DNS change at GoDaddy

## Prerequisites

- Windows 10/11 (the rest of this assumes Windows — you're on `C:\Users\Hp`)
- A GitHub account ([signup](https://github.com/signup) — use the same email as GoDaddy)
- A Cloudflare account ([signup](https://dash.cloudflare.com/sign-up))

---

## Step 1 — Install Hugo locally (10 min)

Open **PowerShell as administrator** and run:

```powershell
winget install Hugo.Hugo.Extended
```

If `winget` is not available, download the `hugo_extended_*_windows-amd64.zip` from [Hugo Releases](https://github.com/gohugoio/hugo/releases/latest), extract `hugo.exe`, put it in `C:\Hugo\bin\`, and add that path to your System Environment Variables → Path.

Open a **new** PowerShell window and verify:

```powershell
hugo version
```

You should see something like `hugo v0.139.0+extended`. If you see "command not found," the PATH didn't take — close all terminals, open a fresh one.

## Step 2 — Build and preview the site locally (10 min)

```powershell
cd C:\Users\Hp\AppData\Roaming\Claude\local-agent-mode-sessions\7d0a0e06-449f-4af7-b7a8-6e2c3f3304c0\8f9eb4dc-fda3-488e-a990-0a1e4d81fe7a\local_4b7012b1-5cee-4c27-bbf6-365ba53cd355\outputs\hyderabadkingsmen-site
hugo server
```

Open [http://localhost:1313](http://localhost:1313). You should see the homepage with three sample posts. Click around, verify the player profile and venue guide render. If a banner is missing, check that `static/banners/*.png` exists.

Press `Ctrl+C` to stop the server when done.

Permanent home for the site folder: I'd recommend copying it out of the Claude session folder to somewhere you control, like `C:\Users\Hp\Sites\hyderabadkingsmen-site\`. The Claude session folder may get cleaned up.

## Step 3 — Push to GitHub (15 min)

Install GitHub CLI (easiest path):

```powershell
winget install GitHub.cli
gh auth login
```

Pick GitHub.com → HTTPS → Login with web browser.

Then in the site folder:

```powershell
cd C:\Users\Hp\Sites\hyderabadkingsmen-site
git init
git add .
git commit -m "Initial site scaffold + 3 starter posts"
gh repo create hyderabadkingsmen-site --public --source=. --remote=origin --push
```

Confirm the repo exists at `https://github.com/<your-username>/hyderabadkingsmen-site`.

(If you prefer the GitHub website route: create a new repo there, then `git remote add origin https://github.com/<you>/hyderabadkingsmen-site.git && git push -u origin main`.)

## Step 4 — Create the Cloudflare Pages project (10 min)

1. Log in to [Cloudflare dashboard](https://dash.cloudflare.com).
2. Left sidebar → **Workers & Pages** → **Create** → **Pages** tab → **Connect to Git**.
3. Authorize Cloudflare to access your GitHub. Select `hyderabadkingsmen-site` from the repo list.
4. Project name: `hyderabadkingsmen` (this gives you a free `hyderabadkingsmen.pages.dev` subdomain for testing).
5. Production branch: `main`.
6. **Build settings** — this is the critical bit:
   - Framework preset: **Hugo**
   - Build command: `hugo --gc --minify`
   - Build output directory: `public`
   - Environment variables: add `HUGO_VERSION` = `0.139.0`
7. Click **Save and Deploy**. The first build takes ~1 minute.

When the build is green, open `https://hyderabadkingsmen.pages.dev` in your browser. The site should be live there.

## Step 5 — Attach hyderabadkingsmen.com as a custom domain (10 min)

In the Pages project dashboard:

1. **Custom domains** tab → **Set up a custom domain** → enter `hyderabadkingsmen.com`.
2. Cloudflare will tell you the domain isn't on Cloudflare yet and offer to walk you through moving it. Click **Begin DNS transfer**.
3. Cloudflare gives you **two nameservers** that look like `xxx.ns.cloudflare.com` and `yyy.ns.cloudflare.com`. Copy them.

Now in GoDaddy:

1. [account.godaddy.com/products](https://account.godaddy.com/products) → click `hyderabadkingsmen.com` (the **domain**, not the Coming Soon site) → DNS → **Nameservers** → **Change Nameservers** → **I'll use my own nameservers** → paste the two Cloudflare nameservers → Save.
2. GoDaddy will warn you that this will disconnect the Coming Soon site. That's fine — that's what you want.

Wait 10–60 minutes (sometimes up to 24 hours) for DNS to propagate. Cloudflare will email you when it sees the change. Once it does, `hyderabadkingsmen.com` will resolve to your Pages site.

Cloudflare also gives you free SSL automatically — no extra setup. The site will be `https://hyderabadkingsmen.com`.

## Step 6 — Verify llms.txt and AEO files (5 min)

Once the domain is live, open these in your browser:

- `https://hyderabadkingsmen.com/` — homepage with 3 posts
- `https://hyderabadkingsmen.com/llms.txt` — your AI-search discovery file (this is what we couldn't do on GoDaddy)
- `https://hyderabadkingsmen.com/llms-full.txt` — full corpus
- `https://hyderabadkingsmen.com/sitemap.xml` — Hugo auto-generates this
- `https://hyderabadkingsmen.com/robots.txt` — should explicitly allow GPTBot, ClaudeBot, PerplexityBot
- `https://hyderabadkingsmen.com/index.xml` — RSS feed

If any 404, check that `static/llms.txt` etc. are in your repo, then redeploy with a small commit.

## Step 7 — Submit to Google + AI surfaces (10 min)

1. **Google Search Console** — [search.google.com/search-console](https://search.google.com/search-console). Add `hyderabadkingsmen.com` as a property using DNS verification (Cloudflare makes this one click). Submit the sitemap URL.
2. **Indexing API** — in Search Console → URL Inspection → paste each of your 3 URLs (homepage, the post, the player page) → Request Indexing. Saves days.
3. **Bing Webmaster Tools** — [bing.com/webmasters](https://bing.com/webmasters). Same drill. ChatGPT search uses Bing.
4. **ICC/cricket directories** — submit `hyderabadkingsmen.com` to cricket-blog directories (CricketWeb, Crictracker forums) for early backlinks.

## Step 8 — How to publish post #4 onward

When you have a new post:

```powershell
cd C:\Users\Hp\Sites\hyderabadkingsmen-site
hugo new posts/srh-vs-csk-match-report.md
# Edit the new file in VS Code or Notepad. Paste content. Set draft: false.
git add .
git commit -m "Add SRH vs CSK match report"
git push
```

Cloudflare Pages sees the push, rebuilds, deploys. New post is live in ~60 seconds. No paste-into-editor work.

When you wire the agents to this repo (next phase — `FilesystemPublisher` is on the build list), the agent will run `git commit && git push` for you and the whole loop becomes hands-off.

## Things that will go wrong (and the fix)

**Hugo build fails on Cloudflare** with "theme not found." Fix: in `hugo.toml` you should have `theme = "kingsmen"`. Your repo must include `themes/kingsmen/` (the whole folder). Check git status — sometimes the theme folder doesn't get added because of nested `.git` directories.

**Site loads but CSS is broken.** Open the page, view source, check the CSS link. It should resolve to `/css/main.css`. If it's missing, the theme's `static/` folder didn't get included. Add `themes/kingsmen/static/` to git explicitly.

**DNS hasn't propagated after an hour.** Check at [dnschecker.org](https://dnschecker.org) — paste your domain, see which countries can resolve it. India is usually slowest. Worst case, wait overnight.

**Google Search Console says "Page indexed but not in sitemap."** Wait 48 hours, then re-submit. Don't worry about it on day 1.

## After this is live

Next phase: wire the agents from `hyderabadkingsmen-agents/` to push directly to this repo. That means:

- Adding a `FilesystemPublisher` to the agents (writes Markdown to `content/posts/`, banners to `static/banners/`)
- Adding a small `git commit && git push` after each agent run
- Setting up the agent on a cron job (or GitHub Action)

This is on the build list as task #6. When you're done with Step 8 above and you want this, say so and I'll wire it.
