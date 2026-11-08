Scriptname MLWS_Food extends MLWS_Job
{Mantella Living World - Survival: what the player and the party eat, from the MLWS_Ate event of the SKSE plugin (kept on
each actor with StorageUtil). All of it is told to the party only:
  last food, with its day, for 2 days (raw flagged; drinks are not food); the food eaten most often, lasting; a meal
  shared within an hour, told for 2 days;
  a follower who has not eaten in days (the clock starts when they were first seen, capped so it stays believable);
  few food items left in the player's pack.}

string Property KEY_NAME = "MLWS_FoodName" AutoReadOnly
string Property KEY_AT = "MLWS_FoodAt" AutoReadOnly
string Property KEY_RAW = "MLWS_FoodRaw" AutoReadOnly
string Property KEY_NAMES = "MLWS_FoodNames" AutoReadOnly     ; parallel lists: every food and how often
string Property KEY_COUNTS = "MLWS_FoodCounts" AutoReadOnly
string Property KEY_MEAL_AT = "MLWS_MealAt" AutoReadOnly
string Property KEY_MEAL_FOOD = "MLWS_MealFood" AutoReadOnly
string Property KEY_DRINKS = "MLWS_Drinks" AutoReadOnly
string Property KEY_BLOOD_AT = "MLWS_BloodAt" AutoReadOnly
float Property HOUR = 0.0417 AutoReadOnly
float Property TWO_HOURS = 0.0834 AutoReadOnly
int Property MAX_FOODS = 40 AutoReadOnly
int Property FAVOURITE_MIN = 3 AutoReadOnly

Function Register()
	RegisterForModEvent("MLWS_Ate", "OnAte")
EndFunction

Event OnAte(string asEvent, string asName, float afFlags, Form akSender)
	Actor who = akSender as Actor
	If !who
		Return
	EndIf
	; An action that equipped this item already recorded it: skip its equip event once.
	float real = Utility.GetCurrentRealTime()
	float actionReal = StorageUtil.GetFloatValue(who, "MLWS_FoodReal", -100.0)
	If StorageUtil.GetStringValue(who, "MLWS_FoodPending") == asName && real >= actionReal && real - actionReal < 3.0
		StorageUtil.UnsetStringValue(who, "MLWS_FoodPending")
		Return
	EndIf
	Record(who, asName, afFlags as int)
EndEvent

; Actions eat through this too. abEquipped: the action equipped the item, so its equip event will follow and is not
; counted twice. Eating the same food several times in a row by hand still counts each time.
Function Record(Actor akWho, string asName, int aiFlags, bool abEquipped = false)
	float now = Utility.GetCurrentGameTime()
	If abEquipped
		StorageUtil.SetFloatValue(akWho, "MLWS_FoodReal", Utility.GetCurrentRealTime())
		StorageUtil.SetStringValue(akWho, "MLWS_FoodPending", asName)
	EndIf
	If Math.LogicalAnd(aiFlags, 4)
		StorageUtil.SetFloatValue(akWho, KEY_BLOOD_AT, now)  ; blood is not a meal
		If akWho == PlayerRef
			; bottled blood feeds the player without OnVampireFeed: no victim, and no older victim named as the last
			StorageUtil.SetFloatValue(PlayerRef, "MLWS_FedAt", now)
			StorageUtil.SetStringValue(PlayerRef, "MLWS_FedVictim", "")
		EndIf
		Return
	EndIf
	If Math.LogicalAnd(aiFlags, 2)
		StorageUtil.FloatListAdd(akWho, KEY_DRINKS, now)
		While StorageUtil.FloatListCount(akWho, KEY_DRINKS) > 0 && now - StorageUtil.FloatListGet(akWho, KEY_DRINKS, 0) > TWO_HOURS
			StorageUtil.FloatListRemoveAt(akWho, KEY_DRINKS, 0)
		EndWhile
		Return  ; a drink is not a meal: no last food, favourite or hunger clock
	EndIf
	StorageUtil.SetStringValue(akWho, KEY_NAME, asName)
	StorageUtil.SetFloatValue(akWho, KEY_AT, now)
	StorageUtil.SetIntValue(akWho, KEY_RAW, Math.LogicalAnd(aiFlags, 1))
	Count(akWho, asName)
	SharedMeal(akWho, asName, now)
EndFunction

Function Count(Actor akWho, string asName)
	int at = StorageUtil.StringListFind(akWho, KEY_NAMES, asName)
	If at >= 0
		StorageUtil.IntListSet(akWho, KEY_COUNTS, at, StorageUtil.IntListGet(akWho, KEY_COUNTS, at) + 1)
	ElseIf StorageUtil.StringListCount(akWho, KEY_NAMES) < MAX_FOODS
		StorageUtil.StringListAdd(akWho, KEY_NAMES, asName)
		StorageUtil.IntListAdd(akWho, KEY_COUNTS, 1)
	EndIf
EndFunction

; Player and party member ate within an hour of each other: remembered on the party member.
Function SharedMeal(Actor akWho, string asName, float afNow)
	If akWho == PlayerRef
		Actor[] near = MLWS_Native.PartyNear(2048.0)
		int i = 0
		While i < near.Length
			If afNow - StorageUtil.GetFloatValue(near[i], KEY_AT, -1000.0) <= HOUR
				StorageUtil.SetFloatValue(near[i], KEY_MEAL_AT, afNow)
				StorageUtil.SetStringValue(near[i], KEY_MEAL_FOOD, asName)
			EndIf
			i += 1
		EndWhile
	ElseIf afNow - StorageUtil.GetFloatValue(PlayerRef, KEY_AT, -1000.0) <= HOUR && akWho.GetDistance(PlayerRef) <= 2048.0
		StorageUtil.SetFloatValue(akWho, KEY_MEAL_AT, afNow)
		StorageUtil.SetStringValue(akWho, KEY_MEAL_FOOD, asName)
	EndIf
EndFunction

string Function Favourite(Actor akWho)
	string best = ""
	int bestCount = FAVOURITE_MIN - 1
	int i = StorageUtil.StringListCount(akWho, KEY_NAMES)
	While i > 0
		i -= 1
		int c = StorageUtil.IntListGet(akWho, KEY_COUNTS, i)
		If c > bestCount
			bestCount = c
			best = StorageUtil.StringListGet(akWho, KEY_NAMES, i)
		EndIf
	EndWhile
	Return best
EndFunction

Function WriteFacts(Actor akNpc, string asPath, bool abParty, float afNow)
	If !abParty
		ClearAll(asPath)
		Return
	EndIf
	string player = MLWS_Util.PlayerName()
	int today = afNow as int
	LastFood(PlayerRef, asPath, "fact_surv_food_player", player + " last ate ")
	LastFood(akNpc, asPath, "fact_surv_food_self", "You last ate ")

	string favourite = Favourite(PlayerRef)
	If favourite != ""
		MLWS_Util.SetFact(asPath, "fact_surv_fav_player", -1, -1, 1, player + " eats " + favourite + " most often.")
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_fav_player")
	EndIf
	favourite = Favourite(akNpc)
	If favourite != ""
		MLWS_Util.SetFact(asPath, "fact_surv_fav_self", -1, -1, 1, "You eat " + favourite + " most often.")
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_fav_self")
	EndIf

	float mealAt = StorageUtil.GetFloatValue(akNpc, KEY_MEAL_AT, -1.0)
	If mealAt >= 0.0
		MLWS_Util.SetFact(asPath, "fact_surv_meal", mealAt as int, (mealAt as int) + 2, 2, "You and " + player + " shared a meal of " + StorageUtil.GetStringValue(akNpc, KEY_MEAL_FOOD))
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_meal")
	EndIf

	; Followers ask for food: a vampire's hunger is in MLWS_Vampire.
	int hungry = MLWS_Util.DaysSince(akNpc, KEY_AT, afNow)
	If hungry >= MLWS_Util.SettingInt("follower_hungry_days", 2) && !MLWS_Util.IsVampire(akNpc)
		int most = MLWS_Util.SettingInt("follower_hungry_max", 7)
		If hungry > most
			MLWS_Util.SetNowFact(asPath, "fact_surv_hungry", today, 3, "You have not eaten in over " + most + " days.")
		Else
			MLWS_Util.SetNowFact(asPath, "fact_surv_hungry", today, 3, "You have not eaten in " + hungry + " days.")
		EndIf
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_hungry")
	EndIf

	int food = MLWS_Native.FoodCount(PlayerRef)
	If food <= MLWS_Util.SettingInt("low_food", 3) && !MLWS_Util.IsVampire(PlayerRef)
		If food == 0
			MLWS_Util.SetNowFact(asPath, "fact_surv_supplies", today, 2, player + " is carrying no food.")
		Else
			MLWS_Util.SetNowFact(asPath, "fact_surv_supplies", today, 2, player + " is carrying only " + food + " food items.")
		EndIf
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_supplies")
	EndIf
EndFunction

Function LastFood(Actor akWho, string asPath, string asFact, string asText)
	float at = StorageUtil.GetFloatValue(akWho, KEY_AT, -1.0)
	If at < 0.0
		MLWS_Util.ClearFact(asPath, asFact)
		Return
	EndIf
	int day = at as int
	string text = asText + StorageUtil.GetStringValue(akWho, KEY_NAME)
	If StorageUtil.GetIntValue(akWho, KEY_RAW) == 1
		text += ", raw"
	EndIf
	MLWS_Util.SetFact(asPath, asFact, day, day + 2, 2, text)
EndFunction

Function ClearAll(string asPath)
	MLWS_Util.ClearFact(asPath, "fact_surv_food_player")
	MLWS_Util.ClearFact(asPath, "fact_surv_food_self")
	MLWS_Util.ClearFact(asPath, "fact_surv_fav_player")
	MLWS_Util.ClearFact(asPath, "fact_surv_fav_self")
	MLWS_Util.ClearFact(asPath, "fact_surv_meal")
	MLWS_Util.ClearFact(asPath, "fact_surv_hungry")
	MLWS_Util.ClearFact(asPath, "fact_surv_supplies")
EndFunction
