Scriptname MLWS_Util Hidden
{Shared helpers for Mantella Living World - Survival. Nothing here needs another Living World module: the Hub is only
looked up, and without it the fact files simply are not read.}

string Function HUB_PLUGIN() global
	Return "Mantella Living World - Integration Hub.esp"
EndFunction

string Function SURVIVAL_ESL() global
	Return "ccqdrsse001-survivalmode.esl"
EndFunction

string Function SMI_ESP() global
	Return "SurvivalModeImproved.esp"
EndFunction

string Function SETTINGS() global
	Return "MantellaLivingWorld/survival_settings.json"
EndFunction

; A full plugin answers GetModByName, a light one GetLightModByName.
bool Function PluginLoaded(string asName) global
	Return Game.GetModByName(asName) != 255 || Game.GetLightModByName(asName) != 65535
EndFunction

bool Function SmiLoaded() global
	Return PluginLoaded(SMI_ESP())
EndFunction

bool Function HubLoaded() global
	Return PluginLoaded(HUB_PLUGIN())
EndFunction

; Survival Mode is installed and switched on.
bool Function SurvivalOn() global
	If !PluginLoaded(SURVIVAL_ESL())
		Return false
	EndIf
	GlobalVariable on = Game.GetFormFromFile(0x000826, SURVIVAL_ESL()) as GlobalVariable
	Return on && on.GetValueInt() == 1
EndFunction

int Function SettingInt(string asKey, int aiDefault) global
	Return JsonUtil.GetIntValue(SETTINGS(), asKey, aiDefault)
EndFunction

float Function SettingFloat(string asKey, float afDefault) global
	Return JsonUtil.GetFloatValue(SETTINGS(), asKey, afDefault)
EndFunction

Function Log(string asText) global
	If HubLoaded()
		MLW_Hub hub = Game.GetFormFromFile(0x000820, HUB_PLUGIN()) as MLW_Hub
		If hub
			hub.Log("survival", asText)
		EndIf
	EndIf
EndFunction

; One event line for the running Mantella conversation (Mantella keeps it for the next talk when none runs).
Function Send(string asLine) global
	If asLine == ""
		Return
	EndIf
	int handle = ModEvent.Create("MantellaAddEvent")
	If handle
		ModEvent.PushString(handle, asLine)
		ModEvent.Send(handle)
	EndIf
	Log(asLine)
EndFunction

; Tells Mantella an action that requires a response has finished. Sent on every path.
Function ActionDone(string asIdentifier) global
	int handle = ModEvent.Create("Mantella_ActionResponseCompleted")
	If handle
		ModEvent.PushString(handle, asIdentifier)
		ModEvent.Send(handle)
	EndIf
EndFunction

string Function PlayerName() global
	Return Game.GetPlayer().GetDisplayName()
EndFunction

; The file the Hub reads for an NPC: the base record's FormID as its last 6 hex digits.
string Function NpcFile(Actor akNpc) global
	string digits = "0123456789ABCDEF"
	int v = akNpc.GetActorBase().GetFormID()
	string out = ""
	int i = 0
	While i < 6
		out = StringUtil.GetNthChar(digits, Math.LogicalAnd(v, 15)) + out
		v = Math.RightShift(v, 4)
		i += 1
	EndWhile
	Return "MantellaLivingWorld/npc/" + out + ".json"
EndFunction

; day and expires are game days, -1 = none. The Hub adds "(N days ago)" when day is set.
; Priority: 3 a need or condition right now, 2 something the party saw or did, 1 lasting trivia.
; Facts are only gathered here (per file, on this save); MLWS_Facts.Commit writes the most important ones to the file.
Function SetFact(string asPath, string asName, int aiDay, int aiExpires, int aiPriority, string asText) global
	StorageUtil.StringListAdd(None, "MLWS_FactName" + asPath, asName)
	StorageUtil.StringListAdd(None, "MLWS_FactValue" + asPath, aiDay + "|" + aiExpires + "|" + aiPriority + "|" + asText)
EndFunction

; Marks a fact as not applying now; MLWS_Facts.Commit removes it from the file.
Function ClearFact(string asPath, string asName) global
	StorageUtil.StringListAdd(None, "MLWS_FactGone" + asPath, asName, false)
EndFunction

; A fact about right now: no date, and at worst it lasts until the end of today.
Function SetNowFact(string asPath, string asName, int aiToday, int aiPriority, string asText) global
	SetFact(asPath, asName, -1, aiToday, aiPriority, asText)
EndFunction

bool Function IsParty(Actor akActor) global
	If akActor.IsCommandedActor()
		Return false  ; summons and raised thralls are teammates, not party members
	EndIf
	If akActor.IsPlayerTeammate()
		Return true
	EndIf
	Faction current = Game.GetFormFromFile(0x05C84E, "Skyrim.esm") as Faction  ; CurrentFollowerFaction
	Return current && akActor.GetFactionRank(current) >= 0
EndFunction

; Party members the player is close to: a set relationship rank, or marked close by another module. Another module's
; mark counts only while that module is loaded: nothing clears it after an uninstall.
bool Function IsClose(Actor akActor) global
	If !IsParty(akActor)
		Return false
	EndIf
	If akActor.GetRelationshipRank(Game.GetPlayer()) >= SettingInt("close_rank", 4)
		Return true
	EndIf
	If PluginLoaded("Mantella Living World - Arousal.esp") && StorageUtil.GetIntValue(akActor, "MLW_IsClose", 0) > 0
		Return true
	EndIf
	Return PluginLoaded("Mantella Living World - Relationships.esp") && StorageUtil.GetIntValue(akActor, "MRB_Close", 0) > 0
EndFunction

; Werewolf or Vampire Lord form.
bool Function InBeastForm(Actor akActor) global
	Race now = akActor.GetRace()
	If !now
		Return false
	EndIf
	If now == Game.GetFormFromFile(0x0CDD84, "Skyrim.esm")  ; WerewolfBeastRace
		Return true
	EndIf
	If !PluginLoaded("Dawnguard.esm")
		Return false
	EndIf
	Return now == Game.GetFormFromFile(0x00283A, "Dawnguard.esm")  ; DLC1VampireBeastRace
EndFunction

; A hood, helmet or mask (biped slot 30 or 31) hides the face.
bool Function FaceHidden(Actor akActor) global
	Return (akActor.GetWornForm(0x00000001) as Armor) != None || (akActor.GetWornForm(0x00000002) as Armor) != None
EndFunction

; The NPC saw the player feed or turn into a Vampire Lord since the player was last cured (an older sighting is from a
; time the player was a vampire before, MLWS_Vampire.PlayerFacts).
bool Function SawVampire(Actor akNpc) global
	float cured = StorageUtil.GetFloatValue(Game.GetPlayer(), "MLWS_CuredAt", -1.0)
	float saw = StorageUtil.GetFloatValue(akNpc, "MLWS_SawFeedAt", -1.0)
	float lord = StorageUtil.GetFloatValue(akNpc, "MLWS_SawLordAt", -1.0)
	Return (saw >= 0.0 && saw >= cured) || (lord >= 0.0 && lord >= cured)
EndFunction

; Harkon, Valerica and Serana by record (any language), and any name listed in the settings file for modded ones.
; Only while they are vampires (a cured Serana is not), and never the player, whatever the player is called.
bool Function IsPureBlood(Actor akActor) global
	If akActor == Game.GetPlayer() || !IsVampire(akActor)
		Return false
	EndIf
	ActorBase base = akActor.GetActorBase()
	If base && PluginLoaded("Dawnguard.esm")
		If base == Game.GetFormFromFile(0x002B6C, "Dawnguard.esm") || base == Game.GetFormFromFile(0x003B8B, "Dawnguard.esm") \
			|| base == Game.GetFormFromFile(0x003BA7, "Dawnguard.esm") || base == Game.GetFormFromFile(0x01A93D, "Dawnguard.esm")
			Return true
		EndIf
	EndIf
	Return JsonUtil.StringListHas(SETTINGS(), "pure_bloods", akActor.GetDisplayName())
EndFunction

bool Function IsVampire(Actor akActor) global
	Keyword vampire = Game.GetFormFromFile(0x0A82BB, "Skyrim.esm") as Keyword
	Return vampire && akActor.HasKeyword(vampire)
EndFunction

; Drinks within two game hours, from Survival's food tracking.
bool Function IsDrunk(Actor akActor, float afNow) global
	int count = 0
	int i = StorageUtil.FloatListCount(akActor, "MLWS_Drinks")
	While i > 0
		i -= 1
		If afNow - StorageUtil.FloatListGet(akActor, "MLWS_Drinks", i) <= 0.0834
			count += 1
		EndIf
	EndWhile
	Return count >= SettingInt("drunk_drinks", 3)
EndFunction

; Whole game days since a stamp on the actor, starting the clock from when the party member was first seen when unset.
int Function DaysSince(Actor akActor, string asKey, float afNow) global
	float at = StorageUtil.GetFloatValue(akActor, asKey, -1.0)
	If at < 0.0
		at = StorageUtil.GetFloatValue(akActor, "MLWS_SeenAt", afNow)
	EndIf
	Return (afNow - at) as int
EndFunction
