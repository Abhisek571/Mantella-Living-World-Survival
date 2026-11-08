Scriptname MLWS_Native Hidden
{Native functions from Survival's SKSE plugin (MLWS_Listener.dll).}

; Living party members in range, nearest first.
Actor[] Function PartyNear(float afRadius) global native

; Living, awake NPCs in range with line of sight to the player who have detected them, leaving out akSkip.
Actor[] Function WitnessesNear(Actor akSkip, float afRadius) global native

; Food items carried.
int Function FoodCount(Actor akActor) global native

; One item to eat, never a quest item: cooked before raw, no alcohol if avoidable, cheapest first. With abBlood, a blood potion instead.
Form Function PickFood(Actor akActor, bool abBlood) global native

; 1 raw, 2 alcohol, 4 blood potion.
int Function FoodFlags(Form akItem) global native

; Active diseases, comma separated, without Sanguinare Vampiris (it would give a vampire away).
string Function DiseaseNames(Actor akActor) global native

; A real fire spell on the NPC's record or added since. Leveled spell lists are not read.
bool Function KnowsFire(Actor akActor) global native
