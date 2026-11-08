#!/usr/bin/env bash
# Drives the Survival module's live tests (S1-S8) over DevBench and checks the NPC files on disk.
# Needs: the game running in a test profile with DevBench and a save loaded, this mod's test build (MLWS_Test.pex next
# to the module's scripts), Survival Mode Improved on, one follower in the party (FOLLOWER) and a stranger (STRANGER)
# near the player, the player not a vampire for S1-S6. Use a throwaway save: food and stage values are changed.
# usage: MO2=<instance> FOLLOWER=0x000A2C94 STRANGER=0x0001A672 bash run-tests.sh
#   FOLLOWER  a party member reference (default Lydia 0x000A2C94)
#   STRANGER  a non-party NPC reference (default Belethor 0x0001A672)
#   MAGE      a party member or NPC who knows a fire spell, for S8 (default: skipped)
set -u
MO2=${MO2:?set MO2 to your Mod Organizer 2 instance folder}
NPC_DIR="$MO2/overwrite/SKSE/Plugins/StorageUtilData/MantellaLivingWorld/npc"
DB="$MO2/tools/devbench-cli.sh"
PASS=0; FAIL=0

call() { bash "$DB" call "$@" 2>&1 | py -3 -I -c "import json,sys
try:
    d=json.load(sys.stdin); print(d.get('returned') if d.get('called') else 'ERROR '+str(d))
except Exception: print('ERROR no reply')"; }
t() { call MLWS_Test "$1" "${2:-[]}"; }
con() { bash "$DB" exec "$1" >/dev/null 2>&1; }
note() { bash "$DB" notify "$1" >/dev/null 2>&1; echo "== $1"; }
check() {  # check <name> <value> <regex>
  if printf '%s' "$2" | grep -qiE -- "$3"; then PASS=$((PASS+1)); echo "   PASS $1"; else FAIL=$((FAIL+1)); echo "   FAIL $1: got [$2], want /$3/"; fi
}
nocheck() {  # nocheck <name> <value> <regex>: passes when the regex does NOT match
  if printf '%s' "$2" | grep -qiE -- "$3"; then FAIL=$((FAIL+1)); echo "   FAIL $1: got [$2], must not match /$3/"; else PASS=$((PASS+1)); echo "   PASS $1"; fi
}
f() { printf '{"form":"%s"}' "$1"; }

FOL=$(f "${FOLLOWER:-0x000A2C94}"); STR=$(f "${STRANGER:-0x0001A672}")

bash "$DB" alive | grep -qi running || { echo "game not running with a save loaded"; exit 2; }
con "set GameHour to 12"
note "setup"
check "quests running, SMI seen" "$(t Status)" "facts=true condition=true food=true beds=true vampire=true actions=true survival=true smi=true"
check "old-save registration (as on load)" "$(t Reload)" "registered"
check "natives answer" "$(t Natives "[$FOL]")" "food=[0-9]+ pick=.* party=[1-9]"

note "S1 healthy player in town: almost nothing"
for n in 0 1 2; do t SetStage "[$n,0]" >/dev/null; done
con "player.restoreav health 10000"
out=$(t Write "[$STR]")
nocheck "stranger: no need, food or bed facts" "$out" "fact_surv_(hunger|cold|tired|food|bed|road|supplies|fav)"

note "S2 needs past the mild stage are visible to anyone"
check "hunger stage 4 set" "$(t SetStage '[0,4]')" "^4$"
check "cold stage 3 set" "$(t SetStage '[1,3]')" "^3$"
check "tired stage 2 (mild) set" "$(t SetStage '[2,2]')" "^2$"
out=$(t Write "[$STR]")
check "stranger sees famished" "$out" "fact_surv_hunger=-1\|[0-9]+\|3\|.* is famished"
check "stranger sees very cold" "$out" "fact_surv_cold=-1\|[0-9]+\|3\|.* is very cold"
nocheck "mild tiredness not told" "$out" "fact_surv_tired"

note "S3 warming up and the critical warning"
t SetStage '[1,4]' >/dev/null; t Check >/dev/null; t SetStage '[1,1]' >/dev/null; t Check >/dev/null
check "party member hears warming up" "$(t Write "[$FOL]")" "fact_surv_warming="
nocheck "stranger does not" "$(t Write "[$STR]")" "fact_surv_warming"
t ResetWarnings >/dev/null; t SetStage '[0,5]' >/dev/null; t Check >/dev/null; sleep 3
echo "   LOOK: the follower should open a talk about the player starving (one talk, then nothing for 3 days)"
t Check >/dev/null
for n in 0 1 2; do t SetStage "[$n,0]" >/dev/null; done

note "S4 food: last, favourite, raw, shared meal, hungry follower, supplies"
t Ate "[$(f 0x14),\"Apple\",0]" >/dev/null; t Ate "[$FOL,\"Apple\",0]" >/dev/null
out=$(t Write "[$FOL]")
check "last food dated, expires in 2 days" "$out" "fact_surv_food_player=([0-9]+)\|[0-9]+\|2\|.* last ate Apple"
check "shared meal remembered" "$out" "fact_surv_meal=[0-9]+\|-1\|2\|You and .* shared a meal of Apple"
for i in 1 2 3; do t Ate "[$(f 0x14),\"Venison Stew\",0]" >/dev/null; sleep 4; done
check "favourite after 3" "$(t Write "[$FOL]")" "fact_surv_fav_player=-1\|-1\|1\|.* eats Venison Stew most often"
t Ate "[$(f 0x14),\"Raw Beef\",1]" >/dev/null
check "raw flagged" "$(t Write "[$FOL]")" "last ate Raw Beef, raw"
nocheck "stranger: no food facts" "$(t Write "[$STR]")" "fact_surv_(food|fav|meal)"
t Age "[$FOL,3.0]" >/dev/null
check "follower not eaten in 3 days" "$(t Write "[$FOL]")" "fact_surv_hungry=-1\|[0-9]+\|3\|You have not eaten in 3 days"
con "player.removeallitems"
check "no food carried" "$(t Write "[$FOL]")" "fact_surv_supplies=.*carrying no food"

note "S5 beds: last, best, days on the road, follower rest"
t Slept '[2,"Bleak Falls Barrow",6.0]' >/dev/null
out=$(t Write "[$FOL]")
check "shared bedroll night" "$out" "fact_surv_bed=[0-9]+\|[0-9]+\|2\|You and .* slept in a bedroll at Bleak Falls Barrow, 6 hours"
t Slept '[5,"The Bannered Mare",8.0]' >/dev/null
check "best bed is the inn" "$(t Write "[$FOL]")" "fact_surv_best_bed=.*at an inn at The Bannered Mare, 8 hours"
t Age "[$(f 0x14),3.0]" >/dev/null; t Age "[$FOL,3.0]" >/dev/null
out=$(t Write "[$FOL]")
check "3 days without a real bed" "$out" "fact_surv_road=.* has gone 3 days without a real bed"
check "follower not slept in 3 days" "$out" "fact_surv_rest=.*You have not slept in 3 days"
echo "   LOOK: activate a bed and sit, then:"; check "furniture in use read" "$(t BedHere)" "kind="

note "S6 visible condition"
con "player.damageav health 600"
check "wounded seen by a stranger" "$(t Write "[$STR]")" "fact_surv_player_wounded="
con "player.restoreav health 10000"
for i in 1 2 3; do t Ate "[$(f 0x14),\"Ale\",2]" >/dev/null; sleep 4; done
check "drunk after 3 drinks" "$(t Write "[$STR]")" "fact_surv_player_drunk="
con "player.addspell 000B877C"   # Ataxia
check "disease named" "$(t Write "[$STR]")" "fact_surv_player_disease=.*has Ataxia"
con "player.removespell 000B877C"

note "S7 vampires (Serana if Dawnguard; the player part needs a vampire player save)"
SERANA=$(f "${SERANA:-0x02002B74}")
check "Serana knows she is pure-blood" "$(t Write "[$SERANA]")" "fact_surv_v_self=-1\|-1\|2\|You are a pure-blood vampire"
nocheck "no daylight weakness for a pure-blood" "$(t Write "[$SERANA]")" "fact_surv_v_self_sun"
echo "   MANUAL (vampire player save): stage 1-3 => stranger has no fact_surv_v_*; stage 4 => fact_surv_v_signs only;"
echo "   close follower => fact_surv_v_player + fact_surv_v_fed; t Feed [<victim>] near a stranger in sight => fact_surv_v_saw on them"

note "S8 actions"
con "player.additem 00064B2F 2"   # Apple
check "follower takes an apple from the player" "$(t Share "[$FOL,\"player_gives\"]")" "gave .* to .*, who ate it"
check "follower with no food refuses" "$(t Share "[$STR,\"npc_gives\"]")" "has no food to give|gave"
t SetStage '[0,0]' >/dev/null
check "not hungry: EatThis refused" "$(t EatThis "[$FOL]")" "is not hungry"
t SetStage '[0,4]' >/dev/null
check "hungry: EatThis eats" "$(t EatThis "[$FOL]")" "ate .* at .*'s urging|nor .* has any food"
check "WarmYou refused without a fire spell" "$(t Warm "[$FOL]")" "knows no fire spell|is not cold"
if [ -n "${MAGE:-}" ]; then
  t SetStage '[1,4]' >/dev/null
  check "mage warms the player, cold need drops" "$(t Warm "[$(f "$MAGE")]")" "conjured flames"
fi
for n in 0 1 2; do t SetStage "[$n,0]" >/dev/null; done

check "npc files still valid JSON" "$(py -3 -I -c "import json,glob,sys
bad=[p for p in glob.glob(sys.argv[1]+'/*.json') if not (lambda p: (json.load(open(p,encoding='utf-8')), True))(p)]
print('ok' if not bad else bad)" "$NPC_DIR" 2>&1)" "^ok$"
note "tests finished: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
