Scriptname MLWS_Condition extends MLWS_Job
{Mantella Living World - Survival: how the player looks right now.

Needs (Survival Mode, live in globals of its .esl, stages from those globals with Survival Mode Improved): hunger, cold
and tiredness as plain facts past the mild stage, for anyone who sees the player. Stages are 0-5: the number of the five
thresholds reached. Warming up: the cold stage came down lately, for the party. A vampire player has no hunger fact
(SMI turns that need off for vampires; blood hunger is in MLWS_Vampire).

Works without Survival Mode: wounded, drunk, diseased, and not my weather for a party member from a warm land.

Critical warning: once when a need reaches the worst stage a party member near the player says so through a
MantellaAddEvent line. Checked every 30 real seconds, and only with Survival Mode installed.}

float Property POLL = 30.0 AutoReadOnly
float Property WARM_DAYS = 0.05 AutoReadOnly     ; about an hour of game time
string Property KEY_WARM_AT = "MLWS_WarmAt" AutoReadOnly
string Property KEY_WARM_FROM = "MLWS_WarmFrom" AutoReadOnly
string Property KEY_WARNED = "MLWS_WarnedAt" AutoReadOnly
float Property PACE_COOLDOWN = 600.0 AutoReadOnly

GlobalVariable[] needs      ; 0 hunger, 1 cold, 2 tired
GlobalVariable[] stages     ; five thresholds per need
int[] lastStage
bool[] armed

Function Register()
	Setup()
	If needs[0]
		RegisterForSingleUpdate(POLL)
	EndIf
EndFunction

Function Setup()
	needs = new GlobalVariable[3]
	stages = new GlobalVariable[15]
	If !lastStage
		lastStage = new int[3]
		armed = new bool[3]
		armed[0] = true
		armed[1] = true
		armed[2] = true
	EndIf
	string esl = MLWS_Util.SURVIVAL_ESL()
	If !MLWS_Util.PluginLoaded(esl)
		Return
	EndIf
	needs[0] = Game.GetFormFromFile(0x00081A, esl) as GlobalVariable
	needs[1] = Game.GetFormFromFile(0x00081B, esl) as GlobalVariable
	needs[2] = Game.GetFormFromFile(0x000816, esl) as GlobalVariable
	stages[0] = Game.GetFormFromFile(0x000806, esl) as GlobalVariable
	stages[1] = Game.GetFormFromFile(0x000802, esl) as GlobalVariable
	stages[2] = Game.GetFormFromFile(0x000803, esl) as GlobalVariable
	stages[3] = Game.GetFormFromFile(0x000804, esl) as GlobalVariable
	stages[4] = Game.GetFormFromFile(0x000805, esl) as GlobalVariable
	If !MLWS_Util.SmiLoaded()
		Return  ; without SMI only the hunger thresholds are known
	EndIf
	string smi = MLWS_Util.SMI_ESP()
	int i = 0
	While i < 5
		stages[5 + i] = Game.GetFormFromFile(0x000D20 + i, smi) as GlobalVariable
		stages[10 + i] = Game.GetFormFromFile(0x000A17 + i, smi) as GlobalVariable
		i += 1
	EndWhile
EndFunction

; 0-5, or -1 when this need cannot be read now.
int Function Stage(int aiNeed)
	If !needs || !needs[aiNeed] || !stages[aiNeed * 5 + 4] || !MLWS_Util.SurvivalOn()
		Return -1
	EndIf
	float value = needs[aiNeed].GetValue()
	int stage = 0
	int i = 0
	While i < 5
		If value >= stages[aiNeed * 5 + i].GetValue()
			stage = i + 1
		EndIf
		i += 1
	EndWhile
	Return stage
EndFunction

; "is hungry" and so on, for stages 3-5.
string Function NeedWords(int aiNeed, int aiStage)
	If aiNeed == 0
		If aiStage == 3
			Return "is hungry"
		ElseIf aiStage == 4
			Return "is famished"
		EndIf
		Return "is starving"
	ElseIf aiNeed == 1
		If aiStage == 3
			Return "is very cold"
		ElseIf aiStage == 4
			Return "is freezing"
		EndIf
		Return "is numb with cold"
	EndIf
	If aiStage == 3
		Return "is tired"
	ElseIf aiStage == 4
		Return "is weary"
	EndIf
	Return "is debilitated by exhaustion"
EndFunction

; ---------------------------------------------------------------------------
; The check every 30 seconds: warming up and the critical warning
; ---------------------------------------------------------------------------

Event OnUpdate()
	Check()
	RegisterForSingleUpdate(POLL)
EndEvent

Function Check()
	float now = Utility.GetCurrentGameTime()
	bool vampire = MLWS_Util.IsVampire(PlayerRef)
	int i = 0
	While i < 3
		int stage = Stage(i)
		If stage >= 0 && !(i == 0 && vampire)
			If i == 1 && lastStage[1] >= 3 && stage < lastStage[1]
				StorageUtil.SetFloatValue(PlayerRef, KEY_WARM_AT, now)
				StorageUtil.SetIntValue(PlayerRef, KEY_WARM_FROM, lastStage[1])
			EndIf
			lastStage[i] = stage
			If stage < 5
				armed[i] = true
			ElseIf armed[i] && Warn(i, now)
				armed[i] = false
			EndIf
		EndIf
		i += 1
	EndWhile
EndFunction

; True when the line was given (or never will be). A claim refused for now is tried again on the next check.
bool Function Warn(int aiNeed, float afNow)
	If MLWS_Util.SettingInt("critical_warning", 1) != 1
		Return true
	EndIf
	string warnKey = KEY_WARNED + aiNeed
	If afNow - StorageUtil.GetFloatValue(None, warnKey, -1000.0) < MLWS_Util.SettingFloat("critical_cooldown_days", 3.0)
		Return true
	EndIf
	If PlayerRef.IsInCombat() || PlayerRef.IsSneaking() || !MLWS_Util.PluginLoaded("Mantella.esp")
		Return false
	EndIf
	; not in beast form, and not while the game holds the player still (OStim scenes, cutscenes)
	If MLWS_Util.InBeastForm(PlayerRef) || !Game.IsMovementControlsEnabled()
		Return false
	EndIf
	Actor[] near = MLWS_Native.PartyNear(MLWS_Util.SettingFloat("critical_radius", 1500.0))
	If !near || near.Length == 0
		Return false
	EndIf
	Actor follower = near[0]
	string line = MLWS_Util.PlayerName() + " " + NeedWords(aiNeed, 5) + ". " + follower.GetDisplayName() + " can see it."
	MantellaConversation talk = Game.GetFormFromFile(0x03D41A, "Mantella.esp") as MantellaConversation
	If !talk
		Return false
	EndIf
	If talk.IsRunning()
		MLWS_Util.Send(line)
	Else
		; The Hub's pacing keeps this from stepping on other ambient lines; without the Hub the cooldown above is enough.
		If MLWS_Util.HubLoaded() && !MLW_Pace.TryClaim("survival", PACE_COOLDOWN)
			Return false
		EndIf
		; Mantella sends its waiting events with the first request, so the line goes first.
		MLWS_Util.Send(line)
		Utility.Wait(0.2)
		Actor[] actors = new Actor[2]
		actors[0] = PlayerRef
		actors[1] = follower
		talk.Start()
		talk.StartConversation(actors)
	EndIf
	StorageUtil.SetFloatValue(None, warnKey, afNow)
	Return true
EndFunction

; ---------------------------------------------------------------------------
; Facts
; ---------------------------------------------------------------------------

Function WriteFacts(Actor akNpc, string asPath, bool abParty, float afNow)
	int today = afNow as int
	string player = MLWS_Util.PlayerName()
	NeedFact(asPath, "fact_surv_hunger", 0, today, player, MLWS_Util.IsVampire(PlayerRef))
	NeedFact(asPath, "fact_surv_cold", 1, today, player, false)
	NeedFact(asPath, "fact_surv_tired", 2, today, player, false)

	float warmAt = StorageUtil.GetFloatValue(PlayerRef, KEY_WARM_AT, -1.0)
	If abParty && warmAt >= 0.0 && afNow - warmAt <= WARM_DAYS && Stage(1) < 3  ; not while still very cold
		MLWS_Util.SetNowFact(asPath, "fact_surv_warming", today, 2, player + " has warmed up since the cold got to them.")
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_warming")
	EndIf

	Visible(PlayerRef, asPath, "fact_surv_player_", player + " ", today, afNow)
	Visible(akNpc, asPath, "fact_surv_self_", "You ", today, afNow)
	Weather(akNpc, asPath, abParty, today)
EndFunction

Function NeedFact(string asPath, string asFact, int aiNeed, int aiToday, string asPlayer, bool abSkip)
	int stage = Stage(aiNeed)
	If stage >= 3 && !abSkip
		MLWS_Util.SetNowFact(asPath, asFact, aiToday, 3, asPlayer + " " + NeedWords(aiNeed, stage) + ".")
	Else
		MLWS_Util.ClearFact(asPath, asFact)
	EndIf
EndFunction

; Wounded, drunk and diseased, for the player or the NPC themselves. asWho ends in a space; "You " and a name read the same.
Function Visible(Actor akActor, string asPath, string asPrefix, string asWho, int aiToday, float afNow)
	bool you = asWho == "You "
	float health = akActor.GetActorValuePercentage("Health")
	If health < 0.25
		If you
			MLWS_Util.SetNowFact(asPath, asPrefix + "wounded", aiToday, 3, "You are badly wounded.")
		Else
			MLWS_Util.SetNowFact(asPath, asPrefix + "wounded", aiToday, 3, asWho + "is badly wounded.")
		EndIf
	ElseIf health < 0.5
		If you
			MLWS_Util.SetNowFact(asPath, asPrefix + "wounded", aiToday, 3, "You are wounded.")
		Else
			MLWS_Util.SetNowFact(asPath, asPrefix + "wounded", aiToday, 3, asWho + "is wounded.")
		EndIf
	Else
		MLWS_Util.ClearFact(asPath, asPrefix + "wounded")
	EndIf

	If MLWS_Util.IsDrunk(akActor, afNow)
		If you
			MLWS_Util.SetNowFact(asPath, asPrefix + "drunk", aiToday, 3, "You are drunk.")
		Else
			MLWS_Util.SetNowFact(asPath, asPrefix + "drunk", aiToday, 3, asWho + "is drunk.")
		EndIf
	Else
		MLWS_Util.ClearFact(asPath, asPrefix + "drunk")
	EndIf

	string diseases = ShownDiseases(akActor)
	If diseases != ""
		If you
			MLWS_Util.SetNowFact(asPath, asPrefix + "disease", aiToday, 3, "You have " + diseases + ".")
		Else
			MLWS_Util.SetNowFact(asPath, asPrefix + "disease", aiToday, 3, asWho + "has " + diseases + ".")
		EndIf
	Else
		MLWS_Util.ClearFact(asPath, asPrefix + "disease")
	EndIf
EndFunction

; The disease names, without those the settings file lists in disease_ignore (Better Vampires' "Victim Damage" on a
; feeding victim is no illness anyone could see).
string Function ShownDiseases(Actor akActor)
	string all = MLWS_Native.DiseaseNames(akActor)
	If all == ""
		Return ""
	EndIf
	string[] names = StringUtil.Split(all, ", ")
	string out = ""
	int i = 0
	While names && i < names.Length
		If names[i] != "" && !JsonUtil.StringListHas(MLWS_Util.SETTINGS(), "disease_ignore", names[i])
			If out != ""
				out += ", "
			EndIf
			out += names[i]
		EndIf
		i += 1
	EndWhile
	Return out
EndFunction

; Not my weather: snow outdoors, for a party member whose people come from a warm land (the race is known).
Function Weather(Actor akNpc, string asPath, bool abParty, int aiToday)
	string home = ""
	If abParty && !PlayerRef.IsInInterior()
		Weather now = Weather.GetCurrentWeather()
		If now && now.GetClassification() == 3
			home = WarmHome(akNpc.GetRace())
		EndIf
	EndIf
	If home != ""
		MLWS_Util.SetNowFact(asPath, "fact_surv_weather", aiToday, 3, "It is snowing. Your people come from " + home + ", a warmer land.")
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_weather")
	EndIf
EndFunction

string Function WarmHome(Race akRace)
	If !akRace
		Return ""
	EndIf
	int id = akRace.GetFormID()
	; the playable races and their vampire twins
	If id == 0x013740 || id == 0x08883A
		Return "Black Marsh"
	ElseIf id == 0x013745 || id == 0x088845
		Return "Elsweyr"
	ElseIf id == 0x013748 || id == 0x088846
		Return "Hammerfell"
	ElseIf id == 0x013742 || id == 0x08883D
		Return "Morrowind"
	ElseIf id == 0x013744 || id == 0x088844
		Return "Cyrodiil"
	ElseIf id == 0x013743 || id == 0x088840
		Return "the Summerset Isles"
	ElseIf id == 0x013749 || id == 0x088884
		Return "Valenwood"
	EndIf
	Return ""
EndFunction
