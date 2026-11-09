Scriptname MLWS_Actions extends MLWS_Job
{Mantella Living World - Survival: the three actions.
  ShareFood: party members only; one real item moves between the NPC and the player and the one who received it eats it.
  EatThis: the player eats something the NPC gave them or from their own pack. Hunger is restored through SMI's API when
           SMI is on, otherwise the item is simply eaten.
  WarmYou: an NPC who really has a fire spell makes a show of flames (a vanilla shader, no damage) and SMI's cold need
           comes down. Refused without SMI.
Each refuses with an event line when it cannot apply. Every path tells Mantella the action is done.}

MLWS_Job Property Food Auto
MLWS_Job Property Condition Auto
MLWS_Facts Property Facts Auto  ; rewrites the NPC's facts after an action, so the running talk sees the change

string Property ACTION_SHARE = "mantella_mlws_share_food" AutoReadOnly
string Property ACTION_EAT = "mantella_mlws_eat_this" AutoReadOnly
string Property ACTION_WARM = "mantella_mlws_warm_you" AutoReadOnly
string Property ADVANCED = "MantellaConversation_Advanced_Action_" AutoReadOnly
string Property LEGACY = "MantellaConversation_Action_" AutoReadOnly
float Property FOOD_COOLDOWN = 0.02 AutoReadOnly   ; half an hour of game time
float Property WARM_COOLDOWN = 0.1 AutoReadOnly

Function Register()
	RegisterForModEvent(ADVANCED + ACTION_SHARE, "OnShareAdvanced")
	RegisterForModEvent(LEGACY + ACTION_SHARE, "OnShareLegacy")
	RegisterForModEvent(ADVANCED + ACTION_EAT, "OnEatAdvanced")
	RegisterForModEvent(LEGACY + ACTION_EAT, "OnEatLegacy")
	RegisterForModEvent(ADVANCED + ACTION_WARM, "OnWarmAdvanced")
	RegisterForModEvent(LEGACY + ACTION_WARM, "OnWarmLegacy")
EndFunction

Event OnShareAdvanced(Form akSpeaker, Form akConversation, int aiArguments)
	MLWS_Util.Send(ShareFood(akSpeaker as Actor, SKSE_HTTP.getString(aiArguments, "direction", "npc_gives")))
	MLWS_Util.ActionDone(ACTION_SHARE)
EndEvent

; Mantella sent no arguments: the NPC gives.
Event OnShareLegacy(Form akSpeaker)
	MLWS_Util.Send(ShareFood(akSpeaker as Actor, "npc_gives"))
	MLWS_Util.ActionDone(ACTION_SHARE)
EndEvent

Event OnEatAdvanced(Form akSpeaker, Form akConversation, int aiArguments)
	MLWS_Util.Send(EatThis(akSpeaker as Actor))
	MLWS_Util.ActionDone(ACTION_EAT)
EndEvent

Event OnEatLegacy(Form akSpeaker)
	MLWS_Util.Send(EatThis(akSpeaker as Actor))
	MLWS_Util.ActionDone(ACTION_EAT)
EndEvent

Event OnWarmAdvanced(Form akSpeaker, Form akConversation, int aiArguments)
	MLWS_Util.Send(WarmYou(akSpeaker as Actor))
	MLWS_Util.ActionDone(ACTION_WARM)
EndEvent

Event OnWarmLegacy(Form akSpeaker)
	MLWS_Util.Send(WarmYou(akSpeaker as Actor))
	MLWS_Util.ActionDone(ACTION_WARM)
EndEvent

; ---------------------------------------------------------------------------
; The actions: each returns the event line
; ---------------------------------------------------------------------------

string Function ShareFood(Actor akNpc, string asDirection)
	string player = MLWS_Util.PlayerName()
	If !Usable(akNpc)
		Return "Nobody could share food just now."
	EndIf
	string name = akNpc.GetDisplayName()
	If !MLWS_Util.IsParty(akNpc)
		Return name + " is not travelling with " + player + "."
	EndIf
	float now = Utility.GetCurrentGameTime()
	If now - StorageUtil.GetFloatValue(akNpc, "MLWS_SharedAt", -1000.0) < FOOD_COOLDOWN
		Return name + " shared food moments ago; nothing more changed hands."
	EndIf
	Actor giver = akNpc
	Actor taker = PlayerRef
	If asDirection == "player_gives"
		giver = PlayerRef
		taker = akNpc
	EndIf
	bool blood = MLWS_Util.IsVampire(taker)
	If blood && taker == PlayerRef && !KnowsPlayerVampire(akNpc)
		blood = false  ; a hidden vampire takes plain food like anyone; the event line is heard by the whole talk
	EndIf
	Form item = MLWS_Native.PickFood(giver, blood)
	If !item
		If blood
			Return giver.GetDisplayName() + " has no blood to give, and " + taker.GetDisplayName() + " has no use for anything else."
		EndIf
		Return giver.GetDisplayName() + " has no food to give."
	EndIf
	string itemName = item.GetName()
	giver.RemoveItem(item, 1, true, taker)
	(Food as MLWS_Food).Record(taker, itemName, MLWS_Native.FoodFlags(item), true)  ; before the equip, so its event is known
	taker.EquipItem(item, false, true)
	StorageUtil.SetFloatValue(akNpc, "MLWS_SharedAt", now)
	Facts.Write(akNpc)
	Return giver.GetDisplayName() + " gave " + itemName + " to " + taker.GetDisplayName() + ", who ate it."
EndFunction

string Function EatThis(Actor akNpc)
	string player = MLWS_Util.PlayerName()
	If !Usable(akNpc)
		Return "Nobody could hand over food just now."
	EndIf
	If !MLWS_Util.IsParty(akNpc)
		Return akNpc.GetDisplayName() + " is not travelling with " + player + "."
	EndIf
	If MLWS_Util.IsVampire(PlayerRef) && KnowsPlayerVampire(akNpc)
		Return player + " has no need of food."  ; otherwise a hidden vampire eats like anyone
	EndIf
	string name = akNpc.GetDisplayName()
	float now = Utility.GetCurrentGameTime()
	If now - StorageUtil.GetFloatValue(akNpc, "MLWS_SharedAt", -1000.0) < FOOD_COOLDOWN
		Return name + " shared food moments ago; " + player + " did not eat again."
	EndIf
	bool smi = MLWS_Util.SmiLoaded() && MLWS_Util.SurvivalOn()
	int hunger = (Condition as MLWS_Condition).Stage(0)  ; Survival Mode's own hunger, with or without SMI
	If hunger >= 0 && hunger < 2
		Return player + " is not hungry and did not eat."
	EndIf
	Actor giver = akNpc
	Form item = MLWS_Native.PickFood(akNpc, false)
	If !item
		giver = PlayerRef
		item = MLWS_Native.PickFood(PlayerRef, false)
	EndIf
	If !item
		Return "Neither " + name + " nor " + player + " has any food."
	EndIf
	string itemName = item.GetName()
	int flags = MLWS_Native.FoodFlags(item)
	(Food as MLWS_Food).Record(PlayerRef, itemName, flags, !smi)  ; before any equip, so its event is known
	If smi
		; Removed, not equipped: SMI would restore hunger for the same item a second time.
		giver.RemoveItem(item, 1, true)
		MLWS_SMI.RestoreHunger(MLWS_Util.SettingFloat("eat_this_hunger", 80.0))
	Else
		If giver != PlayerRef
			giver.RemoveItem(item, 1, true, PlayerRef)
		EndIf
		PlayerRef.EquipItem(item, false, true)
	EndIf
	StorageUtil.SetFloatValue(akNpc, "MLWS_SharedAt", now)
	Facts.Write(akNpc)
	Return player + " ate " + itemName + " at " + name + "'s urging."
EndFunction

string Function WarmYou(Actor akNpc)
	string player = MLWS_Util.PlayerName()
	If !Usable(akNpc)
		Return "Nobody could conjure warmth just now."
	EndIf
	string name = akNpc.GetDisplayName()
	If !MLWS_Native.KnowsFire(akNpc)
		Return name + " knows no fire spell and conjured no warmth."
	EndIf
	If !MLWS_Util.SmiLoaded() || !MLWS_Util.SurvivalOn()
		Return name + " conjured no warmth: it would change nothing here."
	EndIf
	If (Condition as MLWS_Condition).Stage(1) < 2
		Return player + " is not cold; " + name + " conjured no warmth."
	EndIf
	float now = Utility.GetCurrentGameTime()
	If now - StorageUtil.GetFloatValue(akNpc, "MLWS_WarmedAt", -1000.0) < WARM_COOLDOWN
		Return name + " warmed " + player + " moments ago and cannot do more yet."
	EndIf
	EffectShader flames = Game.GetFormFromFile(0x02ACD8, "Skyrim.esm") as EffectShader  ; FireCloakFXShader
	If flames
		flames.Play(akNpc, 4.0)
	EndIf
	MLWS_SMI.RestoreCold(MLWS_Util.SettingFloat("warm_you_cold", 150.0))
	StorageUtil.SetFloatValue(akNpc, "MLWS_WarmedAt", now)
	Facts.Write(akNpc)
	Return name + " conjured flames and warmed " + player + "."
EndFunction

; The same NPCs MLWS_Vampire tells: close party members and witnesses of a feeding. The event line is heard by the
; whole talk, so every NPC in it must know.
bool Function KnowsPlayerVampire(Actor akNpc)
	If !KnowsOne(akNpc)
		Return false
	EndIf
	If !MLWS_Util.PluginLoaded("Mantella.esp")
		Return true
	EndIf
	MantellaConversation talk = Game.GetFormFromFile(0x03D41A, "Mantella.esp") as MantellaConversation
	If !talk || !talk.IsRunning()
		Return true
	EndIf
	int i = talk.CountActorsInConversation()
	While i > 0
		i -= 1
		Actor other = talk.GetActorInConversationByIndex(i)
		If other && other != PlayerRef && other != akNpc && !KnowsOne(other)
			Return false
		EndIf
	EndWhile
	Return true
EndFunction

bool Function KnowsOne(Actor akNpc)
	; Only unique NPCs are told (MLWS_Vampire.PlayerFacts): NPCs of one record share one file.
	Return akNpc.GetActorBase().IsUnique() && (MLWS_Util.IsClose(akNpc) || MLWS_Util.SawVampire(akNpc))
EndFunction

bool Function Usable(Actor akNpc)
	Return akNpc && akNpc != PlayerRef && !akNpc.IsDead() && !akNpc.IsInCombat()
EndFunction

; ---------------------------------------------------------------------------
; Gates the Hub's action filter reads
; ---------------------------------------------------------------------------

; surv_warm opens WarmYou only for an NPC with a fire spell while SMI's cold need is running.
Function WriteFacts(Actor akNpc, string asPath, bool abParty, float afNow)
	bool canWarm = MLWS_Util.SmiLoaded() && MLWS_Util.SurvivalOn() && MLWS_Native.KnowsFire(akNpc)
	JsonUtil.SetIntValue(asPath, "surv_warm", canWarm as int)
EndFunction
