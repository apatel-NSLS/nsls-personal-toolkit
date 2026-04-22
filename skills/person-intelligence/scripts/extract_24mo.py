"""Pull Fathom meetings back 24 months, filter small ones with SLT members, digest personal signals."""
import sys, json, os, re, time
sys.path.insert(0, 'C:/Users/apate/.claude/.mcp-servers/fathom')
from server import list_meetings, get_transcript

CACHE = 'C:/Users/apate/.claude/.mcp-servers/fathom/cache'
os.makedirs(CACHE, exist_ok=True)

SLT = {
    'kevin':   'kprentiss@nsls.org',
    'gary':    'gtuerack@nsls.org',
    'adam':    'astone@nsls.org',
    'ashleigh':'asmith@nsls.org',
    'cory1':   'cory.capoccia@gmail.com',
    'cory2':   'ccapoccia@nsls.org',
    'michael': 'mobrien@nsls.org',
}
SLT_EMAILS = {v.lower() for v in SLT.values()}

# Exclude recordings already digested in round 1
already = set()
for p in ['kevin','gary','adam','ashleigh','cory','michael']:
    f = f'{CACHE}/digest_{p}.json'
    if os.path.exists(f):
        with open(f) as fp:
            for m in json.load(fp):
                already.add(m['rid'])
print(f'Already digested in round 1: {len(already)} recordings')

# Step 1: pull meetings back to 2024-04-22
print('Pulling meetings back 24 months...')
cursor = None
all_meetings = []
pages = 0
while True:
    r = list_meetings(limit=50, cursor=cursor, recorded_after='2024-04-22T00:00:00Z')
    items = r.get('items', [])
    all_meetings.extend(items)
    cursor = r.get('next_cursor')
    pages += 1
    if pages % 5 == 0:
        print(f'  page {pages}, total {len(all_meetings)}')
    if not cursor:
        break
    if pages >= 100:  # safety cap
        break
    time.sleep(0.8)

# Save full index
with open(f'{CACHE}/all_meetings_24mo.json','w') as f:
    json.dump(all_meetings, f, indent=1)
print(f'Total meetings pulled 24mo: {len(all_meetings)} across {pages} pages')

# Step 2: filter to small meetings with SLT members, not already digested
by_person = {k: [] for k in ['kevin','gary','adam','ashleigh','cory','michael']}
skip_titles = ['SLT Huddle','SLT Standing','Manager Preview','All Staff','All-Staff','Mandatory']
for m in all_meetings:
    if m.get('recording_id') in already:
        continue
    invitees = m.get('calendar_invitees') or []
    if len(invitees) > 4:
        continue
    title = m.get('meeting_title') or m.get('title') or ''
    if any(x in title for x in skip_titles):
        continue
    invitee_emails = {i.get('email','').lower() for i in invitees}
    for person, email in SLT.items():
        if email.lower() in invitee_emails:
            key = 'cory' if person in ('cory1','cory2') else person
            by_person[key].append({
                'recording_id': m['recording_id'],
                'title': title,
                'start': m.get('recording_start_time',''),
                'n_invitees': len(invitees),
                'invitees': sorted(invitee_emails),
            })

for p, meetings in by_person.items():
    # Deduplicate by recording_id
    seen = set()
    unique = []
    for mm in meetings:
        if mm['recording_id'] not in seen:
            seen.add(mm['recording_id'])
            unique.append(mm)
    by_person[p] = unique
    print(f'{p}: {len(unique)} new small meetings to mine')

with open(f'{CACHE}/slt_new_meetings_24mo.json','w') as f:
    json.dump(by_person, f, indent=1)

# Step 3: fetch transcripts, extract keyword-matching + edge segments
KW = re.compile(
    r'\b('
    r'kids?|son|daughter|child|children|baby|babies|'
    r'wife|husband|spouse|partner|girlfriend|boyfriend|fiance|married|'
    r'mom|dad|mother|father|parent|sister|brother|sibling|'
    r'dog|cat|pet|puppy|kitten|'
    r'weekend|vacation|holiday|trip|travel|flight|hotel|'
    r'birthday|anniversary|wedding|funeral|'
    r"love|favorite|favourite|hate|can't stand|enjoy|"
    r'hobby|hobbies|fun|relax|'
    r'family|home|house|apartment|move|moved|moving|'
    r'sick|flu|covid|hospital|doctor|health|'
    r'school|college|university|graduated|'
    r'Lauren|Katie|Perrone|Raven Ridge|Loveland|Park City|Utah|'
    r'Colorado|Denver|Hattiesburg|Mississippi|NOLA|New Orleans|'
    r'San Diego|Bird Rock|La Jolla|'
    r"Pittsville|Maryland|Eastern Shore|New Jersey|Jersey|Jackson|"
    r"Asheville|North Carolina|Miami|Biscayne|"
    r'skiing|ski|snowboard|golf|tennis|hike|hiking|bike|run|running|'
    r'March Madness|bracket|NFL|NBA|MLB|football|basketball|baseball|Giants|Broncos|Steelers|Titans|Saints|'
    r'Civ|Starcraft|game|video game|board game|'
    r'dinner|lunch|brunch|breakfast|'
    r'garden|flower|farm|cooking|cook|bake|'
    r"how's|how are you|how have you been|doing well|doing good|"
    r'thanksgiving|christmas|easter|passover|eid|diwali'
    r')\b', re.IGNORECASE
)

def ts_to_s(ts):
    try:
        parts = [int(p) for p in ts.split(':')]
        if len(parts) == 3: return parts[0]*3600+parts[1]*60+parts[2]
        if len(parts) == 2: return parts[0]*60+parts[1]
        return 0
    except: return 0

def extract(rid, date, title):
    try:
        t = get_transcript(rid)
    except Exception as e:
        return {'rid': rid, 'date': date, 'title': title, 'error': str(e)}
    segs = t.get('transcript', []) or []
    n = len(segs)
    keep = set()
    for i in range(min(15, n)): keep.add(i)
    for i in range(max(0, n-15), n): keep.add(i)
    for i, s in enumerate(segs):
        if KW.search(s.get('text','')):
            keep.add(i)
    out = []
    for i in sorted(keep):
        s = segs[i]
        out.append({'i':i,'ts':s.get('timestamp',''),'spk':(s.get('speaker') or {}).get('display_name',''),'txt':s.get('text','').strip()})
    return {'rid':rid,'date':date,'title':title,'n_segments':n,'n_kept':len(out),'segments':out}

# Cap per person to control API volume (highest-signal small meetings)
CAP = 30  # per person, max new transcripts to pull
for person, meetings in by_person.items():
    # Prefer 2-person meetings, then 3-person, then 4-person
    meetings.sort(key=lambda m: (m['n_invitees'], -ts_to_s(m['start'][:10].replace('-','')[:6]+'00')))
    subset = meetings[:CAP]
    if not subset:
        print(f'{person}: no new meetings, skipping')
        continue
    out_path = f'{CACHE}/digest_{person}_v2.json'
    if os.path.exists(out_path):
        print(f'{person}: {out_path} exists, skipping')
        continue
    print(f'=== {person}: {len(subset)} new transcripts ===')
    results = []
    for m in subset:
        print(f'  {m["recording_id"]} ({m["start"][:10]} {m["title"][:50]})...', end=' ', flush=True)
        r = extract(m['recording_id'], m['start'][:10], m['title'])
        print(f'kept {r.get("n_kept","err")}/{r.get("n_segments","?")}')
        results.append(r)
        time.sleep(1.1)
    with open(out_path,'w',encoding='utf-8') as f:
        json.dump(results, f, indent=1)
    print(f'  wrote {out_path}')

print('Done.')
