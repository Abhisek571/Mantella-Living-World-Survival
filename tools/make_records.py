"""Writes the Survival module's plugin as Spriggit YAML (one quest per job, each with a player alias that re-registers
its events on every game load), its Mantella action files and its default settings file. Run from the project root."""
import json, os

E = 'Mantella Living World - Survival.esp'
# form id, editor id, script, name, other quests its script holds (property, form id)
QUESTS = [
    ('000800', 'MLWS_QuestFacts', 'MLWS_Facts', 'Mantella Living World - Survival facts',
     [('Condition', '000801'), ('Food', '000802'), ('Beds', '000803'), ('Vampire', '000804'), ('Actions', '000805')]),
    ('000801', 'MLWS_QuestCondition', 'MLWS_Condition', 'Mantella Living World - Survival condition', []),
    ('000802', 'MLWS_QuestFood', 'MLWS_Food', 'Mantella Living World - Survival food', []),
    ('000803', 'MLWS_QuestBeds', 'MLWS_Beds', 'Mantella Living World - Survival beds', []),
    ('000804', 'MLWS_QuestVampire', 'MLWS_Vampire', 'Mantella Living World - Survival vampires', []),
    ('000805', 'MLWS_QuestActions', 'MLWS_Actions', 'Mantella Living World - Survival actions',
     [('Food', '000802'), ('Condition', '000801'), ('Facts', '000800')]),
]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'w', encoding='utf-8', newline='\n').write(text)


for fid, eid, script, name, links in QUESTS:
    props = '    - MutagenObjectType: ScriptObjectProperty\n      Name: PlayerRef\n      Object: 000014:Skyrim.esm\n'
    for prop, target in links:
        props += f'    - MutagenObjectType: ScriptObjectProperty\n      Name: {prop}\n      Object: {target}:{E}\n'
    write(f'esp/Quests/{eid} - {fid}_{E}.yaml',
          f"FormKey: {fid}:{E}\nEditorID: {eid}\nVirtualMachineAdapter:\n  Scripts:\n  - Name: {script}\n    Properties:\n{props}"
          f"  FileName: ''\n  Aliases:\n  - Property:\n      Name: ''\n      Object: {fid}:{E}\n      Alias: 0\n"
          f"    Scripts:\n    - Name: MLWS_PlayerAlias\n"
          f"Name:\n  TargetLanguage: English\n  Value: {name}\nFlags:\n- StartGameEnabled\nNextAliasID: 1\n"
          f"Aliases:\n- Name: PlayerAlias\n  Flags: []\n  ForcedReference: 000014:Skyrim.esm\n  VoiceTypes: Null\n")
write('esp/RecordData.yaml', f'ModKey: {E}\nGameRelease: SkyrimSE\nModHeader:\n  Flags:\n  - Small\n  Author: itsPigeon2000\n'
      '  Description: Mantella Living World - Survival. What the player and party eat, where they sleep and how they look, told to Mantella NPCs.\n'
      '  MasterReferences:\n  - Master: Skyrim.esm\n    FileSize: 0\n')
write('esp/spriggit-meta.json', json.dumps({'PackageName': 'Spriggit.Yaml.Skyrim', 'Version': '0.40.0', 'Release': 'SkyrimSE', 'ModKey': E}, indent=2))

NOTE = 'Needs Mantella Living World - Survival.'
ACTIONS = [
    {'identifier': 'mantella_mlws_share_food', 'name': 'ShareFood', 'gate': 'follower',
     'description': 'Hand one real food item to the player, or take one from the player and eat it. Only when it really happens now; not for talk about food.',
     'key': 'ShareFood',
     'parameters': {'direction': {'type': 'string', 'enum': ['npc_gives', 'player_gives'],
                                  'description': 'npc_gives: you hand the player food from your pack and the player eats it; player_gives: the player hands you food and you eat it.'}},
     'required': ['direction'],
     'prompt': "If you hand the player food from your pack, or eat food the player gives you, begin your response with '{key}:'"},
    {'identifier': 'mantella_mlws_eat_this', 'name': 'EatThis', 'gate': 'follower',
     'description': 'Make the hungry player eat something now, from your pack or theirs. Only when the player clearly agrees to eat.',
     'key': 'EatThis',
     'prompt': "If the player is hungry and clearly agrees to eat what you offer, begin your response with '{key}:'"},
    {'identifier': 'mantella_mlws_warm_you', 'name': 'WarmYou', 'gate': 'surv_warm=1',
     'description': 'Warm the cold player with a fire spell you know. Only when the player is cold and you do it now.',
     'key': 'WarmYou',
     'prompt': "If the player is cold and you warm them with a fire spell you know, begin your response with '{key}:'"},
]
for a in ACTIONS:
    data = {'identifier': a['identifier'], 'name': a['name'], 'description': a['description'], 'note': NOTE, 'key': a['key'],
            'enabled': True, 'lw_gate': a['gate']}
    if 'parameters' in a:
        data['parameters'] = a['parameters']
        data['required'] = a['required']
    data.update({'prompt': a['prompt'], 'allowed_games': ['skyrim'], 'requires_response': True, 'is-interrupting': False,
                 'allow_repeat': False, 'one-on-one': True, 'multi-npc': True, 'radiant': False})
    write(f"SKSE/Plugins/MantellaSoftware/data/actions/{a['identifier']}.json", json.dumps(data, indent=4) + '\n')

# PapyrusUtil's JSON layout: values sorted by type.
SETTINGS = {
    'int': {'close_rank': 4,'critical_warning': 1, 'drunk_drinks': 3, 'follower_hungry_days': 2, 'follower_hungry_max': 7,
            'low_food': 3, 'max_facts': 6, 'vampire_hungry_days': 2, 'visible_stage': 4},
    'float': {'critical_cooldown_days': 3.0, 'critical_radius': 1500.0, 'eat_this_hunger': 80.0, 'warm_you_cold': 150.0},
    'stringList': {'pure_bloods': ['Lord Harkon', 'Harkon', 'Valerica', 'Serana'], 'disease_ignore': ['Victim Damage']},
}
write('SKSE/Plugins/StorageUtilData/MantellaLivingWorld/survival_settings.json', json.dumps(SETTINGS, indent=2) + '\n')
print('survival records written:', len(QUESTS), 'quests,', len(ACTIONS), 'actions, settings')
