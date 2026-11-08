Scriptname MLWS_Facts extends MLWS_Job
{Mantella Living World - Survival: when an NPC joins a Mantella talk, every job writes or clears its facts in that NPC's
file (fact_surv_*, read by the Hub), and the file is saved once. Only what applies now is written; a healthy player in
town adds almost nothing to anyone who is not in the party.}

MLWS_Job Property Condition Auto
MLWS_Job Property Food Auto
MLWS_Job Property Beds Auto
MLWS_Job Property Vampire Auto
MLWS_Job Property Actions Auto

Function Register()
	RegisterForModEvent("MantellaConversation_NPC_Added", "OnNpcAdded")
	RegisterForModEvent("MLW_ReportRequest", "OnReportRequest")
EndFunction

Event OnNpcAdded(Form akActor)
	Actor npc = akActor as Actor
	If npc && npc != PlayerRef && !npc.IsDead()
		Write(npc)
	EndIf
EndEvent

; Also called after an action changes something, so a running talk sees it.
Function Write(Actor akNpc)
	string path = MLWS_Util.NpcFile(akNpc)
	float now = Utility.GetCurrentGameTime()
	bool party = MLWS_Util.IsParty(akNpc)
	If party && !StorageUtil.HasFloatValue(akNpc, "MLWS_SeenAt")
		StorageUtil.SetFloatValue(akNpc, "MLWS_SeenAt", now)  ; the clocks for food and sleep start here, not at day zero
	EndIf
	; The jobs only gather their facts; Commit then writes them, so the file never holds a half-cleared set.
	ClearStaged(path)  ; anything left by a write that was cut off
	; Vampire first: within a priority Commit keeps the write order, and the late-stage signs must not be cut by conditions.
	Vampire.WriteFacts(akNpc, path, party, now)
	Condition.WriteFacts(akNpc, path, party, now)
	Food.WriteFacts(akNpc, path, party, now)
	Beds.WriteFacts(akNpc, path, party, now)
	Actions.WriteFacts(akNpc, path, party, now)
	Commit(path)
	JsonUtil.Save(path)
	int handle = ModEvent.Create("MLW_RefreshNpc")
	If handle
		ModEvent.PushForm(handle, akNpc)
		ModEvent.Send(handle)
	EndIf
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
