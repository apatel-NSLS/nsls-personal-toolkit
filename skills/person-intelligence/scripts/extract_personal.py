"""Pull target transcripts, keyword-filter to personal-signal segments, save per-person digests."""
import sys, json, os, re, time
sys.path.insert(0, 'C:/Users/apate/.claude/.mcp-servers/fathom')
from server import get_transcript

CACHE = 'C:/Users/apate/.claude/.mcp-servers/fathom/cache'
os.makedirs(CACHE, exist_ok=True)

# Target recording_ids per SLT member (1:1s and small meetings from the 200-meeting index)
TARGETS = {
    'kevin': [
        (138983923, '2026-04-17', 'Kevin/Anish'),
        (137049637, '2026-04-10', 'Kevin/Anish'),
        (133524610, '2026-03-27', 'Kevin/Anish'),
        (127863780, '2026-03-06', 'Kevin/Anish'),
        (124094387, '2026-02-20', 'Kevin/Anish'),
        (116719061, '2026-01-23', 'Kevin/Anish'),
        (112458681, '2026-01-07', 'Kevin/AP'),
    ],
    'gary': [
        (138345808, '2026-04-15', 'AP/GT'),
        (137816547, '2026-04-14', 'GT/AP'),
        (133197264, '2026-03-26', 'AP/GT'),
        (131354116, '2026-03-19', 'GT/AP'),
        (126810570, '2026-03-03', 'Anish Gary weekly'),
        (125693460, '2026-02-26', 'GT/AP'),
        (119749306, '2026-02-04', 'GT/AP'),
        (115640115, '2026-01-20', 'Anish Gary weekly'),
        (112134493, '2026-01-06', 'Anish Gary weekly'),
        (109757005, '2025-12-18', 'AP/GT'),
    ],
    'adam': [
        (133222063, '2026-03-26', 'Anish / Adam'),
        (131013231, '2026-03-18', 'Anish / Adam Bi-Weekly'),
        (129827816, '2026-03-13', 'Anish / Adam LTV/ARPM'),
        (127163637, '2026-03-04', 'Anish / Adam'),
        (126925606, '2026-03-03', 'Anish / Adam Bi-Weekly'),
        (125738273, '2026-02-26', 'Anish / Adam'),
    ],
    'ashleigh': [
        (137009751, '2026-04-10', 'Anish / Ashleigh'),
        (135958653, '2026-04-07', 'Anish / Ashleigh'),
        (133540400, '2026-03-27', 'Anish / Ashleigh'),
        (125967310, '2026-02-27', 'Anish / Ashleigh'),
        (120964183, '2026-02-09', 'Ashleigh / Anish'),
        (117923768, '2026-01-28', 'Anish / Ashleigh Commission Prep'),
        (113073884, '2026-01-09', 'Anish / Ashleigh'),
        (112568155, '2026-01-07', 'Ashleigh/AP'),
        (110032783, '2025-12-19', 'Anish / Ashleigh'),
    ],
    'cory': [
        (132335753, '2026-03-24', 'Anish / Cory re: SARs'),
        (133456787, '2026-03-27', 'SARs meeting'),
        (109580275, '2025-12-17', 'Anish / Gary / Cory 2025/26 comp'),
        (110734084, '2025-12-23', 'CC/HD/AP'),
    ],
    'michael': [
        (139458249, '2026-04-20', 'Connect on LTV'),
        (114524280, '2026-01-15', 'Anish:MOB'),
        (112443952, '2026-01-07', 'MOB/AP'),
        (109483011, '2025-12-17', 'Talk 2026 marketing budget'),
    ],
}

# Personal-signal keywords — case-insensitive
KW = re.compile(
    r'\b('
    r'kids?|son|daughter|child|children|baby|babies|'
    r'wife|husband|spouse|partner|girlfriend|boyfriend|fiance|married|'
    r'mom|dad|mother|father|parent|sister|brother|sibling|'
    r'dog|cat|pet|puppy|kitten|'
    r'weekend|vacation|holiday|trip|travel|flight|hotel|'
    r'birthday|anniversary|wedding|funeral|'
    r"love|favorite|favourite|hate|can't stand|"
    r'hobby|hobbies|fun|relax|'
    r'family|home|house|apartment|move|moved|moving|'
    r'sick|flu|covid|hospital|doctor|health|'
    r'school|college|university|graduated|'
    r'Lauren|Katie|Perrone|Raven Ridge|Loveland|Park City|Utah|'
    r'Colorado|Denver|Hattiesburg|Mississippi|NOLA|New Orleans|'
    r'San Diego|Bird Rock|La Jolla|'
    r"Pittsville|Maryland|Eastern Shore|New Jersey|Jersey|"
    r"Asheville|North Carolina|"
    r'skiing|ski|snowboard|golf|tennis|hike|hiking|bike|'
    r'March Madness|bracket|NFL|NBA|MLB|football|basketball|baseball|'
    r'dinner|lunch|brunch|breakfast|'
    r"how's|how are you|how have you been|doing well|doing good"
    r')\b', re.IGNORECASE
)

def ts_to_s(ts):
    """Convert 'HH:MM:SS' or 'MM:SS' to seconds."""
    try:
        parts = ts.split(':')
        parts = [int(p) for p in parts]
        if len(parts) == 3:
            return parts[0]*3600 + parts[1]*60 + parts[2]
        if len(parts) == 2:
            return parts[0]*60 + parts[1]
        return 0
    except Exception:
        return 0

def extract(rid, date, title):
    try:
        t = get_transcript(rid)
    except Exception as e:
        return {'rid': rid, 'date': date, 'title': title, 'error': str(e)}
    segs = t.get('transcript', [])
    if not segs:
        return {'rid': rid, 'date': date, 'title': title, 'n_segments': 0, 'matches': []}
    n = len(segs)
    last_ts = segs[-1].get('timestamp', '00:00')
    last_s = ts_to_s(last_ts)
    # Keep: first 20 segments, last 20 segments, and any keyword-matching segment
    keep = set()
    for i in range(min(20, n)):
        keep.add(i)
    for i in range(max(0, n-20), n):
        keep.add(i)
    for i, s in enumerate(segs):
        if KW.search(s.get('text', '')):
            keep.add(i)
    out = []
    for i in sorted(keep):
        s = segs[i]
        out.append({
            'i': i,
            'ts': s.get('timestamp',''),
            'spk': (s.get('speaker') or {}).get('display_name',''),
            'txt': s.get('text','').strip(),
        })
    return {
        'rid': rid, 'date': date, 'title': title,
        'n_segments': n, 'duration_s': last_s,
        'n_kept': len(out),
        'segments': out,
    }

def main():
    for person, targets in TARGETS.items():
        path = f'{CACHE}/digest_{person}.json'
        if os.path.exists(path):
            print(f'{person}: digest exists, skipping')
            continue
        print(f'=== {person} ({len(targets)} transcripts) ===')
        results = []
        for rid, date, title in targets:
            print(f'  fetching {rid} ({date} {title})...', end=' ', flush=True)
            r = extract(rid, date, title)
            print(f"kept {r.get('n_kept','?')}/{r.get('n_segments','?')}")
            results.append(r)
            time.sleep(1.2)  # stay under 60/min rate limit
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=1)
        print(f'  wrote {path}')

if __name__ == '__main__':
    main()
