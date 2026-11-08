Scriptname MLWS_Beds extends MLWS_Job
{Mantella Living World - Survival: where the player sleeps decides, and party members near the player share that night.
Kept on each actor. All of it is told to the party only:
  last bed (1 day, replaced at the next sleep); best bed by kind, hours and place (a bedroll or better), lasting; days since a real bed;
  follower rest: not slept in days, or only a few hours last time.
Kinds: 6 the player's home, 5 an inn, 4 a house or other lived-in place, 3 another bed, 2 a bedroll, 1 no bed found.
The bed is the furniture in use (SKSE's Actor.GetFurnitureReference), or what the player last sat on just now.}

float Property SIT_WINDOW = 0.02 AutoReadOnly   ; half an hour of game time
float Property SHARE_RADIUS = 4096.0 AutoReadOnly
float Property MIN_HOURS = 0.25 AutoReadOnly
int Property REAL_BED_KIND = 3 AutoReadOnly

ObjectReference lastSat
float lastSatAt = -1.0
float startAt = -1.0
int startKind
string startPlace
Actor[] sharers

bool Function WantsSleep()
	Return true
EndFunction

Function Sat(ObjectReference akFurniture)
	lastSat = akFurniture
	lastSatAt = Utility.GetCurrentGameTime()
EndFunction

Function SleepStart(float afStart, float afDesiredEnd)
	startAt = Utility.GetCurrentGameTime()
	ObjectReference bed = PlayerRef.GetFurnitureReference()
	If !bed && lastSat && startAt - lastSatAt <= SIT_WINDOW
		bed = lastSat
	EndIf
	Location here = PlayerRef.GetCurrentLocation()
	startKind = KindOf(bed, here)
	startPlace = ""
	If here
		startPlace = here.GetName()
	EndIf
	sharers = MLWS_Native.PartyNear(SHARE_RADIUS)
EndFunction

Function SleepStop(bool abInterrupted)
	If startAt < 0.0
		Return
	EndIf
	float now = Utility.GetCurrentGameTime()
	float hours = (now - startAt) * 24.0
	startAt = -1.0
	If hours < MIN_HOURS
		Return
	EndIf
	Apply(PlayerRef, startKind, startPlace, hours, now)
	int i = 0
	While sharers && i < sharers.Length
		If sharers[i]
			Apply(sharers[i], startKind, startPlace, hours, now)
		EndIf
		i += 1
	EndWhile
	sharers = None
EndFunction

Function Apply(Actor akWho, int aiKind, string asPlace, float afHours, float afNow)
	int hours = (afHours + 0.5) as int  ; rounded: the difference of two game times reads 7.9999 for 8 hours
	StorageUtil.SetIntValue(akWho, "MLWS_BedKind", aiKind)
	StorageUtil.SetStringValue(akWho, "MLWS_BedPlace", asPlace)
	StorageUtil.SetFloatValue(akWho, "MLWS_BedAt", afNow)
	StorageUtil.SetIntValue(akWho, "MLWS_BedHours", hours)
	If aiKind >= REAL_BED_KIND
		StorageUtil.SetFloatValue(akWho, "MLWS_RealBedAt", afNow)
	EndIf
	int score = Score(aiKind, asPlace, afHours)
	If aiKind >= 2 && score > StorageUtil.GetIntValue(akWho, "MLWS_BestScore", 0)
		StorageUtil.SetIntValue(akWho, "MLWS_BestScore", score)
		StorageUtil.SetIntValue(akWho, "MLWS_BestKind", aiKind)
		StorageUtil.SetStringValue(akWho, "MLWS_BestPlace", asPlace)
		StorageUtil.SetIntValue(akWho, "MLWS_BestHours", hours)
	EndIf
EndFunction

int Function Score(int aiKind, string asPlace, float afHours)
	float h = afHours
	If h > 8.0
		h = 8.0
	EndIf
	int score = aiKind * 100 + (h * 5.0) as int
	If asPlace != ""
		score += 10
	EndIf
	Return score
EndFunction

int Function KindOf(ObjectReference akBed, Location akHere)
	If !akBed
		Return 1
	EndIf
	Keyword roll = Game.GetFormFromFile(0x0E4AD6, "Skyrim.esm") as Keyword  ; FurnitureBedRoll
	Form base = akBed.GetBaseObject()
	If roll && (akBed.HasKeyword(roll) || (base && base.HasKeyword(roll)))
		Return 2
	EndIf
	If !akHere
		Return 3
	EndIf
	If HasLocType(akHere, 0x0FC1A3)     ; LocTypePlayerHouse
		Return 6
	ElseIf HasLocType(akHere, 0x01CB87) ; LocTypeInn
		Return 5
	ElseIf HasLocType(akHere, 0x01CB85) || HasLocType(akHere, 0x01CD57) || HasLocType(akHere, 0x01CD5A) \
		|| HasLocType(akHere, 0x01CD56) || HasLocType(akHere, 0x01CB86) || HasLocType(akHere, 0x01CD55)  ; house, castle, guild, temple, store, barracks
		Return 4
	EndIf
	Return 3
EndFunction

bool Function HasLocType(Location akHere, int aiKeyword)
	Keyword k = Game.GetFormFromFile(aiKeyword, "Skyrim.esm") as Keyword
	Return k && akHere.HasKeyword(k)
EndFunction

string Function Describe(int aiKind, string asPlace, int aiHours, string asPlayer)
	string where = ""
	If asPlace != ""
		where = " at " + asPlace
	EndIf
	string out
	If aiKind == 6
		out = "in " + asPlayer + "'s home" + where
	ElseIf aiKind == 5
		out = "at an inn" + where
	ElseIf aiKind >= 3
		out = "in a bed" + where
	ElseIf aiKind == 2
		out = "in a bedroll" + where
	Else
		out = "without a bed" + where
	EndIf
	Return out + ", " + aiHours + " hours"
EndFunction

Function WriteFacts(Actor akNpc, string asPath, bool abParty, float afNow)
	If !abParty
		MLWS_Util.ClearFact(asPath, "fact_surv_bed")
		MLWS_Util.ClearFact(asPath, "fact_surv_best_bed")
		MLWS_Util.ClearFact(asPath, "fact_surv_road")
		MLWS_Util.ClearFact(asPath, "fact_surv_rest")
		Return
	EndIf
	string player = MLWS_Util.PlayerName()
	int today = afNow as int

	float mine = StorageUtil.GetFloatValue(akNpc, "MLWS_BedAt", -1.0)
	float theirs = StorageUtil.GetFloatValue(PlayerRef, "MLWS_BedAt", -1.0)
	If mine >= 0.0 && mine >= theirs
		string text = "You slept "
		If mine == theirs
			text = "You and " + player + " slept "
		EndIf
		MLWS_Util.SetFact(asPath, "fact_surv_bed", mine as int, (mine as int) + 1, 2, text + Describe(StorageUtil.GetIntValue(akNpc, "MLWS_BedKind"), StorageUtil.GetStringValue(akNpc, "MLWS_BedPlace"), StorageUtil.GetIntValue(akNpc, "MLWS_BedHours"), player))
	ElseIf theirs >= 0.0
		MLWS_Util.SetFact(asPath, "fact_surv_bed", theirs as int, (theirs as int) + 1, 2, player + " slept " + Describe(StorageUtil.GetIntValue(PlayerRef, "MLWS_BedKind"), StorageUtil.GetStringValue(PlayerRef, "MLWS_BedPlace"), StorageUtil.GetIntValue(PlayerRef, "MLWS_BedHours"), player))
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_bed")
	EndIf

	If StorageUtil.GetIntValue(akNpc, "MLWS_BestScore", 0) > 0
		MLWS_Util.SetFact(asPath, "fact_surv_best_bed", -1, -1, 1, "The best bed you have had with " + player + ": " + Describe(StorageUtil.GetIntValue(akNpc, "MLWS_BestKind"), StorageUtil.GetStringValue(akNpc, "MLWS_BestPlace"), StorageUtil.GetIntValue(akNpc, "MLWS_BestHours"), player) + ".")
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_best_bed")
	EndIf

	; The player's clock starts at the first night tracked, like a party member's at first seen.
	If !StorageUtil.HasFloatValue(PlayerRef, "MLWS_SeenAt")
		StorageUtil.SetFloatValue(PlayerRef, "MLWS_SeenAt", afNow)
	EndIf
	int road = MLWS_Util.DaysSince(PlayerRef, "MLWS_RealBedAt", afNow)
	If road >= 2
		MLWS_Util.SetNowFact(asPath, "fact_surv_road", today, 2, player + " has gone " + road + " days without a real bed.")
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_road")
	EndIf

	int awake = MLWS_Util.DaysSince(akNpc, "MLWS_BedAt", afNow)
	int most = MLWS_Util.SettingInt("follower_hungry_max", 7)  ; days apart from the party count too, so capped like food
	If awake > most && awake >= 2
		MLWS_Util.SetNowFact(asPath, "fact_surv_rest", today, 3, "You have not slept in over " + most + " days.")
	ElseIf awake >= 2
		MLWS_Util.SetNowFact(asPath, "fact_surv_rest", today, 3, "You have not slept in " + awake + " days.")
	ElseIf mine >= 0.0 && afNow - mine <= 1.0 && StorageUtil.GetIntValue(akNpc, "MLWS_BedHours") < 4
		MLWS_Util.SetNowFact(asPath, "fact_surv_rest", today, 3, "You slept only " + StorageUtil.GetIntValue(akNpc, "MLWS_BedHours") + " hours last time.")
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_rest")
	EndIf
EndFunction
