---
description: Generate a pre-meeting briefing for a specific person, or for all of today's meetings
argument-hint: [person-name-or-email | today | tomorrow]
---

Generate a pre-meeting briefing using the orchestrator at `C:\Users\apate\.claude\.agents\pre-meeting-briefing\run_briefings.py`.

**How to interpret the argument** `$ARGUMENTS`:

1. **If the argument is `today` or is empty** → run:
   `python C:\Users\apate\.claude\.agents\pre-meeting-briefing\run_briefings.py --today`

2. **If the argument is `tomorrow`** → run:
   `python C:\Users\apate\.claude\.agents\pre-meeting-briefing\run_briefings.py --tomorrow`

3. **If the argument looks like an email address** → run:
   `python C:\Users\apate\.claude\.agents\pre-meeting-briefing\run_briefings.py --email $ARGUMENTS`

4. **If the argument looks like a person's name** (Kevin, Gary, Ashleigh, Adam, Cory, Michael, Heather, Jenna, Chelsea, Jordan) → map to the email:
   - Kevin → kprentiss@nsls.org
   - Gary → gtuerack@nsls.org
   - Adam → astone@nsls.org
   - Ashleigh → asmith@nsls.org
   - Cory → ccapoccia@nsls.org
   - Michael → mobrien@nsls.org
   - Heather → hdarnell@nsls.org
   - Jenna → jfontanez@nsls.org
   - Chelsea → cbyers@nsls.org
   - Jordan → jtannenbaum@nsls.org
   Then run with `--email <mapped-email>`.

After the orchestrator finishes, list the generated briefings in `C:\Users\apate\Obsidian\AP\00-inbox\pre-meeting\` with their filenames and open the most recent one so Anish can read it.

**If a briefing already exists** for the target person + meeting, the orchestrator will say "already exists" — in that case, just read it out, don't regenerate.

**Important:**
- Use Bash to invoke the python command
- The orchestrator can take 2–5 minutes per briefing (it invokes a Claude sub-session)
- Stream the output so Anish can see progress
