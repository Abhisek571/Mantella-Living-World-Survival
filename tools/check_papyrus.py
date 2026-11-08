"""Static checks of the Survival scripts, no game or compiler needed. Run from the project root:
    py -3 tools/check_papyrus.py
Checks:
  handlers     every RegisterForModEvent handler exists, is an Event, and takes what the sender pushes (Mantella's own
               source when it is installed, the SKSE ModCallbackEvent for MLWS_Ate); every engine event matches the
               vanilla declaration; overrides of MLWS_Job keep its signatures; MLWS_Native matches the SKSE plugin;
               stubs match the real scripts they stand for
  keys         StorageUtil keys: every read has a writer (here or in a named module), every write is read, one value
               type per key; JsonUtil settings keys exist in the settings file with that type; npc file keys lowercase
  optional     every GetFormFromFile on a plugin other than the base game masters runs after a check that it is loaded
  actions      every action with requires_response has an advanced and a legacy handler, and each sends
               Mantella_ActionResponseCompleted with its own identifier on every path, before anything that could wait
  polling      no update or wait loop under the design minimum (the interval the script's own docs give)
  properties   every Auto property of a quest script is filled in the plugin YAML
"""
import glob, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODING = os.path.dirname(ROOT)
SRC = os.path.join(ROOT, 'Source', 'Scripts')
STUBS = os.path.join(ROOT, 'build', 'stubs')
_paths = json.load(open(os.path.join(CODING, 'Mantella-Living-World-Hub', 'tools', 'local-paths.json'))) \
    if os.path.isfile(os.path.join(CODING, 'Mantella-Living-World-Hub', 'tools', 'local-paths.json')) else {}
_mo2 = os.environ.get('MLW_MO2') or _paths.get('mo2', '')
MODS = os.path.join(_mo2, 'mods') if _mo2 else ''
VANILLA = os.path.join(_paths.get('game', ''), 'Data', 'Source', 'Scripts')
REAL = {  # stub -> the real script it stands for
    'MLW_Hub': os.path.join(CODING, 'Mantella-Living-World-Hub', 'Source', 'Scripts', 'MLW_Hub.psc'),
    'MLW_Pace': os.path.join(CODING, 'Mantella-Living-World-Hub', 'Source', 'Scripts', 'MLW_Pace.psc'),
    'MantellaConversation': os.path.join(MODS, '[NoDelete] Mantella - Bring NPCs to Life with AI', 'Scripts', 'Source', 'MantellaConversation.psc'),
    'SKSE_HTTP': os.path.join(MODS, '[NoDelete] Mantella - Bring NPCs to Life with AI', 'Scripts', 'Source', 'SKSE_HTTP.psc'),
    'SurvivalModeImprovedApi': os.path.join(MODS, '[NoDelete] Survival Mode Improved - SKSE', 'Source', 'Scripts', 'SurvivalModeImprovedApi.psc'),
}
BASE_MASTERS = {'skyrim.esm', 'update.esm'}
DESIGN_POLL = 30.0  # the fallback minimum; a script's own "every N real seconds" wins when it states one
fails = 0
results = []


def check(group, name, ok, detail=''):
    global fails
    results.append((group, name, ok, detail))
    fails += not ok


# ---------------------------------------------------------------------------------------------------------------------
# A small Papyrus reader
# ---------------------------------------------------------------------------------------------------------------------

def strip(line):
    """The line without its comment (a ; outside a string)."""
    out, q = [], False
    for c in line:
        if c == '"':
            q = not q
        if c == ';' and not q:
            break
        out.append(c)
    return ''.join(out).rstrip()


FUNC = re.compile(r'^\s*(?:(\w+(?:\[\])?)\s+)?(Function|Event)\s+(\w+)\s*\(([^)]*)\)(.*)$', re.I)


def params(text):
    out = []
    for p in [p.strip() for p in text.split(',') if p.strip()]:
        m = re.match(r'(\w+(?:\[\])?)\s+(\w+)(\s*=\s*(.+))?', p)
        if m:
            out.append((m.group(1).lower(), m.group(2), m.group(4)))
    return out


class Script:
    def __init__(self, path):
        self.path = path
        self.file = os.path.basename(path)
        raw = open(path, encoding='utf-8', errors='replace').read()
        raw = re.sub(r'\{[^}]*\}', lambda m: '\n' * m.group(0).count('\n'), raw)  # doc comments
        raw = re.sub(r';/.*?/;', lambda m: '\n' * m.group(0).count('\n'), raw, flags=re.S)
        self.lines = [strip(l) for l in raw.split('\n')]
        # join "\" continuations onto the first line, keeping line numbers
        for i in range(len(self.lines) - 1):
            while self.lines[i].endswith('\\'):
                self.lines[i] = self.lines[i][:-1] + ' ' + self.lines[i + 1].strip()
                self.lines[i + 1] = ''
        head = re.match(r'\s*Scriptname\s+(\w+)(?:\s+extends\s+(\w+))?', self.lines[0] if self.lines else '', re.I)
        self.name = head.group(1) if head else self.file[:-4]
        self.extends = head.group(2) if head and head.group(2) else None
        self.props, self.funcs = {}, {}
        cur = None
        for i, l in enumerate(self.lines, 1):
            m = re.match(r'^\s*(\w+(?:\[\])?)\s+Property\s+(\w+)(?:\s*=\s*(.+?))?\s+(AutoReadOnly|Auto)\b', l, re.I)
            if m and cur is None:
                val = m.group(3)
                if val and val.startswith('"'):
                    val = val.strip('"')
                elif val:
                    try:
                        val = float(val)
                    except ValueError:
                        pass
                self.props[m.group(2)] = (m.group(1).lower(), val, m.group(4).lower(), i)
                continue
            m = FUNC.match(l)
            if m and cur is None:
                cur = {'ret': (m.group(1) or '').lower(), 'kind': m.group(2).lower(), 'name': m.group(3),
                       'params': params(m.group(4)), 'flags': m.group(5).lower(), 'start': i, 'body': []}
                if 'native' in cur['flags']:
                    self.funcs[cur['name'].lower()] = cur
                    cur = None
                continue
            if cur is not None:
                if re.match(r'^\s*End(Function|Event)\b', l, re.I):
                    self.funcs[cur['name'].lower()] = cur
                    cur = None
                else:
                    cur['body'].append((i, l))

    def resolve(self, expr, scripts=None):
        """A string expression from literals and AutoReadOnly properties; unknown parts become '*'."""
        out = []
        for part in [p.strip() for p in split_plus(expr)]:
            if part.startswith('"') and part.endswith('"'):
                out.append(part[1:-1])
            elif part in self.props and isinstance(self.props[part][1], str):
                out.append(self.props[part][1])
            elif re.match(r'^\w+\.\w+\(\)$', part) and scripts:
                s, f = part[:-2].split('.')
                fn = scripts.get(s.lower(), {}).funcs.get(f.lower()) if s.lower() in scripts else None
                ret = next((re.search(r'Return\s+"([^"]*)"', l) for _, l in (fn['body'] if fn else [])), None)
                out.append(ret.group(1) if ret else '*')
            else:
                out.append('*')
        return ''.join(out)


def split_plus(expr):
    parts, depth, q, cur = [], 0, False, ''
    for c in expr:
        if c == '"':
            q = not q
        if not q and c in '([':
            depth += 1
        if not q and c in ')]':
            depth -= 1
        if c == '+' and not q and depth == 0:
            parts.append(cur)
            cur = ''
        else:
            cur += c
    parts.append(cur)
    return parts


def call_args(text, start):
    """Arguments of the call whose '(' is at text[start]."""
    depth, q, cur, args = 0, False, '', []
    for c in text[start:]:
        if c == '"':
            q = not q
        if not q and c == '(':
            depth += 1
            if depth == 1:
                continue
        if not q and c == ')':
            depth -= 1
            if depth == 0:
                args.append(cur.strip())
                return [a for a in args if a]
        if c == ',' and depth == 1 and not q:
            args.append(cur.strip())
            cur = ''
        else:
            cur += c
    return args


def calls(script, pattern):
    """(function, line number, name match, args) for each call matching pattern (a regex ending before '(')."""
    rx = re.compile(pattern + r'\s*\(', re.I)
    for fn in script.funcs.values():
        for i, l in fn['body']:
            for m in rx.finditer(l):
                yield fn, i, m, call_args(l, m.end() - 1)


scripts = {s.name.lower(): s for s in (Script(p) for p in sorted(glob.glob(os.path.join(SRC, '*.psc'))))}
stubs = {s.name.lower(): s for s in (Script(p) for p in sorted(glob.glob(os.path.join(STUBS, '*.psc'))))}


def vanilla(name):
    p = os.path.join(VANILLA, name + '.psc')
    return Script(p) if os.path.isfile(p) else None


# ---------------------------------------------------------------------------------------------------------------------
# handlers
# ---------------------------------------------------------------------------------------------------------------------

def pushes_after(path, create_rx):
    """The Push types after a ModEvent.Create matching create_rx, up to its Send, in a sender's source."""
    if not os.path.isfile(path):
        return None
    lines = [strip(l) for l in open(path, encoding='utf-8', errors='replace')]
    for i, l in enumerate(lines):
        if re.search(create_rx, l):
            types = []
            for l2 in lines[i + 1:i + 12]:
                m = re.search(r'ModEvent\.Push(\w+)\s*\(', l2)
                if m:
                    types.append(m.group(1).lower())
                if 'ModEvent.Send' in l2:
                    return types
    return None


MANTELLA = REAL['MantellaConversation']
cpp = open(os.path.join(ROOT, 'plugin', 'src', 'Survival.cpp'), encoding='utf-8').read()
SENDERS = [  # (event name or prefix, is prefix, pushed types, where it comes from)
    ('MantellaConversation_NPC_Added', False, pushes_after(MANTELLA, r'ModEvent\.Create\(EventInterface\.EVENT_CONVERSATION_NPC_ADDED\)') or ['form'], 'MantellaConversation.psc SendActorAddedEvents'),
    ('MantellaConversation_Advanced_Action_', True, pushes_after(MANTELLA, r'EVENT_ADVANCED_ACTIONS_PREFIX \+ actionIdentifier') or ['form', 'form', 'int'], 'MantellaConversation.psc RaiseActionEvent'),
    ('MantellaConversation_Action_', True, pushes_after(MANTELLA, r'EVENT_ACTIONS_PREFIX \+ actionIdentifier') or ['form'], 'MantellaConversation.psc RaiseActionEvent'),
    ('MLW_ReportRequest', False, pushes_after(os.path.join(CODING, 'Mantella-Living-World-Hub', 'Source', 'Scripts', 'MLW_Hub.psc'), r'ModEvent\.Create\("MLW_ReportRequest"\)'), 'MLW_Hub.psc WriteReport'),
]
if re.search(r'ModCallbackEvent\s+event\{\s*"MLWS_Ate"', cpp):
    SENDERS.append(('MLWS_Ate', False, ['string', 'string', 'float', 'form'], 'Survival.cpp OnEquip (SKSE ModCallbackEvent)'))
# Vampire Feed Proxy (optional mod): akFeeder.SendModEvent("NpcVampireFeed", <target FormID>, <lethal>), an SKSE mod event
VFP = os.path.join(MODS, '[NoDelete] Vampire Feed Proxy', 'Scripts', 'Source', 'VampireFeedProxy.psc')
if not os.path.isfile(VFP) or re.search(r'\.SendModEvent\("NpcVampireFeed"', open(VFP, encoding='utf-8').read()):
    SENDERS.append(('NpcVampireFeed', False, ['string', 'string', 'float', 'form'], 'VampireFeedProxy.psc NpcVampireFeed (SendModEvent)'))
check('handlers', 'senders found in Mantella and Hub sources', all(t is not None for _, _, t, _ in SENDERS),
      [n for n, _, t, _ in SENDERS if t is None])

registered = {}  # script -> set of handler names
for s in scripts.values():
    for fn, i, m, args in calls(s, r'\bRegisterForModEvent'):
        event, handler = s.resolve(args[0], scripts), args[1].strip('"')
        registered.setdefault(s.name, set()).add(handler.lower())
        sender = next((x for x in SENDERS if (event.startswith(x[0]) if x[1] else event == x[0])), None)
        h = s.funcs.get(handler.lower())
        where = f'{s.file}:{i} {event} -> {handler}'
        check('handlers', f'{where}: sender known', sender is not None)
        check('handlers', f'{where}: handler exists as an Event', bool(h) and h['kind'] == 'event')
        if sender and h:
            got = [t for t, _, _ in h['params']]
            want = ['form' if t == 'form' else t for t in sender[2]]
            ok = len(got) == len(want) and all(g == w or (w == 'form' and g in ('form', 'actor', 'objectreference', 'quest')) for g, w in zip(got, want))
            check('handlers', f'{where}: takes {want} ({sender[3]})', ok, got)

# engine events against the vanilla declarations
for s in scripts.values():
    chain, base = [], s.extends
    while base:
        v = scripts.get(base.lower()) or vanilla(base)
        if not v:
            break
        chain.append(v)
        base = v.extends
    for fn in s.funcs.values():
        if fn['kind'] != 'event' or fn['name'].lower() in registered.get(s.name, set()):
            continue
        decl = next((c.funcs[fn['name'].lower()] for c in chain if fn['name'].lower() in c.funcs), None)
        if decl is None and fn['name'].lower() == 'oninit':  # every script object has it; no .psc declares it
            decl = {'params': []}
        check('handlers', f"{s.file}:{fn['start']} Event {fn['name']} is an engine event of {s.extends}", decl is not None)
        if decl:
            check('handlers', f"{s.file}: Event {fn['name']} signature matches {decl['params']}",
                  [t for t, _, _ in fn['params']] == [t for t, _, _ in decl['params']])

# overrides of MLWS_Job keep its signatures
job = scripts.get('mlws_job')
for s in scripts.values():
    if s.extends and s.extends.lower() == 'mlws_job':
        for name, fn in s.funcs.items():
            if name in job.funcs:
                j = job.funcs[name]
                check('handlers', f"{s.file}: {fn['name']} overrides MLWS_Job with the same signature",
                      [t for t, _, _ in fn['params']] == [t for t, _, _ in j['params']] and fn['ret'] == j['ret'])

# natives against the SKSE plugin
CPP_TYPES = {'RE::Actor*': 'actor', 'float': 'float', 'bool': 'bool', 'RE::TESForm*': 'form', 'std::int32_t': 'int',
             'RE::BSFixedString': 'string', 'std::vector<RE::Actor*>': 'actor[]'}
native = scripts['mlws_native']
registered_cpp = dict(re.findall(r'RegisterFunction\("(\w+)",\s*"MLWS_Native",\s*(\w+)\)', cpp))
for name, fn in native.funcs.items():
    cname = next((k for k in registered_cpp if k.lower() == name), None)
    check('handlers', f"MLWS_Native.{fn['name']} registered by the SKSE plugin", cname is not None)
    if not cname:
        continue
    m = re.search(r'\n\s*([\w:<>*\s]+?)\s+' + registered_cpp[cname] + r'\(RE::StaticFunctionTag\*,?\s*([^)]*)\)', cpp)
    if not m:
        check('handlers', f'{cname}: C++ definition found', False)
        continue
    ret = CPP_TYPES.get(m.group(1).strip(), '?')
    cargs = [CPP_TYPES.get(re.sub(r'\s+a_\w+$', '', a.strip()), '?') for a in m.group(2).split(',') if a.strip()]
    check('handlers', f'{cname}: return and arguments match ({ret} {cargs})',
          ret == fn['ret'] and cargs == [t for t, _, _ in fn['params']], (fn['ret'], [t for t, _, _ in fn['params']]))
for k in registered_cpp:
    check('handlers', f'{k}: declared in MLWS_Native.psc', k.lower() in native.funcs)

# stubs against the real scripts
for name, stub in stubs.items():
    real_path = REAL.get(stub.name)
    if not real_path or not os.path.isfile(real_path):
        check('handlers', f'stub {stub.name}: real script found to compare', False, real_path)
        continue
    real = Script(real_path)
    for fname, fn in stub.funcs.items():
        r = real.funcs.get(fname)
        ok = r is not None and [t for t, _, _ in r['params']] == [t for t, _, _ in fn['params']] and r['ret'] == fn['ret'] \
            and ('global' in r['flags']) == ('global' in fn['flags'])
        check('handlers', f"stub {stub.name}.{fn['name']} matches the real script", ok, r and (r['ret'], r['params'], r['flags']))

# every call into another script names a function it has, with an argument count it takes
everything = {**{k: v for k, v in stubs.items()}, **scripts}
for s in scripts.values():
    for fn, i, m, args in calls(s, r'\b(MLWS_\w+|MLW_Pace|MLW_Hub|SKSE_HTTP|SurvivalModeImprovedApi)\.(\w+)'):
        target = everything.get(m.group(1).lower())
        f = target.funcs.get(m.group(2).lower()) if target else None
        need = sum(1 for _, _, d in f['params'] if d is None) if f else 0
        check('handlers', f'{s.file}:{i} {m.group(1)}.{m.group(2)}({len(args)} args)',
              f is not None and need <= len(args) <= len(f['params']))

# ---------------------------------------------------------------------------------------------------------------------
# keys
# ---------------------------------------------------------------------------------------------------------------------

SU = re.compile(r'StorageUtil\.(Set|Get|Has|Unset|Adjust)(Int|Float|String|Form)(Value)', re.I)
SUL = re.compile(r'StorageUtil\.(Int|Float|String|Form)List(Add|Get|Set|Count|Find|Clear|RemoveAt|Has|Insert)', re.I)
EXTERNAL = {  # keys this module reads that another module writes, with the file that writes them
    'mlw_isclose': os.path.join(CODING, 'Mantella-Living-World-Arousal', 'Source', 'Scripts', 'MantellaOSLA_Main.psc'),
    'mrb_close': os.path.join(CODING, 'Mantella-Living-World-Relationships', 'Source', 'Scripts', 'MRB_MARAS.psc'),
}
WRITE_ONLY = {'mlws_warmfrom': 'the stage warmed up from; no fact uses it yet'}
keys = {}  # key pattern -> {'w': [...], 'r': [...], 'types': set()}
for s in scripts.values():
    for fn in s.funcs.values():
        for i, l in fn['body']:
            for rx, kind in ((SU, 'value'), (SUL, 'list')):
                for m in rx.finditer(l):
                    args = call_args(l, l.index('(', m.end() - 1))
                    if len(args) < 2:
                        continue
                    if kind == 'value':
                        op, typ = m.group(1).lower(), m.group(2).lower()
                    else:
                        typ, op = m.group(1).lower() + '[]', m.group(2).lower()
                    owner = 'none' if args[0].lower() == 'none' else 'actor'
                    key = s.resolve(args[1], scripts).lower()
                    if key == '*':
                        # the key is a parameter: resolve from each caller's literal (the facts lists, MLWS_Util.DaysSince)
                        continue
                    k = keys.setdefault(key, {'w': [], 'r': [], 'types': set(), 'owners': set()})
                    write = op in ('set', 'add', 'adjust', 'insert', 'unset', 'clear', 'removeat')
                    k['w' if write else 'r'].append(f'{s.file}:{i}')
                    if op not in ('unset', 'clear', 'has', 'count', 'removeat'):
                        k['types'].add(typ)
                    k['owners'].add(owner)
# keys passed as arguments: DaysSince(actor, "<key>", now), and the IsDrunk list
for s in scripts.values():
    for fn, i, m, args in calls(s, r'MLWS_Util\.DaysSince'):
        key = s.resolve(args[1], scripts).lower()
        keys.setdefault(key, {'w': [], 'r': [], 'types': set(), 'owners': set()})['r'].append(f'{s.file}:{i}')
        keys[key]['types'].add('float')
for key, k in sorted(keys.items()):
    if key.endswith('*'):
        continue
    if not k['w']:
        ext = EXTERNAL.get(key)
        ok = bool(ext) and os.path.isfile(ext) and re.search(re.escape(key), open(ext, encoding='utf-8').read(), re.I) is not None
        check('keys', f'StorageUtil "{key}": read here, written by {os.path.basename(ext) if ext else "nobody"}', ok, k['r'])
    elif key in WRITE_ONLY:
        check('keys', f'StorageUtil "{key}": written, never read (known: {WRITE_ONLY[key]})', True)
    else:
        check('keys', f'StorageUtil "{key}": written and read', bool(k['r']), f"written at {k['w']}, never read")
    check('keys', f'StorageUtil "{key}": one value type', len({t.rstrip('[]') for t in k['types']}) <= 1, sorted(k['types']))
    check('keys', f'StorageUtil "{key}": one owner kind', len(k['owners']) <= 1, sorted(k['owners']))

settings = json.load(open(os.path.join(ROOT, 'SKSE/Plugins/StorageUtilData/MantellaLivingWorld/survival_settings.json'), encoding='utf-8'))
for s in scripts.values():
    for fn, i, m, args in calls(s, r'JsonUtil\.(\w+)'):
        op = m.group(1)
        if len(args) < 2:
            continue
        file = s.resolve(args[0], scripts)
        key = s.resolve(args[1], scripts)
        if key == '*':
            continue  # the key is a parameter; the callers' literals are checked below
        if file == 'MantellaLivingWorld/survival_settings.json' or 'SETTINGS()' in args[0]:
            typ = {'GetIntValue': 'int', 'GetFloatValue': 'float', 'StringListHas': 'stringList'}.get(op)
            check('keys', f'{s.file}:{i} settings "{key}" exists as {typ}', typ is not None and key in settings.get(typ, {}))
        elif op.startswith(('Set', 'Unset')) and key != '*':
            check('keys', f'{s.file}:{i} npc file key "{key}" is lowercase (JsonUtil lowercases lookups)', key == key.lower())
for s in scripts.values():
    for fn, i, m, args in calls(s, r'MLWS_Util\.Setting(Int|Float)'):
        key = s.resolve(args[0], scripts)
        check('keys', f'{s.file}:{i} setting "{key}" exists as {m.group(1).lower()}', key in settings.get(m.group(1).lower(), {}))
    for fn in s.funcs.values():  # fact names and prefixes, wherever they are written (some pass through a parameter)
        for i, l in fn['body']:
            for name in re.findall(r'"(fact_\w*)"', l):
                check('keys', f'{s.file}:{i} fact "{name}" is lowercase and fact_surv_', name == name.lower() and name.startswith('fact_surv_'))

# ---------------------------------------------------------------------------------------------------------------------
# optional plugins
# ---------------------------------------------------------------------------------------------------------------------

HELPERS = {'SURVIVAL_ESL()': 'ccqdrsse001-survivalmode.esl', 'HUB_PLUGIN()': 'mantella living world - integration hub.esp',
           'SMI_ESP()': 'survivalmodeimproved.esp'}
GUARDS = {'ccqdrsse001-survivalmode.esl': [r'PluginLoaded\((MLWS_Util\.)?SURVIVAL_ESL\(\)\)', r'PluginLoaded\(esl\)', r'SurvivalOn\(\)'],
          'mantella living world - integration hub.esp': [r'HubLoaded\(\)'],
          'survivalmodeimproved.esp': [r'SmiLoaded\(\)'],
          'dawnguard.esm': [r'PluginLoaded\("Dawnguard\.esm"\)'],
          'better vampires.esp': [r'PluginLoaded\("Better Vampires\.esp"\)'],
          'mantella.esp': [r'PluginLoaded\("Mantella\.esp"\)']}
for s in scripts.values():
    for fn, i, m, args in calls(s, r'Game\.GetFormFromFile'):
        plugin = args[1]
        name = plugin.strip('"').lower() if plugin.startswith('"') else next((v for k, v in HELPERS.items() if k in plugin), None)
        if name is None:
            # a local variable: find what it was set to in this function
            var = plugin.strip()
            setto = next((re.search(r'=\s*(.+)$', l).group(1) for _, l in fn['body'] if re.match(r'\s*string\s+' + var + r'\s*=', l, re.I)), '')
            name = next((v for k, v in HELPERS.items() if k in setto), setto.strip('"').lower())
        if name in BASE_MASTERS:
            continue
        before = [l for j, l in fn['body'] if j < i]
        guarded = any(re.search(g, l) for g in GUARDS.get(name, []) for l in before)
        check('optional', f'{s.file}:{i} GetFormFromFile on {name} runs after a loaded check', guarded)

# ---------------------------------------------------------------------------------------------------------------------
# actions
# ---------------------------------------------------------------------------------------------------------------------

util = scripts['mlws_util']
done = util.funcs.get('actiondone')
check('actions', 'MLWS_Util.ActionDone sends Mantella_ActionResponseCompleted with the identifier',
      bool(done) and any('ModEvent.Create("Mantella_ActionResponseCompleted")' in l for _, l in done['body'])
      and any(re.search(r'ModEvent\.PushString\(handle,\s*asIdentifier\)', l) for _, l in done['body']))
iface = os.path.join(os.path.dirname(MANTELLA), 'MantellaInterface.psc')
if os.path.isfile(iface):
    check('actions', "Mantella listens for that event name (MantellaInterface.psc)",
          'EVENT_ACTION_RESPONSE_COMPLETED = "Mantella_ActionResponseCompleted"' in open(iface, encoding='utf-8').read())
for path in sorted(glob.glob(os.path.join(ROOT, 'SKSE/Plugins/MantellaSoftware/data/actions/*.json'))):
    a = json.load(open(path, encoding='utf-8'))
    ident = a['identifier']
    for prefix in ('MantellaConversation_Advanced_Action_', 'MantellaConversation_Action_'):
        found = [(s, fn, i, args) for s in scripts.values() for fn, i, m, args in calls(s, r'\bRegisterForModEvent')
                 if s.resolve(args[0], scripts) == prefix + ident]
        check('actions', f'{ident}: a {prefix} handler is registered', bool(found))
        for s, fn, i, args in found:
            h = s.funcs.get(args[1].strip('"').lower())
            body = h['body'] if h else []
            dones = [(j, l) for j, l in body if re.search(r'MLWS_Util\.ActionDone\(', l)]
            idents = {s.resolve(call_args(l, l.index('(', l.index('ActionDone')))[0], scripts) for _, l in dones}
            top = [l for _, l in body]
            indent = lambda l: len(l) - len(l.lstrip('\t'))
            first_level = all(indent(l) == 1 for _, l in dones)
            early = any(re.match(r'\s*Return\b', l, re.I) for j, l in body if dones and j < dones[0][0])
            check('actions', f"{ident}: {h['name'] if h else '?'} sends the completion with its identifier on every path",
                  a.get('requires_response') is not True or (bool(dones) and idents == {ident} and first_level and not early),
                  f'{idents} top-level={first_level} early return={early}')
            waits = [j for j, l in body if re.search(r'RequestContinueConversation|Utility\.Wait|Debug\.MessageBox|\.Show\(', l)]
            check('actions', f"{ident}: {h['name'] if h else '?'} completes before anything that waits",
                  not waits or (dones and dones[0][0] < waits[0]))
        if prefix.startswith('MantellaConversation_Advanced'):
            for s, fn, i, args in found:
                h = s.funcs.get(args[1].strip('"').lower())
                for _, l in h['body'] if h else []:
                    for pm in re.finditer(r'SKSE_HTTP\.get\w+\(\w+,\s*"(\w+)",\s*"([^"]*)"', l):
                        p = a.get('parameters', {}).get(pm.group(1))
                        check('actions', f'{ident}: argument "{pm.group(1)}" is declared in the action file', p is not None)
                        if p and 'enum' in p:
                            check('actions', f'{ident}: default "{pm.group(2)}" is one of {p["enum"]}', pm.group(2) in p['enum'])

# ---------------------------------------------------------------------------------------------------------------------
# polling
# ---------------------------------------------------------------------------------------------------------------------

for s in scripts.values():
    doc = open(s.path, encoding='utf-8').read()
    stated = re.search(r'every (\d+(?:\.\d+)?) real seconds', doc)
    minimum = float(stated.group(1)) if stated else DESIGN_POLL
    for fn, i, m, args in calls(s, r'\b(RegisterForSingleUpdate|RegisterForUpdate|RegisterForSingleUpdateGameTime|RegisterForUpdateGameTime)'):
        v = args[0]
        val = s.props.get(v, (None, None))[1] if v in s.props else (float(v) if re.match(r'^[\d.]+$', v) else None)
        if 'GameTime' in m.group(1):
            check('polling', f'{s.file}:{i} {m.group(1)}({v}) game-time update at least a quarter hour', val is not None and val >= 0.25)
        else:
            check('polling', f'{s.file}:{i} {m.group(1)}({v} = {val}) at least {minimum:g} s', val is not None and val >= minimum)
            check('polling', f'{s.file}:{i} single updates only (no repeating RegisterForUpdate)', m.group(1) == 'RegisterForSingleUpdate')
        if stated:
            check('polling', f'{s.file}: the interval the docs give ({minimum:g} s) is the one used', val == minimum)
    for fn in s.funcs.values():
        depth = 0
        for i, l in fn['body']:
            if re.match(r'\s*While\b', l, re.I):
                depth += 1
            elif re.match(r'\s*EndWhile\b', l, re.I):
                depth -= 1
            elif depth and re.search(r'Utility\.Wait', l):
                check('polling', f'{s.file}:{i} no Utility.Wait loop', False, l.strip())

# ---------------------------------------------------------------------------------------------------------------------
# properties
# ---------------------------------------------------------------------------------------------------------------------

for path in sorted(glob.glob(os.path.join(ROOT, 'esp', 'Quests', '*.yaml'))):
    y = open(path, encoding='utf-8').read()
    m = re.search(r'Scripts:\s*\n\s*- Name: (\w+)\s*\n\s*Properties:\s*\n((?:\s+- MutagenObjectType.*\n(?:\s{6,}.*\n)*)*)', y)
    if not m:
        check('properties', f'{os.path.basename(path)}: quest script found', False)
        continue
    s = scripts.get(m.group(1).lower())
    filled = set(re.findall(r'Name: (\w+)', m.group(2)))
    want = set()
    cur = s
    while cur:
        want |= {n for n, (t, v, kind, _) in cur.props.items() if kind == 'auto'}
        cur = scripts.get(cur.extends.lower()) if cur.extends else None
    check('properties', f'{m.group(1)}: every Auto property is filled ({sorted(want)})', want <= filled, sorted(want - filled))
    check('properties', f'{m.group(1)}: the YAML fills no property the script lacks', filled <= want, sorted(filled - want))
    check('properties', f'{m.group(1)}: player alias runs MLWS_PlayerAlias', 'Name: MLWS_PlayerAlias' in y and 'ForcedReference: 000014:Skyrim.esm' in y)

# ---------------------------------------------------------------------------------------------------------------------

groups = {}
for g, n, ok, d in results:
    groups.setdefault(g, [0, 0])[0 if ok else 1] += 1
    if not ok:
        print(f'FAIL [{g}] {n}' + (f'  -- {d}' if d not in ('', None) else ''))
for g, (p, f) in groups.items():
    print(f'{g}: {p} passed, {f} failed')
print('papyrus checks:', 'all passed' if not fails else f'{fails} failed')
sys.exit(1 if fails else 0)
