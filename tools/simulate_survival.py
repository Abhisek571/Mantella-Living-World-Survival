"""Offline model of the Survival module's game-side logic, driven by random days of play, plus an exhaustive check of
who may hear about a vampire player. No game needed. Run from the project root:
    py -3 tools/simulate_survival.py                 # random play (default 6 runs x 120 days) + exhaustive vampire check
    py -3 tools/simulate_survival.py --before        # the same with the shipped behaviour of the fixed defects (B1-B6)
    py -3 tools/simulate_survival.py --tokens        # also print the worst-case token estimate of one NPC's facts

Each function below mirrors one Papyrus function or SKSE native; the comment names the file and lines it models
(Source/Scripts/*.psc, plugin/src/Survival.cpp). StorageUtil data and script variables belong to a save; the JsonUtil
npc files are shared by every save, as in the game. Papyrus floats are 32-bit, so game times go through f32().

Defects found by this model, each with a switch so --before reproduces the shipped behaviour:
  B1 a vampire player's secret reached an NPC who shares the base record (and so the npc file) with a witness or a
     close party member in the same talk
  B2 ShareFood/EatThis event lines that give a vampire player away were heard by every NPC in the talk, though only
     the acting NPC was checked
  B3 MLWS_Util.IsParty counted summons and raised thralls as party members
  B4 "has warmed up" was written together with "is very cold"/"is freezing"
  B5 "You have not slept in N days" and "You have not fed in N days" had no cap (days apart from the party counted)
  B6 hours slept were truncated from a float difference: a 1-hour sleep could read "0 hours", 8 hours "7 hours"
Later fixes are modelled as shipped now (no switch): close_rank 4, sleepers are no witnesses, disease_ignore, pure-blood
needs the Vampire keyword and never the player, facts rewritten after an action, ShareFood/EatThis party only, EatThis
reads Survival Mode's hunger without SMI, drinks are not meals, the shared meal lasts 2 days, no best bed without one,
unique-only knowers for the action lines, the vampire job writes first, and (2026-11-08) the later of our feed stamp
and LastFeedTime, bottled blood as a feeding without a victim, witnesses must detect the player, an awake victim knows,
Vampire Lord witnesses, a cure clears the feeding and older sightings become memories, NpcVampireFeed resets an NPC
vampire's hunger, a hood hides the signs, vampire races have a warm homeland, another module's closeness mark counts
only while that module is loaded, and no warning in beast form or while movement is disabled. vampire_cases() checks
each of these on its own.
"""
import argparse, copy, itertools, json, os, random, re, struct, sys
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HUB_SERVER = os.path.join(os.path.dirname(ROOT), 'Mantella-Living-World-Hub', 'server')
SETTINGS = json.load(open(os.path.join(ROOT, 'SKSE/Plugins/StorageUtilData/MantellaLivingWorld/survival_settings.json'), encoding='utf-8'))

sys.path.insert(0, HUB_SERVER)
try:
    from living_world import lw_state as _hub_state, memory as _hub_memory
    game_facts, tokens, FACT_TOKENS, MIN_GROUP = _hub_state.game_facts, _hub_memory.tokens, _hub_memory.FACT_TOKENS, _hub_memory.MIN_GROUP_FACT_TOKENS
    HUB_SOURCE = 'Hub reader imported'
except Exception as e:  # a copy of lw_state.game_facts (lw_state.py:112-131) and memory.tokens (memory.py:161)
    HUB_SOURCE = f'Hub not importable ({e}); using a copy of its reader'

    def game_facts(npc, today):
        rows = []
        for key, value in (npc or {}).items():
            if not str(key).lower().startswith('fact_') or not isinstance(value, str):
                continue
            parts = value.split('|', 3)
            if len(parts) != 4 or not parts[3].strip():
                continue
            try:
                day, expires, priority = int(parts[0]), int(parts[1]), int(parts[2])
            except ValueError:
                continue
            if expires >= 0 and today is not None and today > expires:
                continue
            rows.append({'day': day, 'priority': priority, 'text': parts[3].strip()})
        return sorted(rows, key=lambda r: (-r['priority'], -(r['day'] if r['day'] >= 0 else 1 << 30)))

    tokens = lambda text: (len(text) + 3) // 4
    FACT_TOKENS, MIN_GROUP = 200, 90

FIXED = {'B1', 'B2', 'B3', 'B4', 'B5', 'B6'}  # cleared by --before


def f32(x):
    return struct.unpack('f', struct.pack('f', x))[0]


def setting_int(key, default):  # MLWS_Util.psc:43-45
    return SETTINGS['int'].get(key, default)


def setting_float(key, default):  # MLWS_Util.psc:47-49
    return SETTINGS['float'].get(key, default)


# ---------------------------------------------------------------------------------------------------------------------
# Game data
# ---------------------------------------------------------------------------------------------------------------------

@dataclass
class Item:
    name: str
    food: bool = True
    raw: bool = False
    alcohol: bool = False
    blood: bool = False
    gold: int = 5
    quest: bool = False
    hunger: float = 60.0


FOODS = [Item('Apple', gold=3, hunger=25), Item('Bread', gold=2, hunger=40), Item('Venison Stew', gold=12, hunger=150),
         Item('Horker and Ash Yam Stew', gold=15, hunger=150), Item('Raw Beef', raw=True, gold=4, hunger=30),
         Item('Salmon Meat', raw=True, gold=3, hunger=25), Item('Grilled Leeks', gold=6, hunger=60),
         Item('Sweetroll', gold=4, hunger=30), Item('Elsweyr Fondue', gold=40, hunger=120)]
DRINKS = [Item('Ale', alcohol=True, gold=5, hunger=10), Item('Nord Mead', alcohol=True, gold=8, hunger=10),
          Item('Alto Wine', alcohol=True, gold=10, hunger=10)]
BLOOD = [Item('Potion of Blood', food=False, blood=True, gold=10, hunger=0)]
QUEST_FOOD = Item('Sweet Roll of Ancient Power', gold=1, quest=True)
DISEASES = ['Ataxia', 'Rockjoint', 'Brain Rot', 'Bone Break Fever', 'Witbane', 'Rattles', 'Victim Damage']
SANGUINARE = 'Sanguinare Vampiris'
WARM_RACES = {'Argonian': 'Black Marsh', 'Khajiit': 'Elsweyr', 'Redguard': 'Hammerfell', 'Dark Elf': 'Morrowind',
              'Imperial': 'Cyrodiil', 'High Elf': 'the Summerset Isles', 'Wood Elf': 'Valenwood'}
WARM_RACES.update({k + ' Vampire': v for k, v in list(WARM_RACES.items())})  # the *RaceVampire twins (MLWS_Condition WarmHome)
THRESHOLDS = [[50, 100, 200, 300, 400], [50, 120, 240, 360, 500], [60, 120, 240, 360, 480]]  # hunger, cold, tired
PLACES = ['Whiterun', 'The Bannered Mare', 'Breezehome', 'Bleak Falls Barrow', 'Riverwood', 'Dragon Bridge', '']


@dataclass
class Actor:
    ref: int
    base: int
    name: str
    unique: bool = True
    race: str = 'Nord'
    teammate: bool = False
    follower_rank: int = -1          # CurrentFollowerFaction rank, -1 = not in it
    commanded: bool = False          # summon or raised thrall
    rank: int = 0                    # relationship rank to the player
    vampire_kw: bool = False
    pure_base: bool = False          # Harkon, Valerica, Serana records
    dead: bool = False
    health: float = 1.0
    diseases: list = field(default_factory=list)
    inventory: list = field(default_factory=list)
    fire: bool = False
    combat: bool = False
    distance: float = 600.0
    los: bool = True
    asleep: bool = False
    detects: bool = True             # RequestDetectionLevel(player) > 0


@dataclass
class Player:
    name: str
    race: str = 'Nord'
    vampire_kw: bool = False
    vstatus: int = 0                 # PlayerVampireQuestScript.VampireStatus
    last_feed_time: float = 0.0      # PlayerVampireQuestScript.LastFeedTime
    masked: bool = False
    interior: bool = False
    weather: int = 0                 # classification: 0 pleasant, 1 cloudy, 2 rain, 3 snow
    needs: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    survival_on: bool = True         # Survival Mode's global, kept in the save
    health: float = 1.0
    diseases: list = field(default_factory=list)
    inventory: list = field(default_factory=list)
    combat: bool = False
    sneaking: bool = False
    werewolf: bool = False
    lord: bool = False               # in Vampire Lord form
    movement: bool = True            # Game.IsMovementControlsEnabled
    hooded: bool = False             # a slot 30/31 armor worn


PLAYER = 0x14


class Launch:
    """What is installed for one game launch (shared by every save loaded in it)."""
    def __init__(self, survival=True, smi=True, hub=True, better_vampires=False, arousal=True, relationships=True):
        self.survival, self.smi, self.hub, self.better_vampires = survival, smi, hub, better_vampires
        self.arousal, self.relationships = arousal, relationships
        self.real = 0.0              # real seconds since launch (Utility.GetCurrentRealTime)
        self.pace = {}               # MLW_Pace StorageUtil, per save in the game; kept here as the Hub's own
        self.path_members = True     # whether JsonUtil.PathMembers(".string") returns the keys


class World:
    """One save: StorageUtil, script variables, the player, the actors, and what really happened (for the checks)."""
    def __init__(self, player_name, roster):
        self.time = 3.3
        self.store = {}              # (owner, key) -> value; owner None for global keys
        self.player = Player(player_name)
        self.actors = {a.ref: a for a in copy.deepcopy(roster)}
        # MLWS_Condition script variables (MLWS_Condition.psc:21-24)
        self.last_stage = None
        self.armed = None
        # MLWS_Beds script variables (MLWS_Beds.psc:14-19)
        self.last_sat = None
        self.last_sat_at = -1.0
        self.start_at = -1.0
        self.start_kind = 0
        self.start_place = ''
        self.sharers = None
        self.talk_running = False
        # truth, for the checks (rolls back with the save like everything else)
        self.witnessed = set()       # refs that saw a feeding
        self.witnessed_asleep = set()  # refs made witnesses while asleep (must stay empty)
        self.warnings = []           # (game time, need, follower ref)
        self.party_since = {}        # ref -> game time they last joined
        self.sleep_truth = {}        # actor ref -> true hours of the last tracked sleep
        self.warm_fact_bad = []


ALL_FACTS = set()  # every fact name a Write may stage or clear, collected as the model runs


# ---------------------------------------------------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------------------------------------------------

class Sim:
    def __init__(self, launch, world, files, fixed, report):
        self.L, self.W, self.files, self.fixed, self.rep = launch, world, files, fixed, report
        self.lines = []              # MantellaAddEvent lines of the current talk
        self.food_moved = []         # (giver, taker) of every ShareFood/EatThis that moved food

    # --- StorageUtil -------------------------------------------------------------------------------------------------
    def sget(self, owner, key, default=None):
        return self.W.store.get((owner, key.lower()), default)

    def sset(self, owner, key, value):
        if isinstance(value, float):
            value = f32(value)
        self.W.store[(owner, key.lower())] = value

    def shas(self, owner, key):
        return (owner, key.lower()) in self.W.store

    def sunset(self, owner, key):
        self.W.store.pop((owner, key.lower()), None)

    def slist(self, owner, key):
        return self.W.store.setdefault((owner, key.lower()), [])

    # --- engine reads ------------------------------------------------------------------------------------------------
    def now(self):  # Utility.GetCurrentGameTime: a 32-bit float
        return f32(self.W.time)

    def actor(self, ref):
        return self.W.actors.get(ref)

    def name(self, ref):
        return self.W.player.name if ref == PLAYER else self.actor(ref).name

    # --- MLWS_Util ---------------------------------------------------------------------------------------------------
    def npc_file(self, ref):  # MLWS_Util.psc:87-98
        return 'MantellaLivingWorld/npc/%06X.json' % (self.actor(ref).base & 0xFFFFFF)

    def set_fact(self, path, name, day, expires, prio, text):  # MLWS_Util.psc:103-106
        ALL_FACTS.add(name)
        self.slist(None, 'MLWS_FactName' + path).append(name)
        self.slist(None, 'MLWS_FactValue' + path).append(f'{day}|{expires}|{prio}|{text}')

    def clear_fact(self, path, name):  # MLWS_Util.psc:109-111 (no duplicates)
        ALL_FACTS.add(name)
        gone = self.slist(None, 'MLWS_FactGone' + path)
        if name not in gone:
            gone.append(name)

    def set_now_fact(self, path, name, today, prio, text):  # MLWS_Util.psc:114-116
        self.set_fact(path, name, -1, today, prio, text)

    def is_party(self, ref):  # MLWS_Util.psc:118-124
        a = self.actor(ref)
        if 'B3' in self.fixed and a.commanded:
            return False
        return a.teammate or a.follower_rank >= 0

    def is_close(self, ref):  # MLWS_Util.psc:127-135
        if not self.is_party(ref):
            return False
        a = self.actor(ref)
        if a.rank >= setting_int('close_rank', 4):
            return True
        return (self.L.arousal and self.sget(ref, 'MLW_IsClose', 0) > 0) or (self.L.relationships and self.sget(ref, 'MRB_Close', 0) > 0)

    def in_beast_form(self):  # MLWS_Util.psc InBeastForm
        return self.W.player.werewolf or self.W.player.lord

    def saw_vampire(self, ref):  # MLWS_Util.psc SawVampire
        cured = self.sget(PLAYER, 'MLWS_CuredAt', -1.0)
        saw, lord = self.sget(ref, 'MLWS_SawFeedAt', -1.0), self.sget(ref, 'MLWS_SawLordAt', -1.0)
        return (saw >= 0.0 and saw >= cured) or (lord >= 0.0 and lord >= cured)

    def is_pure_blood(self, ref):  # MLWS_Util.psc IsPureBlood: a vampire NPC only, never the player
        if ref == PLAYER or not self.is_vampire(ref):
            return False
        if self.actor(ref).pure_base:
            return True
        return self.name(ref).lower() in [n.lower() for n in SETTINGS['stringList']['pure_bloods']]

    def is_vampire(self, ref):  # MLWS_Util.psc:149-152
        return self.W.player.vampire_kw if ref == PLAYER else self.actor(ref).vampire_kw

    def is_drunk(self, ref, now):  # MLWS_Util.psc:155-165
        drinks = self.sget(ref, 'MLWS_Drinks', [])
        return sum(1 for t in drinks if now - t <= 0.0834) >= setting_int('drunk_drinks', 3)

    def days_since(self, ref, key, now):  # MLWS_Util.psc:168-174
        at = self.sget(ref, key, -1.0)
        if at < 0.0:
            at = self.sget(ref, 'MLWS_SeenAt', now)
        return int(f32(now - at))

    def survival_on(self):  # MLWS_Util.psc:35-41
        return self.L.survival and self.W.player.survival_on

    def send(self, line):  # MLWS_Util.psc:61-71
        if line:
            self.lines.append(line)

    # --- natives (plugin/src/Survival.cpp) ---------------------------------------------------------------------------
    def party_member_native(self, ref):  # Survival.cpp:36-39
        a = self.actor(ref)
        return a.teammate and not a.commanded

    def party_near(self, radius):  # Survival.cpp:134-159
        found = [a for a in self.W.actors.values() if not a.dead and self.party_member_native(a.ref) and a.distance <= radius]
        return [a.ref for a in sorted(found, key=lambda a: a.distance)]

    def witnesses_near(self, skip, radius):  # Survival.cpp:162-182
        return [a.ref for a in self.W.actors.values() if a.ref != skip and not a.dead and not a.asleep and a.distance <= radius and a.los and a.detects]

    def inventory(self, ref):
        return self.W.player.inventory if ref == PLAYER else self.actor(ref).inventory

    def food_count(self, ref):  # Survival.cpp:184-193
        return sum(1 for i in self.inventory(ref) if i.food)

    def pick_food(self, ref, blood):  # Survival.cpp:197-222
        best, rank = None, 0
        for i in self.inventory(ref):
            if i.quest or not (i.blood if blood else i.food):
                continue
            r = (1_000_000 if i.raw else 0) + (2_000_000 if i.alcohol else 0) + i.gold
            if best is None or r < rank:
                best, rank = i, r
        return best

    def food_flags(self, item):  # Survival.cpp:84-97, 225-229
        return (1 if item.raw else 0) | (2 if item.alcohol else 0) | (4 if item.blood else 0)

    def disease_names(self, ref):  # Survival.cpp:232-263
        names = self.W.player.diseases if ref == PLAYER else self.actor(ref).diseases
        return ', '.join(dict.fromkeys(n for n in names if n != SANGUINARE))

    def shown_diseases(self, ref):  # MLWS_Condition.psc ShownDiseases: drops the settings' disease_ignore names
        ignore = SETTINGS['stringList'].get('disease_ignore', [])
        return ', '.join(n for n in self.disease_names(ref).split(', ') if n and n not in ignore)

    def on_equip(self, ref, item):  # Survival.cpp:99-117: sends MLWS_Ate for the player and party members only
        if not item.food and not item.blood:
            return
        if ref != PLAYER and not self.party_member_native(ref):
            return
        self.on_ate(ref, item.name, float(self.food_flags(item)))

    # --- MLWS_Facts --------------------------------------------------------------------------------------------------
    def file(self, path):
        return self.files.setdefault(path, {'string': {}, 'int': {}})

    def write(self, ref, interleave_with=None):  # MLWS_Facts.psc:25-46
        path = self.npc_file(ref)
        now = self.now()
        party = self.is_party(ref)
        if party and not self.shas(ref, 'MLWS_SeenAt'):
            self.sset(ref, 'MLWS_SeenAt', now)
        self.clear_staged(path)
        self.vampire_facts(ref, path, party, now)
        self.condition_facts(ref, path, party, now)
        self.food_facts(ref, path, party, now)
        self.beds_facts(ref, path, party, now)
        self.actions_facts(ref, path, party, now)
        if interleave_with is not None:
            return path  # the caller runs the other Write's jobs into the same staging lists, then commits
        return self.commit(path)

    def commit(self, path):  # MLWS_Facts.psc:51-95
        names = list(self.slist(None, 'MLWS_FactName' + path))
        values = list(self.slist(None, 'MLWS_FactValue' + path))
        gone = list(self.slist(None, 'MLWS_FactGone' + path))
        staged = list(zip(names, values))
        cap = setting_int('max_facts', 6)
        f = self.file(path)['string']
        kept, taken = [], 0
        for prio in (3, 2, 1):
            if taken >= cap:
                break
            for name, value in staged:
                if taken >= cap:
                    break
                if self.priority_of(value) == prio:
                    f[name] = value
                    if name not in kept:
                        kept.append(name)
                    taken += 1
        in_file = list(f) if self.L.path_members else []
        for n in [k for k in in_file if k.startswith('fact_surv_')] + names + gone:
            if n not in kept:
                f.pop(n, None)
        self.clear_staged(path)
        self.check_commit(path, staged, gone, kept)
        return kept

    @staticmethod
    def priority_of(value):  # MLWS_Facts.psc:104-116
        parts = value.split('|')
        p = int(parts[2]) if len(parts) >= 3 else 1
        return max(1, min(3, p))

    def clear_staged(self, path):  # MLWS_Facts.psc:118-123
        for k in ('MLWS_FactName', 'MLWS_FactValue', 'MLWS_FactGone', 'MLWS_FactKept'):
            self.W.store.pop((None, (k + path).lower()), None)

    # --- MLWS_Condition ----------------------------------------------------------------------------------------------
    def stage(self, need):  # MLWS_Condition.psc:68-82 (needs from Setup, :33-65)
        if not self.L.survival or (need > 0 and not self.L.smi) or not self.survival_on():
            return -1
        value = self.W.player.needs[need]
        return sum(1 for t in THRESHOLDS[need] if value >= t)

    @staticmethod
    def need_words(need, stage):  # MLWS_Condition.psc:85-107
        words = [['is hungry', 'is famished', 'is starving'], ['is very cold', 'is freezing', 'is numb with cold'],
                 ['is tired', 'is weary', 'is debilitated by exhaustion']][need]
        return words[0] if stage == 3 else words[1] if stage == 4 else words[2]

    def condition_register(self):  # MLWS_Condition.psc:26-42
        if self.W.last_stage is None:
            self.W.last_stage, self.W.armed = [0, 0, 0], [True, True, True]

    def check(self):  # MLWS_Condition.psc:118-138, run every 30 real seconds while Survival Mode is installed
        if not self.L.survival:
            return
        self.condition_register()
        now = self.now()
        vampire = self.is_vampire(PLAYER)
        for i in range(3):
            st = self.stage(i)
            if st >= 0 and not (i == 0 and vampire):
                if i == 1 and self.W.last_stage[1] >= 3 and st < self.W.last_stage[1]:
                    self.sset(PLAYER, 'MLWS_WarmAt', now)
                    self.sset(PLAYER, 'MLWS_WarmFrom', self.W.last_stage[1])
                self.W.last_stage[i] = st
                if st < 5:
                    self.W.armed[i] = True
                elif self.W.armed[i] and self.warn(i, now):
                    self.W.armed[i] = False

    def try_claim(self, source, cooldown):  # MLW_Pace.psc:26-60 (quiet, talk, GAP 10 s, own cooldown)
        now = self.L.real
        if self.W.talk_running:
            return False
        last = self.L.pace.get('last', -1.0)
        if 0 <= last <= now and now - last < 10.0:
            return False
        mine = self.L.pace.get(source, -1.0)
        if 0 <= mine <= now and now - mine < cooldown:
            return False
        self.L.pace[source] = self.L.pace['last'] = now
        return True

    def warn(self, need, now):  # MLWS_Condition.psc:141-180
        if setting_int('critical_warning', 1) != 1:
            return True
        key = 'MLWS_WarnedAt' + str(need)
        if now - self.sget(None, key, -1000.0) < setting_float('critical_cooldown_days', 3.0):
            return True
        if self.W.player.combat or self.W.player.sneaking:
            return False
        if self.in_beast_form() or not self.W.player.movement:
            return False
        near = self.party_near(setting_float('critical_radius', 1500.0))
        if not near:
            return False
        follower = near[0]
        line = f'{self.W.player.name} {self.need_words(need, 5)}. {self.name(follower)} can see it.'
        if not self.W.talk_running:
            if self.L.hub and not self.try_claim('survival', 600.0):
                return False
        self.send(line)
        a = self.actor(follower)
        self.W.warnings.append((now, need, follower, a.commanded, self.oracle_party(follower)))
        self.sset(None, key, now)
        return True

    def condition_facts(self, ref, path, party, now):  # MLWS_Condition.psc:186-203
        today = int(now)
        player = self.W.player.name
        self.need_fact(path, 'fact_surv_hunger', 0, today, player, self.is_vampire(PLAYER))
        self.need_fact(path, 'fact_surv_cold', 1, today, player, False)
        self.need_fact(path, 'fact_surv_tired', 2, today, player, False)
        warm_at = self.sget(PLAYER, 'MLWS_WarmAt', -1.0)
        still_cold = 'B4' in self.fixed and self.stage(1) >= 3
        if party and warm_at >= 0.0 and now - warm_at <= 0.05 and not still_cold:
            self.set_now_fact(path, 'fact_surv_warming', today, 2, player + ' has warmed up since the cold got to them.')
        else:
            self.clear_fact(path, 'fact_surv_warming')
        self.visible(PLAYER, path, 'fact_surv_player_', player + ' ', today, now)
        self.visible(ref, path, 'fact_surv_self_', 'You ', today, now)
        self.weather(ref, path, party, today)

    def need_fact(self, path, fact, need, today, player, skip):  # MLWS_Condition.psc:205-212
        st = self.stage(need)
        if st >= 3 and not skip:
            self.set_now_fact(path, fact, today, 3, f'{player} {self.need_words(need, st)}.')
        else:
            self.clear_fact(path, fact)

    def visible(self, ref, path, prefix, who, today, now):  # MLWS_Condition.psc:215-254
        you = who == 'You '
        health = self.W.player.health if ref == PLAYER else self.actor(ref).health
        if health < 0.25:
            self.set_now_fact(path, prefix + 'wounded', today, 3, 'You are badly wounded.' if you else who + 'is badly wounded.')
        elif health < 0.5:
            self.set_now_fact(path, prefix + 'wounded', today, 3, 'You are wounded.' if you else who + 'is wounded.')
        else:
            self.clear_fact(path, prefix + 'wounded')
        if self.is_drunk(ref, now):
            self.set_now_fact(path, prefix + 'drunk', today, 3, 'You are drunk.' if you else who + 'is drunk.')
        else:
            self.clear_fact(path, prefix + 'drunk')
        d = self.shown_diseases(ref)
        if d:
            self.set_now_fact(path, prefix + 'disease', today, 3, f'You have {d}.' if you else f'{who}has {d}.')
        else:
            self.clear_fact(path, prefix + 'disease')

    def weather(self, ref, path, party, today):  # MLWS_Condition.psc:257-293
        home = ''
        if party and not self.W.player.interior and self.W.player.weather == 3:
            home = WARM_RACES.get(self.actor(ref).race, '')
        if home:
            self.set_now_fact(path, 'fact_surv_weather', today, 3, f'It is snowing. Your people come from {home}, a warmer land.')
        else:
            self.clear_fact(path, 'fact_surv_weather')

    # --- MLWS_Food ---------------------------------------------------------------------------------------------------
    def on_ate(self, ref, name, flags):  # MLWS_Food.psc:26-39
        real = self.L.real
        action_real = self.sget(ref, 'MLWS_FoodReal', -100.0)
        if self.sget(ref, 'MLWS_FoodPending', '') == name and real >= action_real and real - action_real < 3.0:
            self.sunset(ref, 'MLWS_FoodPending')
            return
        self.record(ref, name, int(flags))

    def record(self, ref, name, flags, equipped=False):  # MLWS_Food.psc:43-64
        now = self.now()
        if equipped:
            self.sset(ref, 'MLWS_FoodReal', self.L.real)
            self.sset(ref, 'MLWS_FoodPending', name)
        if flags & 4:
            self.sset(ref, 'MLWS_BloodAt', now)
            if ref == PLAYER:  # bottled blood: a feeding without a victim
                self.sset(PLAYER, 'MLWS_FedAt', now)
                self.sset(PLAYER, 'MLWS_FedVictim', '')
            return
        if flags & 2:
            drinks = self.slist(ref, 'MLWS_Drinks')
            drinks.append(now)
            while drinks and now - drinks[0] > 0.0834:
                drinks.pop(0)
            return  # a drink is not a meal
        self.sset(ref, 'MLWS_FoodName', name)
        self.sset(ref, 'MLWS_FoodAt', now)
        self.sset(ref, 'MLWS_FoodRaw', flags & 1)
        self.count(ref, name)
        self.shared_meal(ref, name, now)

    def count(self, ref, name):  # MLWS_Food.psc:66-74
        names, counts = self.slist(ref, 'MLWS_FoodNames'), self.slist(ref, 'MLWS_FoodCounts')
        if name in names:
            counts[names.index(name)] += 1
        elif len(names) < 40:
            names.append(name)
            counts.append(1)

    def shared_meal(self, ref, name, now):  # MLWS_Food.psc:77-92
        if ref == PLAYER:
            for r in self.party_near(2048.0):
                if now - self.sget(r, 'MLWS_FoodAt', -1000.0) <= 0.0417:
                    self.sset(r, 'MLWS_MealAt', now)
                    self.sset(r, 'MLWS_MealFood', name)
        elif now - self.sget(PLAYER, 'MLWS_FoodAt', -1000.0) <= 0.0417 and self.actor(ref).distance <= 2048.0:
            self.sset(ref, 'MLWS_MealAt', now)
            self.sset(ref, 'MLWS_MealFood', name)

    def favourite(self, ref):  # MLWS_Food.psc:94-107
        best, best_count = '', 2
        names, counts = self.sget(ref, 'MLWS_FoodNames', []), self.sget(ref, 'MLWS_FoodCounts', [])
        for i in reversed(range(len(names))):
            if counts[i] > best_count:
                best_count, best = counts[i], names[i]
        return best

    def food_facts(self, ref, path, party, now):  # MLWS_Food.psc:109-162
        food_names = ['fact_surv_food_player', 'fact_surv_food_self', 'fact_surv_fav_player', 'fact_surv_fav_self',
                      'fact_surv_meal', 'fact_surv_hungry', 'fact_surv_supplies']
        if not party:
            for n in food_names:
                self.clear_fact(path, n)
            return
        player, today = self.W.player.name, int(now)
        self.last_food(PLAYER, path, 'fact_surv_food_player', player + ' last ate ')
        self.last_food(ref, path, 'fact_surv_food_self', 'You last ate ')
        fav = self.favourite(PLAYER)
        if fav:
            self.set_fact(path, 'fact_surv_fav_player', -1, -1, 1, f'{player} eats {fav} most often.')
        else:
            self.clear_fact(path, 'fact_surv_fav_player')
        fav = self.favourite(ref)
        if fav:
            self.set_fact(path, 'fact_surv_fav_self', -1, -1, 1, f'You eat {fav} most often.')
        else:
            self.clear_fact(path, 'fact_surv_fav_self')
        meal_at = self.sget(ref, 'MLWS_MealAt', -1.0)
        if meal_at >= 0.0:
            self.set_fact(path, 'fact_surv_meal', int(meal_at), int(meal_at) + 2, 2, f"You and {player} shared a meal of {self.sget(ref, 'MLWS_MealFood', '')}")
        else:
            self.clear_fact(path, 'fact_surv_meal')
        hungry = self.days_since(ref, 'MLWS_FoodAt', now)
        if hungry >= setting_int('follower_hungry_days', 2) and not self.is_vampire(ref):
            most = setting_int('follower_hungry_max', 7)
            text = f'You have not eaten in over {most} days.' if hungry > most else f'You have not eaten in {hungry} days.'
            self.set_now_fact(path, 'fact_surv_hungry', today, 3, text)
        else:
            self.clear_fact(path, 'fact_surv_hungry')
        food = self.food_count(PLAYER)
        if food <= setting_int('low_food', 3) and not self.is_vampire(PLAYER):
            text = f'{player} is carrying no food.' if food == 0 else f'{player} is carrying only {food} food items.'
            self.set_now_fact(path, 'fact_surv_supplies', today, 2, text)
        else:
            self.clear_fact(path, 'fact_surv_supplies')

    def last_food(self, ref, path, fact, text):  # MLWS_Food.psc:164-176
        at = self.sget(ref, 'MLWS_FoodAt', -1.0)
        if at < 0.0:
            self.clear_fact(path, fact)
            return
        day = int(at)
        text += self.sget(ref, 'MLWS_FoodName', '')
        if self.sget(ref, 'MLWS_FoodRaw', 0) == 1:
            text += ', raw'
        self.set_fact(path, fact, day, day + 2, 2, text)

    # --- MLWS_Beds ---------------------------------------------------------------------------------------------------
    def sat(self, kind):  # MLWS_Beds.psc:25-28
        self.W.last_sat, self.W.last_sat_at = kind, self.now()

    def sleep_start(self, bed_kind, place):  # MLWS_Beds.psc:30-43; bed_kind is KindOf(furniture in use), None = none
        self.W.start_at = self.now()
        bed = bed_kind
        if bed is None and self.W.last_sat is not None and self.W.start_at - self.W.last_sat_at <= 0.02:
            bed = self.W.last_sat
        self.W.start_kind = 1 if bed is None else bed
        self.W.start_place = place
        self.W.sharers = self.party_near(4096.0)

    def sleep_stop(self):  # MLWS_Beds.psc:45-64
        if self.W.start_at < 0.0:
            return
        now = self.now()
        hours = f32((now - self.W.start_at) * 24.0)
        self.W.start_at = -1.0
        if hours < 0.25:
            return
        self.apply(PLAYER, self.W.start_kind, self.W.start_place, hours, now)
        for r in self.W.sharers or []:
            self.apply(r, self.W.start_kind, self.W.start_place, hours, now)
        self.W.sharers = None

    def apply(self, ref, kind, place, hours, now):  # MLWS_Beds.psc:66-81
        whole = int(hours + 0.5) if 'B6' in self.fixed else int(hours)
        self.sset(ref, 'MLWS_BedKind', kind)
        self.sset(ref, 'MLWS_BedPlace', place)
        self.sset(ref, 'MLWS_BedAt', now)
        self.sset(ref, 'MLWS_BedHours', whole)
        if kind >= 3:
            self.sset(ref, 'MLWS_RealBedAt', now)
        score = self.score(kind, place, hours)
        if kind >= 2 and score > self.sget(ref, 'MLWS_BestScore', 0):
            self.sset(ref, 'MLWS_BestScore', score)
            self.sset(ref, 'MLWS_BestKind', kind)
            self.sset(ref, 'MLWS_BestPlace', place)
            self.sset(ref, 'MLWS_BestHours', whole)

    @staticmethod
    def score(kind, place, hours):  # MLWS_Beds.psc:83-93
        return kind * 100 + int(min(hours, 8.0) * 5.0) + (10 if place else 0)

    @staticmethod
    def describe(kind, place, hours, player):  # MLWS_Beds.psc:123-141
        where = f' at {place}' if place else ''
        out = (f"in {player}'s home{where}" if kind == 6 else f'at an inn{where}' if kind == 5 else
               f'in a bed{where}' if kind >= 3 else f'in a bedroll{where}' if kind == 2 else f'without a bed{where}')
        return f'{out}, {hours} hours'

    def beds_facts(self, ref, path, party, now):  # MLWS_Beds.psc:143-193
        if not party:
            for n in ('fact_surv_bed', 'fact_surv_best_bed', 'fact_surv_road', 'fact_surv_rest'):
                self.clear_fact(path, n)
            return
        player, today = self.W.player.name, int(now)
        mine, theirs = self.sget(ref, 'MLWS_BedAt', -1.0), self.sget(PLAYER, 'MLWS_BedAt', -1.0)
        g = lambda r, k, d=0: self.sget(r, k, d)
        if mine >= 0.0 and mine >= theirs:
            text = f'You and {player} slept ' if mine == theirs else 'You slept '
            self.set_fact(path, 'fact_surv_bed', int(mine), int(mine) + 1, 2, text + self.describe(g(ref, 'MLWS_BedKind'), g(ref, 'MLWS_BedPlace', ''), g(ref, 'MLWS_BedHours'), player))
        elif theirs >= 0.0:
            self.set_fact(path, 'fact_surv_bed', int(theirs), int(theirs) + 1, 2, f'{player} slept ' + self.describe(g(PLAYER, 'MLWS_BedKind'), g(PLAYER, 'MLWS_BedPlace', ''), g(PLAYER, 'MLWS_BedHours'), player))
        else:
            self.clear_fact(path, 'fact_surv_bed')
        if g(ref, 'MLWS_BestScore') > 0:
            self.set_fact(path, 'fact_surv_best_bed', -1, -1, 1, f'The best bed you have had with {player}: ' + self.describe(g(ref, 'MLWS_BestKind'), g(ref, 'MLWS_BestPlace', ''), g(ref, 'MLWS_BestHours'), player) + '.')
        else:
            self.clear_fact(path, 'fact_surv_best_bed')
        if not self.shas(PLAYER, 'MLWS_SeenAt'):
            self.sset(PLAYER, 'MLWS_SeenAt', now)
        road = self.days_since(PLAYER, 'MLWS_RealBedAt', now)
        if road >= 2:
            self.set_now_fact(path, 'fact_surv_road', today, 2, f'{player} has gone {road} days without a real bed.')
        else:
            self.clear_fact(path, 'fact_surv_road')
        awake = self.days_since(ref, 'MLWS_BedAt', now)
        most = setting_int('follower_hungry_max', 7)
        if awake >= 2:
            text = f'You have not slept in over {most} days.' if 'B5' in self.fixed and awake > most else f'You have not slept in {awake} days.'
            self.set_now_fact(path, 'fact_surv_rest', today, 3, text)
        elif mine >= 0.0 and now - mine <= 1.0 and g(ref, 'MLWS_BedHours') < 4:
            self.set_now_fact(path, 'fact_surv_rest', today, 3, f"You slept only {g(ref, 'MLWS_BedHours')} hours last time.")
        else:
            self.clear_fact(path, 'fact_surv_rest')

    # --- MLWS_Vampire ------------------------------------------------------------------------------------------------
    def player_stage(self):  # MLWS_Vampire.psc:21-30
        return self.W.player.vstatus if self.W.player.vampire_kw else 0

    def player_last_fed(self):  # MLWS_Vampire.psc PlayerLastFed: the later of our stamp and LastFeedTime
        at = self.sget(PLAYER, 'MLWS_FedAt', -1.0)
        if self.W.player.last_feed_time > at:
            at = self.W.player.last_feed_time
        return -1.0 if at <= 0.0 else at

    def fed(self, target):  # MLWS_Vampire.psc:45-61 (OnVampireFeed)
        now = self.now()
        victim = self.name(target) if target else ''
        self.sset(PLAYER, 'MLWS_FedAt', now)
        self.sset(PLAYER, 'MLWS_FedVictim', victim)
        for r in self.witnesses_near(target, 2048.0):
            if self.actor(r).asleep:
                self.W.witnessed_asleep.add(r)
            if self.W.player.sneaking and not self.actor(r).detects:
                continue
            self.sset(r, 'MLWS_SawFeedAt', now)
            self.sset(r, 'MLWS_SawFeedVictim', victim)
            self.W.witnessed.add(r)
        t = self.actor(target) if target else None
        if t and not t.dead and t.unique and not t.asleep:  # an awake victim felt the bite
            self.sset(target, 'MLWS_SawFeedAt', now)
            self.sset(target, 'MLWS_SawFeedVictim', 'you')
            self.W.witnessed.add(target)

    def race_switched(self):  # MLWS_Vampire.psc RaceSwitched (the player's form is already set)
        now = self.now()
        if self.W.player.werewolf:
            self.sset(PLAYER, 'MLWS_WolfAt', now)
        elif self.W.player.lord:
            for r in self.witnesses_near(None, 2048.0):
                self.sset(r, 'MLWS_SawLordAt', now)
                self.W.witnessed.add(r)
        elif self.player_stage() == 0:
            self.sset(PLAYER, 'MLWS_CuredAt', now)
            self.W.witnessed = set()   # truth: they saw the vampire the player was, not one they are now
            if self.sget(PLAYER, 'MLWS_FedAt', -1.0) >= 0.0:
                self.sunset(PLAYER, 'MLWS_FedAt')
                self.sunset(PLAYER, 'MLWS_FedVictim')

    def npc_fed(self, ref):  # MLWS_Vampire.psc OnNpcFeed (Vampire Feed Proxy's NpcVampireFeed, sender = feeder)
        self.sset(ref, 'MLWS_BloodAt', self.now())

    def in_sun(self):  # MLWS_Vampire.psc:71-79
        if self.W.player.interior:
            return False
        hour = (self.now() - int(self.now())) * 24.0
        return 7.0 <= hour < 19.0 and self.W.player.weather <= 1

    def masked(self):  # MLWS_Vampire.psc:175-181
        return self.L.better_vampires and self.W.player.masked

    def vampire_facts(self, ref, path, party, now):  # MLWS_Vampire.psc:81-92
        today, player = int(now), self.W.player.name
        self.self_facts(ref, path, party, now, today)
        self.player_facts(ref, path, now, today, player)
        wolf = self.sget(PLAYER, 'MLWS_WolfAt', -1.0)
        if party and wolf >= 0.0 and now - wolf <= 1.0:
            self.set_fact(path, 'fact_surv_wolf', int(wolf), int(wolf) + 1, 2, player + ' changed into a werewolf')
        else:
            self.clear_fact(path, 'fact_surv_wolf')

    def self_facts(self, ref, path, party, now, today):  # MLWS_Vampire.psc:94-122
        if not self.is_vampire(ref):
            for n in ('fact_surv_v_self', 'fact_surv_v_self_sun', 'fact_surv_v_self_hunger'):
                self.clear_fact(path, n)
            return
        pure = self.is_pure_blood(ref)
        self.set_fact(path, 'fact_surv_v_self', -1, -1, 2, 'You are a pure-blood vampire.' if pure else 'You are a vampire.')
        if not pure and self.in_sun():
            self.set_now_fact(path, 'fact_surv_v_self_sun', today, 3, 'You are in daylight, and the sun weakens you.')
        else:
            self.clear_fact(path, 'fact_surv_v_self_sun')
        days = self.days_since(ref, 'MLWS_BloodAt', now) if party else 0
        most = setting_int('follower_hungry_max', 7)
        if days >= setting_int('vampire_hungry_days', 2):
            text = f'You have not fed in over {most} days.' if 'B5' in self.fixed and days > most else f'You have not fed in {days} days.'
            self.set_now_fact(path, 'fact_surv_v_self_hunger', today, 3, text)
        else:
            self.clear_fact(path, 'fact_surv_v_self_hunger')

    def player_facts(self, ref, path, now, today, player):  # MLWS_Vampire.psc:124-172
        stage = self.player_stage()
        shared = 'B1' in self.fixed and not self.actor(ref).unique
        is_close = stage > 0 and not shared and self.is_close(ref)
        cured = self.sget(PLAYER, 'MLWS_CuredAt', -1.0)
        saw_at, lord_at = self.sget(ref, 'MLWS_SawFeedAt', -1.0), self.sget(ref, 'MLWS_SawLordAt', -1.0)
        saw_feed = stage > 0 and not shared and saw_at >= 0.0 and saw_at >= cured
        saw_old = not shared and 0.0 <= saw_at < cured
        saw_lord = stage > 0 and not shared and lord_at >= 0.0 and lord_at >= cured
        witness = saw_feed or saw_lord
        knows = is_close or witness
        if knows:
            self.set_fact(path, 'fact_surv_v_player', -1, -1, 2, f'{player} is a vampire.')
        else:
            self.clear_fact(path, 'fact_surv_v_player')
        if saw_feed or saw_old:
            self.set_fact(path, 'fact_surv_v_saw', int(saw_at), -1, 2, self.saw_text(player, self.sget(ref, 'MLWS_SawFeedVictim', ''), saw_old))
        else:
            self.clear_fact(path, 'fact_surv_v_saw')
        if saw_lord:
            self.set_fact(path, 'fact_surv_v_saw_lord', int(lord_at), -1, 2, f'You saw {player} turn into a Vampire Lord')
        else:
            self.clear_fact(path, 'fact_surv_v_saw_lord')
        fed = self.player_last_fed()
        if is_close and fed >= 0.0:
            victim = self.sget(PLAYER, 'MLWS_FedVictim', '')
            if victim and self.sget(PLAYER, 'MLWS_FedAt', -1.0) >= fed:
                self.set_fact(path, 'fact_surv_v_fed', int(fed), -1, 2, f'{player} last fed, on {victim}')
            else:
                self.set_fact(path, 'fact_surv_v_fed', int(fed), -1, 2, f'{player} last fed')
        else:
            self.clear_fact(path, 'fact_surv_v_fed')
        if knows and stage >= 3:
            self.set_now_fact(path, 'fact_surv_v_hunger', today, 3, f'{player} is hungry for blood.')
        else:
            self.clear_fact(path, 'fact_surv_v_hunger')
        if knows and self.in_sun():
            self.set_now_fact(path, 'fact_surv_v_sun', today, 3, f'The sun weakens {player} here.')
        else:
            self.clear_fact(path, 'fact_surv_v_sun')
        if stage >= setting_int('visible_stage', 4) and not self.masked() and not self.W.player.hooded:
            self.set_now_fact(path, 'fact_surv_v_signs', today, 3, f'{player} has burning eyes, sunken skin and fangs.')
        else:
            self.clear_fact(path, 'fact_surv_v_signs')

    @staticmethod
    def saw_text(player, victim, old):  # MLWS_Vampire.psc SawText
        past = ', when they were a vampire' if old else ''
        if victim == 'you':
            return f'{player} once fed on you{past}' if old else f'{player} fed on you'
        on = f' on {victim}' if victim else ''
        return f'You once saw {player} feed{on}{past}' if old else f'You saw {player} feed{on}'

    # --- MLWS_Actions ------------------------------------------------------------------------------------------------
    def knows_one(self, ref):  # MLWS_Actions.psc KnowsOne: unique NPCs only
        return self.actor(ref).unique and (self.is_close(ref) or self.saw_vampire(ref))

    def knows_player_vampire(self, ref, talk):  # MLWS_Actions.psc:171-174; B2: every NPC in the talk must know
        if 'B2' not in self.fixed:
            return self.knows_one(ref)
        return all(self.knows_one(r) for r in [ref] + [r for r in talk if r != ref])

    def usable(self, ref):  # MLWS_Actions.psc:176-178
        a = self.actor(ref)
        return a is not None and not a.dead and not a.combat

    def share_food(self, ref, direction, talk):  # MLWS_Actions.psc:65-98
        if not self.usable(ref):
            return 'Nobody could share food just now.'
        name, now = self.name(ref), self.now()
        if not self.is_party(ref):
            return f'{name} is not travelling with {self.W.player.name}.'
        if now - self.sget(ref, 'MLWS_SharedAt', -1000.0) < 0.02:
            return f'{name} shared food moments ago; nothing more changed hands.'
        giver, taker = (PLAYER, ref) if direction == 'player_gives' else (ref, PLAYER)
        blood = self.is_vampire(taker)
        if blood and taker == PLAYER and not self.knows_player_vampire(ref, talk):
            blood = False
        item = self.pick_food(giver, blood)
        if item is None:
            if blood:
                return f'{self.name(giver)} has no blood to give, and {self.name(taker)} has no use for anything else.'
            return f'{self.name(giver)} has no food to give.'
        self.inventory(giver).remove(item)
        self.inventory(taker).append(item)
        self.record(taker, item.name, self.food_flags(item), True)
        self.eat(taker, item)
        self.sset(ref, 'MLWS_SharedAt', now)
        self.food_moved.append((giver, taker, self.oracle_party(ref)))
        self.write(ref)
        return f'{self.name(giver)} gave {item.name} to {self.name(taker)}, who ate it.'

    def eat_this(self, ref, talk):  # MLWS_Actions.psc:100-141
        player = self.W.player.name
        if not self.usable(ref):
            return 'Nobody could hand over food just now.'
        if not self.is_party(ref):
            return f'{self.name(ref)} is not travelling with {player}.'
        if self.is_vampire(PLAYER) and self.knows_player_vampire(ref, talk):
            return f'{player} has no need of food.'
        name, now = self.name(ref), self.now()
        if now - self.sget(ref, 'MLWS_SharedAt', -1000.0) < 0.02:
            return f'{name} shared food moments ago; {player} did not eat again.'
        smi = self.L.smi and self.survival_on()
        hunger = self.stage(0)
        if 0 <= hunger < 2:
            return f'{player} is not hungry and did not eat.'
        giver, item = ref, self.pick_food(ref, False)
        if item is None:
            giver, item = PLAYER, self.pick_food(PLAYER, False)
        if item is None:
            return f'Neither {name} nor {player} has any food.'
        self.record(PLAYER, item.name, self.food_flags(item), not smi)
        self.inventory(giver).remove(item)
        if smi:
            self.W.player.needs[0] = max(0.0, self.W.player.needs[0] - setting_float('eat_this_hunger', 80.0))
        else:
            self.eat(PLAYER, item, in_pack=False)
        self.sset(ref, 'MLWS_SharedAt', now)
        self.food_moved.append((giver, PLAYER, self.oracle_party(ref)))
        self.write(ref)
        return f'{player} ate {item.name} at {name}\'s urging.'

    def warm_you(self, ref):  # MLWS_Actions.psc:143-169
        player = self.W.player.name
        if not self.usable(ref):
            return 'Nobody could conjure warmth just now.'
        name = self.name(ref)
        if not self.actor(ref).fire:
            return f'{name} knows no fire spell and conjured no warmth.'
        if not self.L.smi or not self.survival_on():
            return f'{name} conjured no warmth: it would change nothing here.'
        if self.stage(1) < 2:
            return f'{player} is not cold; {name} conjured no warmth.'
        now = self.now()
        if now - self.sget(ref, 'MLWS_WarmedAt', -1000.0) < 0.1:
            return f'{name} warmed {player} moments ago and cannot do more yet.'
        self.W.player.needs[1] = max(0.0, self.W.player.needs[1] - setting_float('warm_you_cold', 150.0))
        self.sset(ref, 'MLWS_WarmedAt', now)
        self.write(ref)
        return f'{name} conjured flames and warmed {player}.'

    def actions_facts(self, ref, path, party, now):  # MLWS_Actions.psc:185-188
        self.file(path)['int']['surv_warm'] = int(self.L.smi and self.survival_on() and self.actor(ref).fire)

    # --- the game: eating (an equip, so the native's event follows) --------------------------------------------------
    def eat(self, ref, item, in_pack=True):
        inv = self.inventory(ref)
        if in_pack and item in inv:
            inv.remove(item)
        if ref == PLAYER and self.L.survival and self.survival_on():
            self.W.player.needs[0] = max(0.0, self.W.player.needs[0] - item.hunger)
        if item.blood and ref == PLAYER and self.W.player.vampire_kw:
            self.vampire_fed_game()
        self.L.real += 0.5
        self.on_equip(ref, item)

    def vampire_fed_game(self):  # what PlayerVampireQuestScript does on feeding: status 1, LastFeedTime
        self.W.player.vstatus = 1
        self.W.player.last_feed_time = self.now()

    # --- checks ------------------------------------------------------------------------------------------------------
    def check_commit(self, path, staged, gone, kept):
        r = self.rep
        cap = setting_int('max_facts', 6)
        f = self.file(path)['string']
        in_file = [k for k in f if k.startswith('fact_surv_')]
        r.count('commits')
        if len(in_file) > cap:
            r.fail('cap', f'{len(in_file)} facts in {path}')
        expected = [n for n, v in sorted(staged, key=lambda nv: -self.priority_of(nv[1]))][:cap]
        if set(in_file) != set(expected):
            r.fail('priority order', f'kept {sorted(in_file)} expected {sorted(expected)}')
        staged_names = {n for n, _ in staged}
        foreign = set(in_file) - staged_names
        if foreign:
            r.fail('no foreign facts after a write', f'{sorted(foreign)} in {path}')
        if staged_names & set(gone):
            r.fail('a fact both set and cleared', sorted(staged_names & set(gone)))
        missing = ALL_FACTS - staged_names - set(gone)
        if missing:  # with PathMembers unreadable, only the staged and cleared names are removed
            r.fail('every fact name staged or cleared', sorted(missing))
        for n, v in staged:
            self.check_expiry(n, v)
            self.check_text(n, v.split('|', 3)[3])
            if 'Victim Damage' in v:
                r.fail('ignored diseases never named', v)

    NOW = {'fact_surv_hunger', 'fact_surv_cold', 'fact_surv_tired', 'fact_surv_warming', 'fact_surv_weather',
           'fact_surv_hungry', 'fact_surv_supplies', 'fact_surv_road', 'fact_surv_rest', 'fact_surv_v_self_sun',
           'fact_surv_v_self_hunger', 'fact_surv_v_hunger', 'fact_surv_v_sun', 'fact_surv_v_signs'}
    LASTING = {'fact_surv_fav_player', 'fact_surv_fav_self', 'fact_surv_best_bed', 'fact_surv_v_self', 'fact_surv_v_player'}
    DATED = {'fact_surv_v_saw', 'fact_surv_v_saw_lord', 'fact_surv_v_fed'}
    DATED_FOR = {'fact_surv_meal': 2, 'fact_surv_food_player': 2, 'fact_surv_food_self': 2, 'fact_surv_bed': 1, 'fact_surv_wolf': 1}

    def check_expiry(self, name, value):
        day, exp, _, _ = value.split('|', 3)
        day, exp, today = int(day), int(exp), int(self.now())
        base = re.sub(r'^fact_surv_(player|self)_', 'fact_surv_X_', name)
        if name in self.NOW or base == 'fact_surv_X_':
            ok = day == -1 and exp == today
        elif base.startswith('fact_surv_X_'):
            ok = day == -1 and exp == today
        elif name in self.LASTING:
            ok = day == -1 and exp == -1
        elif name in self.DATED:
            ok = 0 <= day <= today and exp == -1
        elif name in self.DATED_FOR:
            ok = 0 <= day <= today and exp == day + self.DATED_FOR[name]
        else:
            ok = False
        self.rep.count('facts checked for expiry')
        if not ok:
            self.rep.fail('expiry as designed', f'{name}={value}')
        # the Hub keeps it exactly while it should apply
        last_day = today if exp == today else exp
        if exp >= 0 and (game_facts({name: value}, last_day) == [] or game_facts({name: value}, last_day + 1) != []):
            self.rep.fail('Hub drops it the day after it expires', f'{name}={value}')

    def check_text(self, name, text):
        r = self.rep
        for m in re.finditer(r'(not eaten|not slept|not fed) in (over )?(-?\d+) days', text):
            n, over = int(m.group(3)), bool(m.group(2))
            if n < 0 or (n > setting_int('follower_hungry_max', 7) and not over):
                r.fail('counters sane: days stated within the cap', text)
        for m in re.finditer(r'gone (-?\d+) days', text):
            if int(m.group(1)) < 0:
                r.fail('counters sane: road days', text)
        for m in re.finditer(r', (-?\d+) hours|only (-?\d+) hours', text):
            n = int(m.group(1) or m.group(2))
            if n < 1 or n > 24:
                r.fail('counters sane: hours slept 1-24', text)
        if name == 'fact_surv_warming' and self.stage(1) >= 3:
            r.fail('warming written while still very cold or worse', f'{text} (cold stage {self.stage(1)})')

    def check_counters(self):
        r = self.rep
        for (owner, key), v in self.W.store.items():
            if key == 'mlws_drinks' and len(v) > 50:
                r.fail('counters sane: drinks list bounded', len(v))
            if key == 'mlws_foodnames' and len(v) > 40:
                r.fail('counters sane: food names <= 40', len(v))
            if key == 'mlws_foodcounts':
                names = self.W.store.get((owner, 'mlws_foodnames'), [])
                if len(v) != len(names) or any(c < 1 for c in v):
                    r.fail('counters sane: food names and counts parallel', (len(names), len(v)))
            if key in ('mlws_bedhours', 'mlws_besthours') and not 0 <= v <= 24:
                r.fail('counters sane: bed hours', v)
            if key == 'mlws_bestscore' and not 0 <= v <= 650:
                r.fail('counters sane: best bed score', v)
            if key == 'mlws_bestkind' and v < 2:
                r.fail('best bed is a bed or bedroll', v)
            if key == 'mlws_foodname' and any(d.name == v for d in DRINKS):
                r.fail('a drink is never the last food', v)
        for giver, taker, party in self.food_moved:  # standing as it was at the action
            npc = taker if giver == PLAYER else giver
            if not party:
                r.fail('ShareFood/EatThis only with party members', self.name(npc))
        self.food_moved.clear()
        if self.W.witnessed_asleep:
            r.fail('sleepers are no witnesses', sorted(self.name(x) for x in self.W.witnessed_asleep))
            if key == 'mlws_bedhours' and owner in self.W.sleep_truth and v != int(self.W.sleep_truth[owner] + 0.5):
                r.fail('counters sane: hours recorded as slept', f'slept {self.W.sleep_truth[owner]} h, recorded {v}')
        if self.W.armed is not None and any(s < 0 or s > 5 for s in self.W.last_stage):
            r.fail('counters sane: need stage 0-5', self.W.last_stage)

    def oracle_party(self, ref):  # README: party members; summons and raised thralls are not
        a = self.actor(ref)
        return (a.teammate or a.follower_rank >= 0) and not a.commanded

    def oracle_close(self, ref):
        a = self.actor(ref)
        return self.oracle_party(ref) and (a.rank >= setting_int('close_rank', 2) or (self.L.arousal and self.sget(ref, 'MLW_IsClose', 0) > 0)
                                           or (self.L.relationships and self.sget(ref, 'MRB_Close', 0) > 0))

    def may_know(self, ref):
        return self.player_stage() > 0 and (self.oracle_close(ref) or ref in self.W.witnessed)

    VAMPIRE_FACTS = ('fact_surv_v_player', 'fact_surv_v_saw', 'fact_surv_v_saw_lord', 'fact_surv_v_fed', 'fact_surv_v_hunger', 'fact_surv_v_sun')
    PAST = ', when they were a vampire'  # a memory of a cured vampire says the player is not one now

    def check_hub_read(self, ref):
        """What the Hub would give this speaker: their base record's file, read with its own reader."""
        r = self.rep
        f = self.file(self.npc_file(ref))['string']
        rows = game_facts(f, int(self.now()))
        r.count('hub reads')
        texts = {row['text'] for row in rows}
        player = self.W.player.name
        for n in self.VAMPIRE_FACTS:
            if n in f and f[n].split('|', 3)[3] in texts and not f[n].endswith(self.PAST) and not self.may_know(ref):
                r.fail('vampire: no fact to an NPC who should not know' + self.cause(ref), f'{n} -> {self.name(ref)} ({self.who(ref)})')
        if 'fact_surv_v_signs' in f and f['fact_surv_v_signs'].split('|', 3)[3] in texts:
            if self.player_stage() < setting_int('visible_stage', 4) or self.masked() or self.W.player.hooded:
                r.fail('vampire: signs only from the visible stage, unmasked', f'stage {self.player_stage()}')
        for t in texts:
            for other in OTHER_NAMES - {player}:
                if re.search(r'\b%s\b' % re.escape(other), t):
                    r.fail('no fact from another save', f'{t!r} read in {player}\'s save')

    def cause(self, ref):
        a = self.actor(ref)
        if a.commanded:
            return ' [summon]'
        if not a.unique and not self.knows_one(ref):
            return ' [shares the record with one who knows]'
        return ' [other]'

    def who(self, ref):
        a = self.actor(ref)
        return (f"party={self.oracle_party(ref)} close={self.oracle_close(ref)} witness={ref in self.W.witnessed} "
                f"summon={a.commanded} unique={a.unique} stage={self.player_stage()}")

    GIVEAWAY = re.compile(r'has no need of food|has no blood to give, and (?P<who>.+?) has no use|gave (Potion of Blood) to (?P<taker>.+?), who')

    def check_lines(self, talk):
        """Action lines go to the whole talk: one that gives a vampire player away must be fine for everyone in it."""
        player = self.W.player.name
        for line in self.lines:
            m = self.GIVEAWAY.search(line)
            if not m:
                continue
            about_player = 'no need of food' in line or m.group('who') == player or m.group('taker') == player
            if about_player:
                for ref in talk:
                    if not self.may_know(ref):
                        why = self.cause(ref) if ref == talk[0] else ' [another NPC in the talk]'
                        self.rep.fail('vampire: no action line to an NPC who should not know' + why, f'{line!r} heard by {self.name(ref)} ({self.who(ref)})')


OTHER_NAMES = set()


class Report:
    def __init__(self):
        self.fails, self.counts, self.examples = {}, {}, {}

    def fail(self, check, detail):
        self.fails[check] = self.fails.get(check, 0) + 1
        self.examples.setdefault(check, str(detail)[:240])

    def count(self, what, n=1):
        self.counts[what] = self.counts.get(what, 0) + n


# ---------------------------------------------------------------------------------------------------------------------
# Random days of play
# ---------------------------------------------------------------------------------------------------------------------

def roster():
    A = Actor
    return [
        A(0x0A2C94, 0x0A2C8E, 'Lydia', rank=random.choice([1, 3])),
        A(0x02002B74, 0x02002B6C, 'Serana', vampire_kw=True, pure_base=True, rank=2),
        A(0x01BCA7, 0x01BCA4, "J'zargo", race='Khajiit', fire=True),
        A(0x0B997F, 0x0B9986, 'Marcurio', race='Imperial', fire=True, rank=1),
        A(0x0FE0101, 0x0FE0100, 'Hired Sword', unique=False),        # two refs, one record: one npc file
        A(0x0FE0102, 0x0FE0100, 'Hired Sword', unique=False),
        A(0x01A672, 0x01A66B, 'Belethor'),
        A(0x0E5401, 0x0E5400, 'Whiterun Guard', unique=False),
        A(0x0E5402, 0x0E5400, 'Whiterun Guard', unique=False),
        A(0x0E5403, 0x0E5400, 'Whiterun Guard', unique=False),
        A(0x0F0001, 0x0F0000, 'Vampire Fledgling', unique=False, vampire_kw=True),
        A(0xFF000801, 0x0204C9, 'Flame Atronach', unique=False, commanded=True),
        A(0xFF000802, 0x016F00, 'Dremora', unique=False, commanded=True),
    ]


FOLLOWERS = (0x0A2C94, 0x02002B74, 0x01BCA7, 0x0B997F, 0x0FE0101, 0x0FE0102)
SUMMONS = (0xFF000801, 0xFF000802)


def play_day(s, rng, style):
    W = s.W
    for _ in range(rng.randint(5, 12)):
        roll = rng.random()
        if roll < 0.22:
            travel(s, rng, rng.uniform(0.5, 4.0))
        elif roll < 0.34:
            if style != 'starve':
                for _ in range(rng.randint(1, 4 if style == 'glutton' else 1)):
                    s.eat(PLAYER, rng.choice(FOODS + (BLOOD if W.player.vampire_kw else [])))
        elif roll < 0.40:
            for _ in range(rng.randint(1, 4)):
                s.eat(PLAYER, rng.choice(DRINKS))
                travel(s, rng, 0.2)
        elif roll < 0.46:
            party = [r for r in FOLLOWERS if s.actor(r).teammate]
            if party:
                r = rng.choice(party)
                s.eat(r, rng.choice(FOODS + DRINKS + (BLOOD if s.actor(r).vampire_kw else [])))
        elif roll < 0.54:
            sleep(s, rng)
        elif roll < 0.68:
            talk(s, rng)
        elif roll < 0.74:
            follower_change(s, rng)
        elif roll < 0.78:
            for r in SUMMONS:
                a = s.actor(r)
                a.teammate = rng.random() < 0.5
                a.dead = not a.teammate
                a.distance = rng.uniform(100, 900)
                a.rank = rng.choice([0, 0, 2])
        elif roll < 0.83:
            vampire_event(s, rng)
        elif roll < 0.86:
            W.player.health = rng.choice([0.1, 0.4, 0.8, 1.0])
            W.player.diseases = rng.sample(DISEASES + [SANGUINARE], rng.randint(0, 2))
        elif roll < 0.88:
            W.player.werewolf = True
            s.sset(PLAYER, 'MLWS_WolfAt', s.now())  # MLWS_Vampire.psc:63-68
        elif roll < 0.92:
            W.player.needs[1] = max(0.0, W.player.needs[1] - rng.uniform(50, 300))  # warmed by a fire
            travel(s, rng, 0.1)
        else:
            W.player.inventory += [rng.choice(FOODS + DRINKS) for _ in range(rng.randint(0, 6))]
    s.check_counters()


def travel(s, rng, hours):
    """Time passes; Condition.Check runs every 30 real seconds (10 game minutes at timescale 20)."""
    W = s.W
    W.player.interior = rng.random() < 0.4
    W.player.weather = rng.choice([0, 0, 1, 2, 3, 3])
    W.player.combat = rng.random() < 0.08
    W.player.sneaking = rng.random() < 0.08
    steps = max(1, int(hours * 6))
    for _ in range(steps):
        W.time += 1 / 144
        s.L.real += 30.0
        if s.survival_on():
            p = W.player.needs
            p[0] += 4.0 if not W.player.vampire_kw else 0.0
            p[1] = max(0.0, p[1] + (-15 if W.player.interior else 12 if W.player.weather == 3 else 2))
            p[2] += 3.0
        progress_vampire(s)
        for a in W.actors.values():
            if rng.random() < 0.05:
                a.distance = rng.choice([200.0, 800.0, 1400.0, 3000.0, 6000.0])
        s.check()
    s.lines.clear()


def progress_vampire(s):  # PlayerVampireQuestScript.OnUpdateGameTime, lines 49-104
    p = s.W.player
    if not p.vampire_kw:
        return
    timer = s.now() - p.last_feed_time
    if timer >= 3 and p.vstatus == 3:
        p.vstatus = 4
    elif timer >= 2 and p.vstatus == 2:
        p.vstatus = 3
    elif timer >= 1 and p.vstatus == 1:
        p.vstatus = 2


def sleep(s, rng):
    W = s.W
    kind = rng.choice([None, None, 2, 3, 4, 5, 6])
    if kind is None and rng.random() < 0.5:
        s.sat(rng.choice([2, 4]))   # sat on a bed just before sleeping
        W.time += 0.005
    hours = rng.choice([0.1, 1, 2, 3, 5, 8, 10])
    s.sleep_start(kind, rng.choice(PLACES))
    W.time += hours / 24.0
    s.L.real += 5
    if hours >= 0.25:
        for r in W.sharers or []:
            W.sleep_truth[r] = hours
        W.sleep_truth[PLAYER] = hours
    W.player.needs[2] = 0.0
    s.sleep_stop()
    progress_vampire(s)
    s.check()


def follower_change(s, rng):
    a = s.actor(rng.choice(FOLLOWERS))
    joining = not a.teammate
    a.teammate = joining
    a.follower_rank = 0 if joining and rng.random() < 0.8 else -1
    if not joining and rng.random() < 0.3:
        a.follower_rank = 0  # some follower frameworks leave the faction rank behind
    a.distance = rng.uniform(150, 1200) if joining else 8000.0
    a.rank = rng.choice([0, 1, 2, 3, 4])
    if rng.random() < 0.3:
        s.sset(a.ref, 'MLW_IsClose', rng.choice([0, 1, 2]))
    if rng.random() < 0.2:
        s.sset(a.ref, 'MRB_Close', rng.choice([0, 1]))
    if joining:
        s.W.party_since[a.ref] = s.now()
    a.inventory = [rng.choice(FOODS + DRINKS + BLOOD) for _ in range(rng.randint(0, 4))]


def vampire_event(s, rng):
    W = s.W
    p = W.player
    r = rng.random()
    if not p.vampire_kw and r < 0.5:
        p.vampire_kw, p.vstatus, p.last_feed_time = True, 1, s.now()   # PlayerVampireQuestScript.VampireChange
    elif p.vampire_kw and r < 0.8:
        victim = rng.choice([a for a in W.actors.values() if not a.commanded])
        W.player.sneaking = rng.random() < 0.3
        for a in W.actors.values():
            a.los = rng.random() < 0.4
            a.asleep = rng.random() < 0.3
            a.detects = rng.random() < 0.7
            if rng.random() < 0.3:
                a.distance = rng.choice([300.0, 1500.0, 2500.0])
        s.vampire_fed_game()
        s.fed(victim.ref)
    elif p.vampire_kw and r < 0.9:
        p.lord = True          # Vampire Lord and back
        s.race_switched()
        p.lord = False
    elif p.vampire_kw:
        p.vampire_kw = False   # cured; VampireStatus is left as it was
        s.race_switched()
    if rng.random() < 0.3:
        s.npc_fed(0x02002B74)  # Serana, through Vampire Feed Proxy
    p.masked = rng.random() < 0.3
    p.hooded = rng.random() < 0.3


def talk(s, rng):
    W = s.W
    pool = [a.ref for a in W.actors.values() if not a.dead and a.distance < 3000]
    if not pool:
        return
    members = rng.sample(pool, min(len(pool), rng.randint(1, 3)))
    W.talk_running = True
    s.lines = []
    order = members[:]
    rng.shuffle(order)
    # MantellaConversation_NPC_Added for each; two refs of one record may run their writes at the same time
    twins = [(a, b) for a, b in itertools.combinations(order, 2) if s.actor(a).base == s.actor(b).base]
    if twins and rng.random() < 0.5:
        a, b = twins[0]
        rest = [r for r in order if r not in (a, b)]
        for r in rest:
            s.write(r)
        path = s.write(a, interleave_with=b)   # a's jobs, then b's jobs into the same staging lists, then one commit
        s.condition_facts(b, path, s.is_party(b), s.now())
        s.food_facts(b, path, s.is_party(b), s.now())
        s.beds_facts(b, path, s.is_party(b), s.now())
        s.vampire_facts(b, path, s.is_party(b), s.now())
        s.actions_facts(b, path, s.is_party(b), s.now())
        staged_names = s.slist(None, 'MLWS_FactName' + path)
        values = s.slist(None, 'MLWS_FactValue' + path)
        gone = [n for n in s.slist(None, 'MLWS_FactGone' + path) if n not in staged_names]
        s.W.store[(None, ('MLWS_FactGone' + path).lower())] = gone
        dedup = dict()
        for n, v in zip(list(staged_names), list(values)):
            dedup.setdefault(n, v)
        s.W.store[(None, ('MLWS_FactName' + path).lower())] = list(dedup)
        s.W.store[(None, ('MLWS_FactValue' + path).lower())] = list(dedup.values())
        s.rep.count('interleaved writes')
        s.commit(path)
    else:
        for r in order:
            s.write(r)
    for r in members:
        s.check_hub_read(r)
    # actions, by party members and anyone the gate lets through in the model
    for r in members:
        x = rng.random()
        if x < 0.25:
            s.send(s.share_food(r, rng.choice(['npc_gives', 'player_gives']), members))
        elif x < 0.40:
            s.send(s.eat_this(r, members))
        elif x < 0.50:
            s.send(s.warm_you(r))
    s.check_lines(members)
    W.talk_running = False
    s.lines = []


def run_random(seed, days, fixed, rep):
    rng = random.Random(seed)
    random.seed(seed)
    files = {}
    chars = ['Vega', 'Nyri']
    OTHER_NAMES.update(chars)
    base = roster()
    saves = {c: [World(c, base)] for c in chars}
    styles = {'Vega': 'glutton', 'Nyri': 'starve'}
    day = 0
    while day < days:
        char = rng.choice(chars)
        launch = Launch(survival=rng.random() < 0.85, smi=rng.random() < 0.6, hub=True, better_vampires=rng.random() < 0.5)
        launch.path_members = rng.random() < 0.8
        rep.count(f"launches survival={launch.survival} smi={launch.smi}")
        world = copy.deepcopy(rng.choice(saves[char][-3:]))   # load one of the last saves
        if rng.random() < 0.2:
            world.player.survival_on = not world.player.survival_on
        s = Sim(launch, world, files, fixed, rep)
        for _ in range(rng.randint(2, 10)):
            play_day(s, rng, styles[char])
            day += 1
            if rng.random() < 0.5:
                saves[char].append(copy.deepcopy(world))
        saves[char].append(copy.deepcopy(world))
        check_warnings(s, rep)
    rep.count('days played', days)


def check_warnings(s, rep):
    by_need = {}
    for t, need, ref, commanded, party in s.W.warnings:   # standing as it was when the line was given
        rep.count('warnings')
        if commanded:
            rep.fail('warning never from a summon', s.name(ref))
        if not party:
            rep.fail('warning from a party member', s.name(ref))
        last = by_need.get(need)
        if last is not None and t - last < setting_float('critical_cooldown_days', 3.0) - 1e-4:
            rep.fail('warning not twice inside its cooldown (same need)', f'need {need} at {last:.3f} and {t:.3f}')
        by_need[need] = t
    times = sorted(w[0] for w in s.W.warnings)
    for a, b in zip(times, times[1:]):
        if b - a < setting_float('critical_cooldown_days', 3.0):
            rep.count('warnings of different needs inside 3 days (by design: one cooldown per need)')


# ---------------------------------------------------------------------------------------------------------------------
# Exhaustive: who may hear that the player is a vampire
# ---------------------------------------------------------------------------------------------------------------------

KINDS = ('stranger', 'teammate', 'faction only', 'summon')


def make_npc(ref, base, kind, rank, isclose, mrb, unique):
    a = Actor(ref, base, 'Guard' if not unique else 'Ralof', unique=unique, rank=rank)
    a.teammate = kind in ('teammate', 'summon')
    a.follower_rank = 0 if kind == 'faction only' else -1
    a.commanded = kind == 'summon'
    a.inventory = [Item('Apple'), BLOOD[0]]
    return a, {'MLW_IsClose': isclose, 'MRB_Close': mrb}


def exhaustive_vampire(fixed, rep):
    """Every combination of the player's stage, mask, sun and feeding, and of one NPC's standing, closeness and witness;
    alone, with a second NPC of the same record (with its own standing), or with a stranger; both write orders and
    interleaved writes. After the writes, each NPC's Hub read and the action lines heard are checked."""
    npc_space = list(itertools.product(KINDS, (0, 1, 2, 4), (0, 1, 2), (0, 1), (False, True)))  # kind rank close mrb witness
    # the second NPC of the same record: every kind and witness, rank below/at close_rank, MLW_IsClose off/on
    small = [c for c in npc_space if c[1] in (0, 2) and c[2] in (0, 1) and c[3] == 0]
    twins = [('twin', o, order) for o in small for order in ('ab', 'ba', 'mix')]
    combos = 0
    for stage, masked, sun, fed_known, unique in itertools.product(range(5), (False, True), (False, True), (False, True), (True, False)):
        # who knows does not depend on mask, sun or feeding; the twin cases run with every fact switched on
        with_twins = not unique and not masked and sun and fed_known
        for me in npc_space:
            for company in [None, 'stranger'] + (twins if with_twins else []):
                combos += 1
                launch = Launch(survival=True, smi=True, better_vampires=True)
                W = World('Vega', [])
                W.time = 120.5 if sun else 120.95
                W.player.weather = 0
                W.player.vampire_kw, W.player.vstatus = stage > 0, max(stage, 1 if stage else 0)
                W.player.masked = masked
                s = Sim(launch, W, {}, fixed, rep)
                a, extra = make_npc(0x100, 0x500, me[0], me[1], me[2], me[3], unique)
                W.actors[a.ref] = a
                for k, v in extra.items():
                    s.sset(a.ref, k, v)
                if me[4]:
                    s.sset(a.ref, 'MLWS_SawFeedAt', 118.0)
                    s.sset(a.ref, 'MLWS_SawFeedVictim', 'Ysolda')
                    W.witnessed.add(a.ref)
                if fed_known:
                    W.player.last_feed_time = 119.0
                    s.sset(PLAYER, 'MLWS_FedAt', 119.0)
                    s.sset(PLAYER, 'MLWS_FedVictim', 'Ysolda')
                members = [a.ref]
                if company == 'stranger':
                    b, _ = make_npc(0x101, 0x501, 'stranger', 0, 0, 0, True)
                    W.actors[b.ref] = b
                    members.append(b.ref)
                    s.write(a.ref)
                    s.write(b.ref)
                elif company:
                    _, o, order = company
                    b, extra = make_npc(0x101, 0x500, o[0], o[1], o[2], o[3], False)
                    W.actors[b.ref] = b
                    for k, v in extra.items():
                        s.sset(b.ref, k, v)
                    if o[4]:
                        s.sset(b.ref, 'MLWS_SawFeedAt', 118.0)
                        s.sset(b.ref, 'MLWS_SawFeedVictim', 'Ysolda')
                        W.witnessed.add(b.ref)
                    members.append(b.ref)
                    if order == 'ab':
                        s.write(a.ref)
                        s.write(b.ref)
                    elif order == 'ba':
                        s.write(b.ref)
                        s.write(a.ref)
                    else:
                        path = s.write(a.ref, interleave_with=b.ref)
                        s.vampire_facts(b.ref, path, s.is_party(b.ref), s.now())
                        names = s.slist(None, 'MLWS_FactName' + path)
                        values = s.slist(None, 'MLWS_FactValue' + path)
                        dedup = {}
                        for n, v in zip(list(names), list(values)):
                            dedup.setdefault(n, v)
                        s.W.store[(None, ('MLWS_FactName' + path).lower())] = list(dedup)
                        s.W.store[(None, ('MLWS_FactValue' + path).lower())] = list(dedup.values())
                        gone = [n for n in s.slist(None, 'MLWS_FactGone' + path) if n not in dedup]
                        s.W.store[(None, ('MLWS_FactGone' + path).lower())] = gone
                        s.commit(path)
                else:
                    s.write(a.ref)
                for r in members:
                    s.check_hub_read(r)
                # the two lines that can give the player away, by the first NPC, heard by everyone in the talk
                s.lines = []
                W.player.inventory = []
                s.sset(a.ref, 'MLWS_SharedAt', -1000.0)
                s.send(s.share_food(a.ref, 'npc_gives', members))
                s.sset(a.ref, 'MLWS_SharedAt', -1000.0)
                a.inventory = [Item('Apple')]  # no blood in the pack: the refusal line
                s.send(s.share_food(a.ref, 'npc_gives', members))
                s.sset(a.ref, 'MLWS_SharedAt', -1000.0)
                s.send(s.eat_this(a.ref, members))
                s.check_lines(members)
    rep.count('exhaustive vampire combinations', combos)


# ---------------------------------------------------------------------------------------------------------------------
# Single cases: the 2026-11-08 vampire and closeness fixes, one at a time
# ---------------------------------------------------------------------------------------------------------------------

def vampire_cases(rep):
    def setup(**launch):
        W = World('Vega', [])
        W.time = 20.95  # night: no sun facts
        W.player.vampire_kw, W.player.vstatus = True, 2
        s = Sim(Launch(**launch), W, {}, set(FIXED), rep)
        spouse = Actor(0x100, 0x500, 'Lydia', teammate=True, rank=4)
        stranger = Actor(0x101, 0x501, 'Ysolda')
        guard = Actor(0x102, 0x502, 'Hulda')
        for a in (spouse, stranger, guard):
            W.actors[a.ref] = a
        return s, W

    def facts(s, ref):
        s.write(ref)
        return s.file(s.npc_file(ref))['string']

    def case(name, ok, detail=''):
        rep.count('single cases')
        if not ok:
            rep.fail('case: ' + name, detail)

    # VMP-1: bottled blood after a feeding: the spouse hears of the later feeding, without the old victim
    s, W = setup()
    W.time = 10.95
    s.vampire_fed_game()
    s.fed(0x101)
    W.time = 20.95
    s.record(PLAYER, 'Blood Potion', 4)
    f = facts(s, 0x100).get('fact_surv_v_fed', '')
    case('bottled blood is the last feeding, no old victim', f.startswith('20|') and 'Ysolda' not in f, f)

    # VMP-1: a feeding that moved only LastFeedTime (no event) is still the later one
    s, W = setup()
    W.time = 10.95
    s.vampire_fed_game()
    s.fed(0x101)
    W.time = 20.95
    s.vampire_fed_game()
    f = facts(s, 0x100).get('fact_surv_v_fed', '')
    case('a later LastFeedTime wins, without naming the old victim', f.startswith('20|') and 'Ysolda' not in f, f)

    # VMP-2: an awake NPC in sight who has not detected the sneaking player is no witness
    s, W = setup()
    W.player.sneaking = True
    W.actors[0x102].detects = False
    s.fed(0x101)
    case('an NPC who did not detect the player is no witness', 'fact_surv_v_player' not in facts(s, 0x102))
    W.actors[0x102].detects = True
    s.fed(0x101)
    case('an NPC who detected the player is a witness', 'fact_surv_v_player' in facts(s, 0x102))

    # VMP-3: an awake unique victim knows; a sleeping one does not
    s, W = setup()
    W.actors[0x102].los = False
    s.fed(0x101)
    f = facts(s, 0x101)
    case('an awake victim knows', f.get('fact_surv_v_saw', '').endswith('|Vega fed on you') and 'fact_surv_v_player' in f, f)
    s, W = setup()
    W.actors[0x101].asleep = True
    s.fed(0x101)
    case('a sleeping victim does not know', 'fact_surv_v_player' not in facts(s, 0x101))

    # VMP-4: turning into a Vampire Lord in sight
    s, W = setup()
    W.player.lord = True
    s.race_switched()
    W.player.lord = False
    f = facts(s, 0x102)
    case('a Vampire Lord change makes witnesses', f.get('fact_surv_v_saw_lord', '').endswith('|You saw Vega turn into a Vampire Lord')
         and 'fact_surv_v_player' in f, f)
    case('a Vampire Lord witness may use the action lines', s.knows_one(0x102))

    # VMP-5: no critical warning in beast form or while movement is disabled
    for label, attr in (('werewolf', 'werewolf'), ('Vampire Lord', 'lord'), ('movement disabled', 'movement')):
        s, W = setup()
        W.player.vampire_kw = False
        setattr(W.player, attr, attr != 'movement')
        case(f'no warning: {label}', s.warn(1, s.now()) is False)
    s, W = setup()
    W.player.vampire_kw = False
    case('a warning otherwise', s.warn(1, s.now()) is True)

    # VMP-7: a cure clears the feeding; old witnesses remember, but do not know after a new infection
    s, W = setup()
    W.time = 10.95
    s.vampire_fed_game()
    s.fed(0x101)
    W.player.vampire_kw = False
    W.time = 15.95
    s.race_switched()
    case('a cure clears the feeding', not s.shas(PLAYER, 'MLWS_FedAt') and not s.shas(PLAYER, 'MLWS_FedVictim'))
    f = facts(s, 0x102)
    case('a cured player: the witness remembers the past', f.get('fact_surv_v_saw', '').endswith('|You once saw Vega feed on Ysolda, when they were a vampire')
         and 'fact_surv_v_player' not in f, f)
    W.player.vampire_kw, W.time = True, 30.95
    f = facts(s, 0x102)
    case('re-infected: the old witness does not know', 'fact_surv_v_player' not in f and not s.knows_one(0x102), f)
    case('re-infected: the spouse hears no feeding from the old life', 'fact_surv_v_fed' not in facts(s, 0x100) or
         'Ysolda' not in facts(s, 0x100).get('fact_surv_v_fed', ''))

    # VMP-8: Vampire Feed Proxy's NpcVampireFeed resets an NPC vampire's hunger
    s, W = setup()
    serana = Actor(0x103, 0x503, 'Serana', teammate=True, vampire_kw=True, pure_base=True)
    W.actors[serana.ref] = serana
    s.sset(0x103, 'MLWS_SeenAt', 1.0)
    case('NPC vampire hunger before feeding', 'fact_surv_v_self_hunger' in facts(s, 0x103))
    s.npc_fed(0x103)
    case('NpcVampireFeed clears the hunger', 'fact_surv_v_self_hunger' not in facts(s, 0x103))

    # VMP-10: a hood hides the signs
    s, W = setup()
    W.player.vstatus = 4
    case('late-stage signs without a hood', 'fact_surv_v_signs' in facts(s, 0x101))
    W.player.hooded = True
    case('no signs under a hood', 'fact_surv_v_signs' not in facts(s, 0x101))

    # VMP-12: a vampire Dark Elf follower in snow
    s, W = setup()
    W.player.vampire_kw, W.player.weather = False, 3
    W.actors[0x100].race = 'Dark Elf Vampire'
    case('vampire races have a warm homeland', 'Morrowind' in facts(s, 0x100).get('fact_surv_weather', ''))

    # SS-4: another module's closeness mark counts only while that module is loaded
    for mod, key in (('arousal', 'MLW_IsClose'), ('relationships', 'MRB_Close')):
        for loaded in (True, False):
            s, W = setup(**{mod: loaded})
            W.actors[0x100].rank = 3
            s.sset(0x100, key, 1)
            case(f'{key} counts only with {mod} loaded ({loaded})', s.is_close(0x100) is loaded)


# ---------------------------------------------------------------------------------------------------------------------
# Worst-case tokens for one NPC
# ---------------------------------------------------------------------------------------------------------------------

def token_estimate(name='Aldmeri Dominion Thalmor Agent', disease_count=8):
    """Every fact at its longest text. Any six facts can be the kept set (the others need only not apply), so the worst
    case is the six longest that can hold together; the Hub adds " (N days ago)" to dated ones and spends
    tokens(row) + 1 per row (memory.py:445-459). A vampire reader has no "not eaten" fact (MLWS_Food.psc:141)."""
    npc = 'Whiterun Stormcloak Soldier'
    diseases = ', '.join(['Bone Break Fever', 'Brain Rot', 'Collywobbles', 'Rockjoint', 'Witbane', 'Ataxia', 'Rattles',
                          'Swamp Rot'][:disease_count])
    food = 'Horker and Ash Yam Stew'
    place = "Dragonsreach Jarl's Quarters"
    facts = [  # (priority, dated, text) in the order the jobs write them
        (3, False, f'{name} is debilitated by exhaustion.'), (3, False, f'{name} is numb with cold.'),
        (3, False, f'{name} is starving.'),
        (3, False, f'{name} is badly wounded.'), (3, False, f'{name} is drunk.'), (3, False, f'{name} has {diseases}.'),
        (3, False, 'You are badly wounded.'), (3, False, 'You are drunk.'), (3, False, f'You have {diseases}.'),
        (3, False, 'It is snowing. Your people come from the Summerset Isles, a warmer land.'),
        (2, True, f'{name} last ate {food}, raw'), (2, True, f'You last ate {food}, raw'),
        (1, False, f'{name} eats {food} most often.'), (2, True, f'You and {name} shared a meal of {food}'),
        (3, False, 'You have not eaten in over 7 days.'), (2, False, f'{name} is carrying only 3 food items.'),
        (2, True, f"You and {name} slept in {name}'s home at {place}, 10 hours"),
        (1, False, f"The best bed you have had with {name}: in {name}'s home at {place}, 10 hours."),
        (2, False, f'{name} has gone 120 days without a real bed.'), (3, False, 'You have not slept in over 7 days.'),
        (2, False, 'You are a vampire.'), (3, False, 'You are in daylight, and the sun weakens you.'),
        (3, False, 'You have not fed in over 7 days.'), (2, False, f'{name} is a vampire.'),
        (2, True, f'You once saw {name} feed on {npc}, when they were a vampire'), (2, True, f'{name} last fed, on {npc}'),
        (2, True, f'You saw {name} turn into a Vampire Lord'),
        (3, False, f'{name} is hungry for blood.'), (3, False, f'The sun weakens {name} here.'),
        (3, False, f'{name} has burning eyes, sunken skin and fangs.'), (2, True, f'{name} changed into a werewolf'),
    ]
    row = lambda f: f[2] + (' (123 days ago)' if f[1] else '')
    worst = sorted(facts, key=lambda f: -tokens(row(f)))[:setting_int('max_facts', 6)]
    cost = sum(tokens(row(f)) + 1 for f in worst) + tokens('What you know for certain:')
    return cost, [row(f) for f in worst]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=120)
    ap.add_argument('--runs', type=int, default=6)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--before', action='store_true', help='model the shipped behaviour of B1-B6')
    ap.add_argument('--tokens', action='store_true')
    ap.add_argument('--no-exhaustive', action='store_true')
    args = ap.parse_args()
    fixed = set() if args.before else set(FIXED)
    print(HUB_SOURCE, '|', 'shipped behaviour (B1-B6 not fixed)' if args.before else 'fixed behaviour')
    rep = Report()
    for i in range(args.runs):
        run_random(args.seed + i, args.days, fixed, rep)
    if not args.no_exhaustive:
        exhaustive_vampire(fixed, rep)
    if not args.before:
        vampire_cases(rep)
    for k in sorted(rep.counts):
        print(f'  {k}: {rep.counts[k]}')
    checks = ['cap', 'priority order', 'no foreign facts after a write', 'a fact both set and cleared',
              'every fact name staged or cleared', 'expiry as designed', 'Hub drops it the day after it expires',
              'vampire: no fact to an NPC who should not know', 'vampire: signs only from the visible stage, unmasked',
              'vampire: no action line to an NPC who should not know', 'warning never from a summon',
              'warning from a party member', 'warning not twice inside its cooldown (same need)',
              'counters sane: days stated within the cap', 'counters sane: road days', 'counters sane: hours slept 1-24', 'counters sane: hours recorded as slept',
              'warming written while still very cold or worse', 'counters sane: drinks list bounded',
              'counters sane: food names <= 40', 'counters sane: food names and counts parallel', 'counters sane: bed hours',
              'counters sane: best bed score', 'counters sane: need stage 0-5', 'no fact from another save',
              'ignored diseases never named', 'best bed is a bed or bedroll', 'a drink is never the last food',
              'ShareFood/EatThis only with party members', 'sleepers are no witnesses']
    for c in checks + sorted(set(rep.fails) - set(checks)):
        n = rep.fails.get(c, 0)
        print(('PASS ' if not n else 'FAIL ') + c + (f'  ({n}x, e.g. {rep.examples[c]})' if n else ''))
    if args.tokens:
        print(f'Hub fact budget: {FACT_TOKENS} tokens for one NPC alone, at least {MIN_GROUP} per NPC in a group')
        for label, args_ in (('worst case (30-letter name, 8 diseases on both)', {}),
                             ('long but plausible (12-letter name, 2 diseases)', {'name': 'Ingrid Snow-', 'disease_count': 2}),
                             ('typical (4-letter name, 1 disease)', {'name': 'Vega', 'disease_count': 1})):
            cost, rows = token_estimate(**args_)
            print(f'  {label}: {cost} tokens incl. heading')
            for r in rows:
                print('    -', r)
    bad = sum(rep.fails.values())
    print('simulation:', 'all checks passed' if not bad else f'{len(rep.fails)} checks failed')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
