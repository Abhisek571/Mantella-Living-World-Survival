Scriptname MLWS_Facts extends MLWS_Job
{Mantella Living World - Survival: when an NPC joins a Mantella talk, every job writes or clears its facts in that NPC's
file (fact_surv_*, read by the Hub), and the file is saved once. Only what applies now is written; a healthy player in
town adds almost nothing to anyone who is not in the party.}

MLWS_Job Property Condition Auto
MLWS_Job Property Food Auto
MLWS_Job Property Beds Auto
MLWS_Job Property Vampire Auto
MLWS_Job Property Actions Auto

; Looked up on first use; a form from a removed plugin reads None after a load and is looked up again.
GlobalVariable modeEnabled  ; Survival Mode's switch
Keyword vampireKeyword

Function Register()
	RegisterForModEvent("MantellaConversation_NPC_Added", "OnNpcAdded")
	RegisterForModEvent("MLW_ReportRequest", "OnReportRequest")
EndFunction

Event OnNpcAdded(Form akActor)
	If StorageUtil.GetIntValue(None, "MLW_TimingOn", 0) == 1  ; speed testing (off by default): one stage-time row
		MiscUtil.WriteToFile("Data/SKSE/Plugins/StorageUtilData/MantellaLivingWorld/timing_game.csv", StorageUtil.GetIntValue(None, "MLW_TimingTalk", 0) + "," + Utility.GetCurrentRealTime() + ",MLWS_Facts,OnNpcAdded_start,\n", true, false)
	EndIf
	Actor npc = akActor as Actor
	If npc && npc != PlayerRef && !npc.IsDead()
		Write(npc)
	EndIf
	If StorageUtil.GetIntValue(None, "MLW_TimingOn", 0) == 1  ; speed testing (off by default): one stage-time row
		MiscUtil.WriteToFile("Data/SKSE/Plugins/StorageUtilData/MantellaLivingWorld/timing_game.csv", StorageUtil.GetIntValue(None, "MLW_TimingTalk", 0) + "," + Utility.GetCurrentRealTime() + ",MLWS_Facts,OnNpcAdded_end,\n", true, false)
	EndIf
EndEvent

; Also called after an action changes something, so a running talk sees it.
Function Write(Actor akNpc)
	string path = MLWS_Util.NpcFile(akNpc)
	; one write per file at a time: two generic NPCs of one base share the file, and a second write in between would
	; clear the first one's staged facts (a stamp, not a flag: a save taken mid-write never blocks the file for good)
	float started = Utility.GetCurrentRealTime()
	float other = StorageUtil.GetFloatValue(None, "MLWS_WritingAt" + path, -1000.0)
	If other <= started && started - other < 10.0
		Return
	EndIf
	StorageUtil.SetFloatValue(None, "MLWS_WritingAt" + path, started)
	float now = Utility.GetCurrentGameTime()
	bool party = MLWS_Util.IsParty(akNpc)
	If party && !StorageUtil.HasFloatValue(akNpc, "MLWS_SeenAt")
		StorageUtil.SetFloatValue(akNpc, "MLWS_SeenAt", now)  ; the clocks for food and sleep start here, not at day zero
	EndIf
	; The jobs only gather their facts; Commit then writes them, so the file never holds a half-cleared set.
	ClearStaged(path)  ; anything left by a write that was cut off
	; Read once for every job.
	bool survivalOn = SurvivalOn()
	If !vampireKeyword
		vampireKeyword = Game.GetFormFromFile(0x0A82BB, "Skyrim.esm") as Keyword
	EndIf
	bool playerVampire = vampireKeyword && PlayerRef.HasKeyword(vampireKeyword)
	string player = PlayerRef.GetDisplayName()
	; Vampire first: within a priority Commit keeps the write order, and the late-stage signs must not be cut by conditions.
	Vampire.WriteFacts(akNpc, path, party, now, survivalOn, playerVampire, player)
	Condition.WriteFacts(akNpc, path, party, now, survivalOn, playerVampire, player)
	Food.WriteFacts(akNpc, path, party, now, survivalOn, playerVampire, player)
	Beds.WriteFacts(akNpc, path, party, now, survivalOn, playerVampire, player)
	Actions.WriteFacts(akNpc, path, party, now, survivalOn, playerVampire, player)
	Commit(path)
	JsonUtil.Save(path)  ; the Hub reads fact_surv_* from this file itself: no refresh of the rest of it
	StorageUtil.UnsetFloatValue(None, "MLWS_WritingAt" + path)
EndFunction

; MLWS_Util.SurvivalOn with the global kept between writes.
bool Function SurvivalOn()
	If !modeEnabled
		If !MLWS_Util.PluginLoaded(MLWS_Util.SURVIVAL_ESL())
			Return false
		EndIf
		modeEnabled = Game.GetFormFromFile(0x000826, MLWS_Util.SURVIVAL_ESL()) as GlobalVariable
	EndIf
	Return modeEnabled && modeEnabled.GetValueInt() == 1
EndFunction

; The Hub gives each NPC a small fact budget, so at most max_facts survival facts go in, highest priority first (ties in
; the order the jobs wrote them). The kept ones are written first; only then is every other fact_surv_ key removed:
; ones from other saves (the npc files are shared), ones that no longer apply and ones over the cap.
Function Commit(string asPath)
	string names = "MLWS_FactName" + asPath
	string values = "MLWS_FactValue" + asPath
	string kept = "MLWS_FactKept" + asPath
	int count = StorageUtil.StringListCount(None, names)
	int cap = MLWS_Util.SettingInt("max_facts", 6)
	int taken = 0
	int priority = 3
	While priority >= 1 && taken < cap
		int j = 0
		While j < count && taken < cap
			string value = StorageUtil.StringListGet(None, values, j)
			If PriorityOf(value) == priority
				string name = StorageUtil.StringListGet(None, names, j)
				JsonUtil.SetStringValue(asPath, name, value)
				StorageUtil.StringListAdd(None, kept, name, false)
				taken += 1
			EndIf
			j += 1
		EndWhile
		priority -= 1
	EndWhile

	; JsonUtil keeps string values under ".string". The jobs' own lists cover the case where that path is not read.
	string[] inFile = JsonUtil.PathMembers(asPath, ".string")
	int i = 0
	While inFile && i < inFile.Length
		If StringUtil.Find(inFile[i], "fact_surv_") == 0
			DropUnlessKept(asPath, inFile[i], kept)
		EndIf
		i += 1
	EndWhile
	i = 0
	While i < count
		DropUnlessKept(asPath, StorageUtil.StringListGet(None, names, i), kept)
		i += 1
	EndWhile
	string gone = "MLWS_FactGone" + asPath
	i = StorageUtil.StringListCount(None, gone)
	While i > 0
		i -= 1
		DropUnlessKept(asPath, StorageUtil.StringListGet(None, gone, i), kept)
	EndWhile
	ClearStaged(asPath)
EndFunction

Function DropUnlessKept(string asPath, string asName, string asKept)
	If StorageUtil.StringListFind(None, asKept, asName) < 0
		JsonUtil.UnsetStringValue(asPath, asName)
	EndIf
EndFunction

; "day|expires|priority|text": the priority, held to 1-3.
int Function PriorityOf(string asValue)
	string[] parts = StringUtil.Split(asValue, "|")
	int p = 1
	If parts && parts.Length >= 3
		p = parts[2] as int
	EndIf
	If p > 3
		Return 3
	ElseIf p < 1
		Return 1
	EndIf
	Return p
EndFunction

Function ClearStaged(string asPath)
	StorageUtil.StringListClear(None, "MLWS_FactName" + asPath)
	StorageUtil.StringListClear(None, "MLWS_FactValue" + asPath)
	StorageUtil.StringListClear(None, "MLWS_FactGone" + asPath)
	StorageUtil.StringListClear(None, "MLWS_FactKept" + asPath)
EndFunction

Event OnReportRequest()
	If !MLWS_Util.HubLoaded()
		Return
	EndIf
	MLW_Hub hub = Game.GetFormFromFile(0x000820, MLWS_Util.HUB_PLUGIN()) as MLW_Hub
	If hub
		hub.ReportAdd("survival", "survival mode on " + MLWS_Util.SurvivalOn() + ", SMI " + MLWS_Util.SmiLoaded() + ", settings file " + JsonUtil.IsGood(MLWS_Util.SETTINGS()))
	EndIf
EndEvent
