"""Offline checks for the Survival module, no game needed: the action files, the settings file, and that the fact
strings the scripts write parse with the Hub's own reader (lw_state.game_facts). Run from the project root:
    py -3 tools/test_offline.py"""
import functools, glob, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HUB = os.path.join(os.path.dirname(ROOT), 'Mantella-Living-World-Hub', 'server')
ACTIONS_DIR = 'SKSE/Plugins/MantellaSoftware/data/actions'
fails = 0


@functools.lru_cache(maxsize=None)
def read(path):
    """A project file's text (path relative to the project root, or absolute); each file is read once."""
    with open(os.path.join(ROOT, path), encoding='utf-8') as f:
        return f.read()


def load_json(path):
    return json.loads(read(path))


def check(name, ok):
    global fails
    print(('PASS ' if ok else 'FAIL ') + name)
    fails += not ok


actions = glob.glob(os.path.join(ROOT, ACTIONS_DIR, '*.json'))
check('two action files (EatThis is ShareFood player_eats)', len(actions) == 2)
share = load_json(f'{ACTIONS_DIR}/mantella_mlws_share_food.json')
check('ShareFood directions: npc_gives, player_gives, player_eats', share['parameters']['direction']['enum'] == ['npc_gives', 'player_gives', 'player_eats'])
for path in actions:
    a = load_json(path)
    name = os.path.basename(path)
    check(f'{name}: identifier matches file', a['identifier'] + '.json' == name)
    check(f'{name}: requires a response', a.get('requires_response') is True)
    check(f'{name}: gated', bool(a.get('lw_gate')))
    check(f'{name}: prompt has key', '{key}' in a['prompt'])

settings = load_json('SKSE/Plugins/StorageUtilData/MantellaLivingWorld/survival_settings.json')
check('settings: PapyrusUtil layout', set(settings) <= {'int', 'float', 'string', 'stringList'})
check('settings: pure-bloods listed', 'Serana' in settings['stringList']['pure_bloods'])
check('settings: close means lover or spouse (followers get rank 3 on recruit)', settings['int']['close_rank'] == 4)
check("settings: Better Vampires' Victim Damage is never named", 'Victim Damage' in settings['stringList'].get('disease_ignore', []))

# Every key a script reads with SettingInt/SettingFloat has a default in the file.
src = ''.join(read(p) for p in glob.glob(os.path.join(ROOT, 'Source/Scripts/*.psc')))
for kind, key in re.findall(r'Setting(Int|Float)\("(\w+)"', src):
    check(f'settings: {key} present as {kind.lower()}', key in settings[kind.lower()])

# Fact names are all fact_surv_*, so they never collide with another module's.
names = set(re.findall(r'"(fact_\w+)"', src))
facts_src = read('Source/Scripts/MLWS_Facts.psc')
check('join commits after every job, then saves',
      0 <= facts_src.find('Actions.WriteFacts') < facts_src.find('\tCommit(path)') < facts_src.find('JsonUtil.Save(path)'))
check('the vampire job writes first, so the late signs are not cut by conditions',
      0 <= facts_src.find('Vampire.WriteFacts') < facts_src.find('Condition.WriteFacts'))
actions_src = read('Source/Scripts/MLWS_Actions.psc')
bodies = re.findall(r'^Event On\w+\(.*?^EndEvent', actions_src, re.M | re.S)
check('every action rewrites the facts after it is done (one helper, called by every action event)',
      actions_src.count('Facts.Write(akNpc)') == 1 and len(bodies) == 6
      and all(b.find('ActionDone(') < b.find('WriteFactsAfter(akSpeaker as Actor)') for b in bodies)
      and all('WriteFactsAfter(akSpeaker as Actor)' in b for b in bodies))
check('ShareFood and EatThis refuse NPCs outside the party', actions_src.count('is not travelling with') == 2)
share_event = actions_src[actions_src.find('Event OnShareAdvanced'):actions_src.find('EndEvent', actions_src.find('Event OnShareAdvanced'))]
check('ShareFood player_eats runs EatThis, the other directions ShareFood', 'If direction == "player_eats"' in share_event
      and 'EatThis(akSpeaker as Actor)' in share_event and 'ShareFood(akSpeaker as Actor, direction)' in share_event)
eat_bodies = [b for b in bodies if b.startswith('Event OnEat')]
check('the EatThis action of the previous version is still answered (advanced and legacy) by EatThis, then done',
      'RegisterForModEvent(ADVANCED + ACTION_EAT, "OnEatAdvanced")' in actions_src
      and 'RegisterForModEvent(LEGACY + ACTION_EAT, "OnEatLegacy")' in actions_src and len(eat_bodies) == 2
      and all('EatThis(akSpeaker as Actor)' in b and 'ActionDone(ACTION_EAT)' in b for b in eat_bodies))
check('legacy ShareFood prompt describes only npc_gives (the legacy handler always passes it)',
      'gives you' not in share['prompt'] and 'hand the player food' in share['prompt'])
condition_src = read('Source/Scripts/MLWS_Condition.psc')
check('a radiant talk gets no critical warning', 'If !talk.IsPlayerInConversation()' in condition_src)
food_src = read('Source/Scripts/MLWS_Food.psc')
vampire_src = read('Source/Scripts/MLWS_Vampire.psc')
check('follower hunger and vampire blood hunger only with Survival Mode on',
      'If abSurvivalOn && hungry >=' in food_src and 'If abParty && abSurvivalOn' in vampire_src)
util_src = read('Source/Scripts/MLWS_Util.psc')
check('jobs only gather facts, Commit writes the file', 'JsonUtil.SetStringValue' not in util_src and 'JsonUtil.UnsetStringValue' not in util_src)
prios = re.findall(r'Set(?:Now)?Fact\(asPath, .*?, ([0-9]), ', src)
check('every fact priority is 1-3', bool(prios) and all(p in '123' for p in prios))
check('fact names prefixed', names and all(n.startswith('fact_surv_') for n in names))

# 2026-11-08 fixes the model (simulate_survival.py) cannot see in the source itself
cpp = read('plugin/src/Survival.cpp')
witness_fn = cpp[cpp.find('WitnessesNear(RE::StaticFunctionTag*'):]
witness_fn = witness_fn[:witness_fn.find('FoodCount(')]
check('witnesses must detect the player', 'RequestDetectionLevel(player) > 0' in witness_fn)
is_close = util_src[util_src.find('bool Function IsClose'):util_src.find('EndFunction', util_src.find('bool Function IsClose'))]
check('MLW_IsClose counts only with Arousal loaded', re.search(r'PluginLoaded\("Mantella Living World - Arousal\.esp"\) && StorageUtil\.GetIntValue\(akActor, "MLW_IsClose"', is_close) is not None)
check('MRB_Close counts only with Relationships loaded', re.search(r'PluginLoaded\("Mantella Living World - Relationships\.esp"\) && StorageUtil\.GetIntValue\(akActor, "MRB_Close"', is_close) is not None)
check('NPC feeding from Vampire Feed Proxy is heard', 'RegisterForModEvent("NpcVampireFeed", "OnNpcFeed")' in vampire_src)
check('the late-stage signs are hidden by a hood', '!MLWS_Util.FaceHidden(PlayerRef)' in vampire_src)
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
        'fact_surv_hunger': '-1|42|2|Inga is famished.',
        'fact_surv_food_player': '41|43|1|Inga last ate Apple, raw',
        'fact_surv_meal': '40|-1|1|You and Inga shared a meal of Venison Stew',
        'fact_surv_bed': '40|41|1|You slept in a bedroll, 6 hours',  # expired by day 42
    }, 42)
    texts = [f['text'] for f in facts]
    check('hub reads now-facts', 'Inga is famished.' in texts)
    check('hub keeps last food within 2 days', 'Inga last ate Apple, raw' in texts)
    check('hub drops an expired bed', 'You slept in a bedroll, 6 hours' not in texts)
    check('hub sorts priority 2 first', texts[0] == 'Inga is famished.')

print('offline tests:', 'all passed' if not fails else f'{fails} failed')
sys.exit(1 if fails else 0)
