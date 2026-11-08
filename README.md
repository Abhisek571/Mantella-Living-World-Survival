# Mantella Living World - Survival

Lets Mantella NPCs notice how you are getting by: hunger, cold, rest, what you have eaten and where you slept. A module of [Mantella Living World - Integration Hub](https://github.com/Abhisek571/Mantella-Living-World-Hub). Not released yet.

Everything is written as short facts into the NPC's file when they join a talk, and only what applies now. A healthy player in town tells a stranger almost nothing. At most six facts go to one NPC (`max_facts`), the most pressing first: needs and condition right now, then what the party saw, then lasting things such as a favourite food.

| Feature | Who knows | What it says |
|---|---|---|
| Hunger, cold, tiredness | Anyone | The Survival Mode stage, past the mild one (hungry, famished, starving; very cold, freezing, numb; tired, weary, debilitated). Needs Survival Mode; cold and tiredness need Survival Mode Improved |
| Warming up | Party | You warmed up in the last hour after being very cold or worse |
| Wounded, drunk, diseased | Anyone | Below half health, three drinks in two hours, the real disease names (vampirism's disease is never named, nor those in `disease_ignore`, such as Better Vampires' Victim Damage). Also the NPC's own |
| Not my weather | Party | Snow outdoors for a party member whose people come from a warm land (vampire versions of those races too) |
| Food | Party | Your last food (2 days, raw flagged), the food you eat most often, a party member's own (drinks are not food), a meal shared within an hour (told for 2 days), a party member who has not eaten in days, few food items left in your pack |
| Beds | Party | Where you slept decides, party members nearby share the night: last bed (1 day or the next sleep), best bed with you by kind, hours and place (a bedroll or better), days without a real bed, a party member who has not slept or slept only a few hours |
| Vampires | See note | An NPC vampire knows they are one (Harkon, Valerica and Serana as pure-bloods, more names in the settings file), feels daylight unless pure-blood, and a party vampire says how long since they fed (a feeding through Vampire Feed Proxy or a blood potion resets it). Your vampirism: signs on your face only at the last stage (not under Better Vampires' Mortal's Mask or a hood or helmet); close party members know you are one, and so do awake NPCs who saw you feed and had spotted you, an awake victim, and anyone who saw you turn into a Vampire Lord. They know when and on whom you last fed (bottled blood counts, with no victim), your blood hunger and sun weakness. After a cure the last feeding is forgotten, and earlier witnesses only remember that you were a vampire |
| Werewolf | Party | You changed into a werewolf in the last day |
| Critical warning | | Once when a need reaches its worst stage, a party member near you says so (3 game days between warnings, the Hub's pacing applies) |
| ShareFood | Party members | Refused for anyone not travelling with you. One real food item moves between you and the NPC, and whoever got it eats it. Blood for a vampire |
| EatThis | Party members | Refused for anyone not travelling with you, and when Survival Mode says you are not hungry. You eat what the NPC offers (or from your pack). With Survival Mode Improved, hunger comes down through its API |
| WarmYou | NPCs with a fire spell | A show of flames and Survival Mode Improved's cold comes down. Refused without it |

After any of the three actions the NPC's facts are written again, so the talk sees the change at once.

Close means a relationship rank of 4 (lover or spouse, `close_rank`), because following someone already gives rank 3. Living World Relationships and Arousal can also mark an NPC close, but only while they are installed; without them only a spouse or lover counts.

The warning talk never starts while you are a werewolf or a Vampire Lord, or while the game holds you still (a scene or cutscene); it waits for the next check.

Requires:
- Mantella Living World - Integration Hub (reads the facts)
- [Mantella](https://www.nexusmods.com/skyrimspecialedition/mods/98631) with Advanced Actions on for the action choices
- SKSE, [PapyrusUtil SE](https://www.nexusmods.com/skyrimspecialedition/mods/13048), [Address Library for SKSE Plugins](https://www.nexusmods.com/skyrimspecialedition/mods/32444)

Optional:
- Survival Mode (Creation Club) for hunger, and [Survival Mode Improved - SKSE](https://www.nexusmods.com/skyrimspecialedition/mods/78244) for cold, tiredness, EatThis's hunger and WarmYou. Neither is a master.
- [Better Vampires](https://www.nexusmods.com/skyrimspecialedition/mods/1925) (its Mortal's Mask hides the signs)

Settings: `SKSE/Plugins/StorageUtilData/MantellaLivingWorld/survival_settings.json` (pure-blood names, thresholds, facts per NPC, the warning on or off).

Build: `py -3 tools/make_records.py` writes the plugin YAML, action files and settings; `plugin/build.ps1` builds the SKSE plugin; then the Hub's `tools/build.py --only survival`. Offline checks: `py -3 tools/test_offline.py`. Live tests: `test/run-tests.sh` over DevBench.

License: GNU AGPL-3.0 for the scripts and data; the SKSE plugin in `plugin/` is GPL-3.0.
