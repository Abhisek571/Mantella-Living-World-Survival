Scriptname MLWS_Test Hidden
{Test build only (never shipped): global functions DevBench calls to drive the Survival module's live tests.}

string Function PLUGIN() global
	Return "Mantella Living World - Survival.esp"
EndFunction

MLWS_Facts Function Facts() global
	Return Game.GetFormFromFile(0x000800, PLUGIN()) as MLWS_Facts
EndFunction
MLWS_Condition Function Condition() global
	Return Game.GetFormFromFile(0x000801, PLUGIN()) as MLWS_Condition
EndFunction
MLWS_Food Function Food() global
	Return Game.GetFormFromFile(0x000802, PLUGIN()) as MLWS_Food
EndFunction
MLWS_Beds Function Beds() global
	Return Game.GetFormFromFile(0x000803, PLUGIN()) as MLWS_Beds
EndFunction
MLWS_Vampire Function Vampire() global
	Return Game.GetFormFromFile(0x000804, PLUGIN()) as MLWS_Vampire
EndFunction
MLWS_Actions Function Actions() global
	Return Game.GetFormFromFile(0x000805, PLUGIN()) as MLWS_Actions
EndFunction

; Every quest running, which survival mods are seen.
string Function Status() global
	Return "facts=" + Facts().IsRunning() + " condition=" + Condition().IsRunning() + " food=" + Food().IsRunning() + " beds=" + Beds().IsRunning() + " vampire=" + Vampire().IsRunning() + " actions=" + Actions().IsRunning() + " survival=" + MLWS_Util.SurvivalOn() + " smi=" + MLWS_Util.SmiLoaded() + " hub=" + MLWS_Util.HubLoaded()
EndFunction

; Re-runs every quest's registration, as a game load does.
string Function Reload() global
	Facts().Register()
	Condition().Register()
	Food().Register()
	Beds().Register()
	Vampire().Register()
	Actions().Register()
	Return "registered"
EndFunction

; Writes the NPC's facts now, as joining a talk does, and returns every fact_surv_ value in the file.
string Function Write(Actor akNpc) global
	Facts().Write(akNpc)
	Return Dump(akNpc)
EndFunction

string Function Dump(Actor akNpc) global
	string path = MLWS_Util.NpcFile(akNpc)
	string[] names = new string[36]
	names[0] = "fact_surv_hunger"
	names[1] = "fact_surv_cold"
	names[2] = "fact_surv_tired"
	names[3] = "fact_surv_warming"
	names[4] = "fact_surv_player_wounded"
	names[5] = "fact_surv_player_drunk"
	names[6] = "fact_surv_player_disease"
	names[7] = "fact_surv_self_wounded"
	names[8] = "fact_surv_self_drunk"
	names[9] = "fact_surv_self_disease"
	names[10] = "fact_surv_weather"
	names[11] = "fact_surv_food_player"
	names[12] = "fact_surv_food_self"
	names[13] = "fact_surv_fav_player"
	names[14] = "fact_surv_fav_self"
	names[15] = "fact_surv_meal"
	names[16] = "fact_surv_hungry"
	names[17] = "fact_surv_supplies"
	names[18] = "fact_surv_bed"
	names[19] = "fact_surv_best_bed"
	names[20] = "fact_surv_road"
	names[21] = "fact_surv_rest"
	names[22] = "fact_surv_v_self"
	names[23] = "fact_surv_v_self_sun"
	names[24] = "fact_surv_v_self_hunger"
	names[25] = "fact_surv_v_player"
	names[26] = "fact_surv_v_saw"
	names[27] = "fact_surv_v_fed"
	names[28] = "fact_surv_v_hunger"
	names[29] = "fact_surv_v_sun"
	names[30] = "fact_surv_v_signs"
	names[31] = "fact_surv_wolf"
	string out = "surv_warm=" + JsonUtil.GetIntValue(path, "surv_warm", -1)
	int i = 0
	While i < 32
		string v = JsonUtil.GetStringValue(path, names[i])
		If v != ""
			out += " ## " + names[i] + "=" + v
		EndIf
		i += 1
	EndWhile
	Return out
EndFunction

; Sets a need (0 hunger, 1 cold, 2 tired) to the value of a stage threshold (1-5), or 0 for none; returns the stage read back.
int Function SetStage(int aiNeed, int aiStage) global
	string esl = MLWS_Util.SURVIVAL_ESL()
	int[] needIds = new int[3]
	needIds[0] = 0x00081A
	needIds[1] = 0x00081B
	needIds[2] = 0x000816
	GlobalVariable need = Game.GetFormFromFile(needIds[aiNeed], esl) as GlobalVariable
	float value = 0.0
	If aiStage > 0
		GlobalVariable threshold
		If aiNeed == 0
			int[] hunger = new int[5]
			hunger[0] = 0x000806
			hunger[1] = 0x000802
			hunger[2] = 0x000803
			hunger[3] = 0x000804
			hunger[4] = 0x000805
			threshold = Game.GetFormFromFile(hunger[aiStage - 1], esl) as GlobalVariable
		ElseIf aiNeed == 1
			threshold = Game.GetFormFromFile(0x000D20 + aiStage - 1, MLWS_Util.SMI_ESP()) as GlobalVariable
		Else
			threshold = Game.GetFormFromFile(0x000A17 + aiStage - 1, MLWS_Util.SMI_ESP()) as GlobalVariable
		EndIf
		value = threshold.GetValue() + 1.0
	EndIf
	need.SetValue(value)
	Return Condition().Stage(aiNeed)
EndFunction

; Runs the 30-second check now (warming up, critical warning).
string Function Check() global
	Condition().Check()
	Return "checked"
EndFunction

; Forgets the critical warning cooldowns.
string Function ResetWarnings() global
	StorageUtil.UnsetFloatValue(None, "MLWS_WarnedAt0")
	StorageUtil.UnsetFloatValue(None, "MLWS_WarnedAt1")
	StorageUtil.UnsetFloatValue(None, "MLWS_WarnedAt2")
	Return "reset"
EndFunction

; As the SKSE plugin's MLWS_Ate event: flags 1 raw, 2 alcohol, 4 blood.
string Function Ate(Actor akWho, string asFood, int aiFlags) global
	Food().Record(akWho, asFood, aiFlags)
	Return StorageUtil.GetStringValue(akWho, "MLWS_FoodName") + " at " + StorageUtil.GetFloatValue(akWho, "MLWS_FoodAt")
EndFunction

; Moves an actor's food, sleep, feeding and first-seen clocks afDays into the past.
string Function Age(Actor akWho, float afDays) global
	string[] stamps = new string[7]
	stamps[0] = "MLWS_FoodAt"
	stamps[1] = "MLWS_BedAt"
	stamps[2] = "MLWS_RealBedAt"
	stamps[3] = "MLWS_SeenAt"
	stamps[4] = "MLWS_BloodAt"
	stamps[5] = "MLWS_MealAt"
	stamps[6] = "MLWS_FedAt"
	int i = 0
	While i < stamps.Length
		If StorageUtil.HasFloatValue(akWho, stamps[i])
			StorageUtil.AdjustFloatValue(akWho, stamps[i], -afDays)
		EndIf
		i += 1
	EndWhile
	Return "aged " + afDays
EndFunction

; As a night in bed: kind 1-6, the given place and hours, shared with party members near the player.
string Function Slept(int aiKind, string asPlace, float afHours) global
	float now = Utility.GetCurrentGameTime()
	Beds().Apply(Game.GetPlayer(), aiKind, asPlace, afHours, now)
	Actor[] near = MLWS_Native.PartyNear(4096.0)
	int i = 0
	While i < near.Length
		Beds().Apply(near[i], aiKind, asPlace, afHours, now)
		i += 1
	EndWhile
	Return "slept, shared with " + near.Length
EndFunction

; The kind of the furniture in use now (sit on a bed first), and what GetFurnitureReference returns.
string Function BedHere() global
	Actor player = Game.GetPlayer()
	ObjectReference bed = player.GetFurnitureReference()
	string name = "None"
	If bed
		name = bed.GetBaseObject().GetName()
	EndIf
	Return name + " kind=" + Beds().KindOf(bed, player.GetCurrentLocation())
EndFunction

; As OnVampireFeed: marks witnesses in sight now.
string Function Feed(Actor akVictim) global
	Vampire().Fed(akVictim)
	Return "fed on " + akVictim.GetDisplayName() + ", stage " + Vampire().PlayerStage() + ", last fed " + Vampire().PlayerLastFed()
EndFunction

string Function Natives(Actor akActor) global
	Form pick = MLWS_Native.PickFood(akActor, false)
	string picked = "None"
	If pick
		picked = pick.GetName()
	EndIf
	Return "food=" + MLWS_Native.FoodCount(akActor) + " pick=" + picked + " fire=" + MLWS_Native.KnowsFire(akActor) + " diseases=[" + MLWS_Native.DiseaseNames(akActor) + "] party=" + MLWS_Native.PartyNear(4096.0).Length + " vampire=" + MLWS_Util.IsVampire(akActor) + " pure=" + MLWS_Util.IsPureBlood(akActor)
EndFunction

; The actions as Mantella's legacy path sends them; returns the event line.
string Function Share(Actor akNpc, string asDirection) global
	StorageUtil.UnsetFloatValue(akNpc, "MLWS_SharedAt")
	Return Actions().ShareFood(akNpc, asDirection)
EndFunction

string Function EatThis(Actor akNpc) global
	StorageUtil.UnsetFloatValue(akNpc, "MLWS_SharedAt")
	Return Actions().EatThis(akNpc)
EndFunction

string Function Warm(Actor akNpc) global
	StorageUtil.UnsetFloatValue(akNpc, "MLWS_WarmedAt")
	Return Actions().WarmYou(akNpc)
EndFunction

; Mantella conversation events, as Mantella sends them.
string Function Join(Actor akActor) global
	int handle = ModEvent.Create("MantellaConversation_NPC_Added")
	ModEvent.PushForm(handle, akActor)
	ModEvent.Send(handle)
	Return "sent"
EndFunction
