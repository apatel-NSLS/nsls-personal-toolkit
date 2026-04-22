"""Extract speaker-attributed name mentions for each SLT member.
Finds when each SLT member themselves mentions family names or personal details.
"""
import json, os, re, glob

CACHE = 'C:/Users/apate/.claude/.mcp-servers/fathom/cache'

SLT = {
    'kevin':    'Kevin Prentiss',
    'gary':     'Gary Tuerack',
    'adam':     'Adam Stone',
    'ashleigh': 'Ashleigh Smith',
    'cory':     'Cory Capoccia',
    'michael':  "Michael O'Brien",
}

# Patterns: signals of personal content that SHOULD have a name nearby
FAMILY_WORDS = r"\b(wife|husband|son|daughter|kid|kids|child|mom|dad|mother|father|brother|sister|dog|cat|pet|girlfriend|boyfriend|fiance|fiancee|ex-wife|ex-husband|partner|parents|in-law|niece|nephew|cousin|baby)\b"
POSSESSIVE = r"\bmy\s+"
CAP_NAME = r"\b[A-Z][a-z]{2,}\b"  # likely first name

for person, speaker_name in SLT.items():
    # Combine v1 + v2
    segments = []
    for path in [f'{CACHE}/digest_{person}.json', f'{CACHE}/digest_{person}_v2.json']:
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        for meeting in data:
            rid = meeting.get('rid')
            date = meeting.get('date','?')
            for seg in meeting.get('segments', []):
                segments.append({
                    'rid': rid, 'date': date,
                    'spk': seg.get('spk',''), 'ts': seg.get('ts',''), 'txt': seg.get('txt','')
                })

    print(f'\n{"="*60}\n{person.upper()} — {speaker_name}')
    print(f'{"="*60}')
    print(f'Total segments: {len(segments)}')

    # Focus on segments where THIS person is speaker
    own = [s for s in segments if s['spk'] == speaker_name]
    print(f'Own-speaker segments: {len(own)}')

    # Find segments with family words
    family_hits = [s for s in own if re.search(FAMILY_WORDS, s['txt'], re.I)]
    print(f'Family-word mentions: {len(family_hits)}')

    # Get unique names per person (capitalized words that aren't common)
    STOP = {
        'Yeah','Yes','No','Okay','OK','Bye','Hi','Hello','Anish','Kevin','Gary','Adam','Ashleigh','Cory',
        'Michael','Heather','Jordan','Ann','Ashley','Claude','Fathom','Slack','Zoom','NSLS','SLT','SARS',
        'SARs','CS','PD','LTV','ARPM','AOV','The','This','That','But','And','And,','So','Or','For','With',
        'You','We','They','She','He','It','I','Just','Like','Then','Now','Really','Good','Great','Fine',
        'Sure','Actually','Maybe','Thanks','Thank','Ashleigh','January','February','March','April','May',
        'June','July','August','September','October','November','December','Monday','Tuesday','Wednesday',
        'Thursday','Friday','Saturday','Sunday','Christmas','Easter','Thanksgiving','NASPA','ACPA','HR',
        'CEO','CFO','COO','CPO','CTO','VP','AP','MOB','GT','CC','AS','HD','AI','BI','LLC','LLP','IRS',
        'NJ','NY','CA','CO','MD','MS','FL','UT','NC','US','USA','Society','Ignite','Carta','Rippling','Ramp',
        'DocuSign','Trigram','Feather','Hex','PostHog','Airtable','HubSpot','Manning','Tomlin','Stack','Burroughs',
        'Titans','Giants','Falcon','Broncos','Steelers','Saints','Falcons','Eagles','Meredith','Tate','Kim',
        'Tatiana','Erin','Valerie','Irina','Ashley','Sandra','Danielle','Dominic','Nicole','Marissa','Kimberly',
        'Jordan','Jenna','Heather','William','Margaret','Stephanie','Mike','Joseph','Joe','Jim','Derald','Cory',
        'Corey','Chelsea','Rachel','Boris','Devin','Royce','Pascal','Jonathan','Noah','Andrew','Isaia','Isaiah',
        'Josh','Julia','David','Lee','Katie','Lauren','Red','Lila','Karina','Colleen','Jana','Daryl','Tyler',
        'Brown','Solidline','Lodestone','Gary','Kevin','Adam','Ashleigh','Cory','Michael','Foundation',
        'Endeavor','Shop','Summit','Spring','Fall','Summer','Winter','Board','Fathoms','Paid','Based','Beyond',
        'Bucks','Come','Content','Covered','Delta','Drive','Emerald','Final','Founder','Fresh','Front','Ground',
        'Healing','Huge','Indian','Legit','Light','Lily','Main','Middle','Name','Network','New','Next','Night',
        'Nothing','Overall','Peter','President','Past','Per','Plan','Plus','Previously','Prior','Private','Pro',
        'Quick','Race','Read','Reality','Regional','Return','Revenue','Right','School','Scrum','Seems','Small',
        'Something','Source','Speak','Standard','Start','Status','Stay','Still','Stop','Story','Strong','Super',
        'Sweet','Take','Taking','Team','Technical','Technology','Tell','Ten','Things','Think','Three','Time',
        'Today','Together','Tom','Top','Total','Towards','Training','Trying','Two','Tyler','Uniform','Updates',
        'Value','View','Wait','Walmart','Way','Week','Well','When','Where','Which','While','Who','Why','Will',
        'Words','Work','World','Worried','Would','Year','Years','You','Your','Yourself','Seahawks','Mario',
        'Civ','StarCraft','Walmart','United','States','University','Jersey','Jackson','Asheville','Colorado',
        'Denver','Utah','Maryland','Mississippi','Hattiesburg','Nashville','Orleans','Pittsville','Diego',
        'Taipei','Japan','Bali','Indonesia','Malaysia','Orlando','Legoland','Legoland','Waikiki','Martin','John',
        'Dutch','Caribbean','Superdome','Roosevelt'
    }

    print(f'\n--- family-word segments (self-spoken) ---')
    for s in family_hits[:50]:  # cap display
        # find capitalized names near family words
        txt = s['txt']
        names = [w for w in re.findall(CAP_NAME, txt) if w not in STOP]
        marker = f' [NAMES: {sorted(set(names))}]' if names else ''
        print(f'  [{s["date"]} @ {s["ts"]}] {txt[:200]}{marker}')

    # Summary of novel names surfaced per person
    all_names = []
    for s in family_hits:
        for n in re.findall(CAP_NAME, s['txt']):
            if n not in STOP:
                all_names.append(n)
    from collections import Counter
    common = Counter(all_names).most_common(20)
    print(f'\n--- candidate names (top 20, speaker-attributed family context) ---')
    for name, count in common:
        print(f'  {name}: {count}')

