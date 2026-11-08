"""Offline checks for the Survival module, no game needed: the action files, the settings file, and that the fact
strings the scripts write parse with the Hub's own reader (lw_state.game_facts). Run from the project root:
    py -3 tools/test_offline.py"""
import glob, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HUB = os.path.join(os.path.dirname(ROOT), 'Mantella-Living-World-Hub', 'server')
fails = 0


def check(name, ok):
    global fails
    print(('PASS ' if ok else 'FAIL ') + name)
    fails += not ok


actions = glob.glob(os.path.join(ROOT, 'SKSE/Plugins/MantellaSoftware/data/actions/*.json'))
check('three action files', len(actions) == 3)
for path in actions:
    a = json.load(open(path, encoding='utf-8'))
    name = os.path.basename(path)
    check(f'{name}: identifier matches file', a['identifier'] + '.json' == name)
    check(f'{name}: requires a response', a.get('requires_response') is True)
    check(f'{name}: gated', bool(a.get('lw_gate')))
    check(f'{name}: prompt has key', '{key}' in a['prompt'])

settings = json.load(open(os.path.join(ROOT, 'SKSE/Plugins/StorageUtilData/MantellaLivingWorld/survival_settings.json'), encoding='utf-8'))
check('settings: PapyrusUtil layout', set(settings) <= {'int', 'float', 'string', 'stringList'})
check('settings: pure-bloods listed', 'Serana' in settings['stringList']['pure_bloods'])
check('settings: close means lover or spouse (followers get rank 3 on recruit)', settings['int']['close_rank'] == 4)
check("settings: Better Vampires' Victim Damage is never named", 'Victim Damage' in settings['stringList'].get('disease_ignore', []))

# Every key a script reads with SettingInt/SettingFloat has a default in the file.
src = ''.join(open(p, encoding='utf-8').read() for p in glob.glob(os.path.join(ROOT, 'Source/Scripts/*.psc')))
for kind, key in re.findall(r'Setting(Int|Float)\("(\w+)"', src):
    check(f'settings: {key} present as {kind.lower()}', key in settings[kind.lower()])

# Fact names are all fact_surv_*, so they never collide with another module's.
names = set(re.findall(r'"(fact_\w+)"', src))
facts_src = open(os.path.join(ROOT, 'Source/Scripts/MLWS_Facts.psc'), encoding='utf-8').read()
check('join commits after every job, then saves',
      0 <= facts_src.find('Actions.WriteFacts') < facts_src.find('\tCommit(path)') < facts_src.find('JsonUtil.Save(path)'))
check('the vampire job writes first, so the late signs are not cut by conditions',
      0 <= facts_src.find('Vampire.WriteFacts') < facts_src.find('Condition.WriteFacts'))
actions_src = open(os.path.join(ROOT, 'Source/Scripts/MLWS_Actions.psc'), encoding='utf-8').read()
check('every action rewrites the facts on success', actions_src.count('Facts.Write(akNpc)') == 3)
check('ShareFood and EatThis refuse NPCs outside the party', actions_src.count('is not travelling with') == 2)
util_src = open(os.path.join(ROOT, 'Source/Scripts/MLWS_Util.psc'), encoding='utf-8').read()
check('jobs only gather facts, Commit writes the file', 'JsonUtil.SetStringValue' not in util_src and 'JsonUtil.UnsetStringValue' not in util_src)
prios = re.findall(r'Set(?:Now)?Fact\(asPath, .*?, ([0-9]), ', src)
check('every fact priority is 1-3', bool(prios) and all(p in '123' for p in prios))
check('fact names prefixed', names and all(n.startswith('fact_surv_') for n in names))

# 2026-11-08 fixes the model (simulate_survival.py) cannot see in the source itself
cpp = open(os.path.join(ROOT, 'plugin/src/Survival.cpp'), encoding='utf-8').read()
witness_fn = cpp[cpp.find('WitnessesNear(RE::StaticFunctionTag*'):]
witness_fn = witness_fn[:witness_fn.find('FoodCount(')]
check('witnesses must detect the player', 'RequestDetectionLevel(player) > 0' in witness_fn)
is_close = util_src[util_src.find('bool Function IsClose'):util_src.find('EndFunction', util_src.find('bool Function IsClose'))]
check('MLW_IsClose counts only with Arousal loaded', re.search(r'PluginLoaded\("Mantella Living World - Arousal\.esp"\) && StorageUtil\.GetIntValue\(akActor, "MLW_IsClose"', is_close) is not None)
check('MRB_Close counts only with Relationships loaded', re.search(r'PluginLoaded\("Mantella Living World - Relationships\.esp"\) && StorageUtil\.GetIntValue\(akActor, "MRB_Close"', is_close) is not None)
vampire_src = open(os.path.join(ROOT, 'Source/Scripts/MLWS_Vampire.psc'), encoding='utf-8').read()
check('NPC feeding from Vampire Feed Proxy is heard', 'RegisterForModEvent("NpcVampireFeed", "OnNpcFeed")' in vampire_src)
check('the late-stage signs are hidden by a hood', '!MLWS_Util.FaceHidden(PlayerRef)' in vampire_src)
condition_src = open(os.path.join(ROOT, 'Source/Scripts/MLWS_Condition.psc'), encoding='utf-8').read()
check('no warning in beast form or while movement is disabled',
      'MLWS_Util.InBeastForm(PlayerRef) || !Game.IsMovementControlsEnabled()' in condition_src)
check('the vampire races have a warm homeland',
      all(i in condition_src for i in ('0x08883A', '0x08883D', '0x088840', '0x088844', '0x088845', '0x088846', '0x088884')))

sys.path.insert(0, HUB)
try:
    from living_world import lw_state
except Exception as e:  # the Hub repository is optional for this test
    print('SKIP hub reader:', e)
else:
    facts = lw_state.game_facts({
        'fact_surv_hunger': '-1|42|2|Vega is famished.',
        'fact_surv_food_player': '41|43|1|Vega last ate Apple, raw',
        'fact_surv_meal': '40|-1|1|You and Vega shared a meal of Venison Stew',
        'fact_surv_bed': '40|41|1|You slept in a bedroll, 6 hours',  # expired by day 42
    }, 42)
    texts = [f['text'] for f in facts]
    check('hub reads now-facts', 'Vega is famished.' in texts)
    check('hub keeps last food within 2 days', 'Vega last ate Apple, raw' in texts)
    check('hub drops an expired bed', 'You slept in a bedroll, 6 hours' not in texts)
    check('hub sorts priority 2 first', texts[0] == 'Vega is famished.')

print('offline tests:', 'all passed' if not fails else f'{fails} failed')
sys.exit(1 if fails else 0)
