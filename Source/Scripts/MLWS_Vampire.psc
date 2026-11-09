Scriptname MLWS_Vampire extends MLWS_Job
{Mantella Living World - Survival: vampires, so that a hidden one stays hidden.

An NPC reader who is a vampire knows it: "You are a vampire" (pure-bloods by name), daylight weakness outdoors (not
pure-bloods), and a party member's hunger as days since feeding (the clock starts when first seen; blood potions reset it).

The player, from PlayerVampireQuest (vanilla and Better Vampires share VampireStatus 1-4 and LastFeedTime):
  anyone: signs on the player's face only at the late stage (settings: visible_stage), not under Better Vampires' Mortal's Mask;
  close party members and witnesses: that the player is a vampire, when and on whom they last fed, sun weakness, hunger stage;
  witnesses are NPCs in sight who detect the player when a feeding sends OnVampireFeed, an awake victim, and NPCs in
  sight when the player turns into a Vampire Lord. Bottled blood counts as a feeding without a victim. A cure clears the
  feeding; older witnesses then remember it as something from the past.
Werewolf: the party knows the player changed in the last day.
NPC vampires fed by Vampire Feed Proxy's NpcVampireFeed event (Serana and other vampire followers) reset their hunger.}

string Property KEY_FED_AT = "MLWS_FedAt" AutoReadOnly
string Property KEY_VICTIM = "MLWS_FedVictim" AutoReadOnly
string Property KEY_SAW_AT = "MLWS_SawFeedAt" AutoReadOnly
string Property KEY_SAW_VICTIM = "MLWS_SawFeedVictim" AutoReadOnly
string Property KEY_WOLF = "MLWS_WolfAt" AutoReadOnly
string Property KEY_BLOOD_AT = "MLWS_BloodAt" AutoReadOnly
string Property KEY_SAW_LORD = "MLWS_SawLordAt" AutoReadOnly
string Property KEY_CURED = "MLWS_CuredAt" AutoReadOnly

Function Register()
	RegisterForModEvent("NpcVampireFeed", "OnNpcFeed")
EndFunction

; Vampire Feed Proxy sends this for NPC feeding, with the feeder as the sender (no dependency: the event is by name).
Event OnNpcFeed(string asEvent, string asTarget, float afLethal, Form akSender)
	Actor feeder = akSender as Actor
	If feeder
		StorageUtil.SetFloatValue(feeder, KEY_BLOOD_AT, Utility.GetCurrentGameTime())
	EndIf
EndEvent

; The stage of the player's vampirism, 0 when not one.
int Function PlayerStage()
	If !PlayerRef.HasKeyword(Game.GetFormFromFile(0x0A82BB, "Skyrim.esm") as Keyword)
		Return 0
	EndIf
	PlayerVampireQuestScript q = Game.GetFormFromFile(0x0EAFD5, "Skyrim.esm") as PlayerVampireQuestScript
	If q
		Return q.VampireStatus
	EndIf
	Return 0
EndFunction

; Game time of the player's last feeding, -1 when unknown.
float Function PlayerLastFed()
	; The later of our own stamp and the quest's: Better Vampires backdates LastFeedTime for bottled blood and partial
	; feeds (our stamp wins), and feeds that send no event (Vampire Lord bites, other mods) only move the quest's value.
	float at = StorageUtil.GetFloatValue(PlayerRef, KEY_FED_AT, -1.0)
	PlayerVampireQuestScript q = Game.GetFormFromFile(0x0EAFD5, "Skyrim.esm") as PlayerVampireQuestScript
	If q && q.LastFeedTime > at
		at = q.LastFeedTime
	EndIf
	If at <= 0.0
		Return -1.0
	EndIf
	Return at
EndFunction

Function Fed(Actor akTarget)
	float now = Utility.GetCurrentGameTime()
	string victim = ""
	If akTarget
		victim = akTarget.GetDisplayName()
	EndIf
	StorageUtil.SetFloatValue(PlayerRef, KEY_FED_AT, now)
	StorageUtil.SetStringValue(PlayerRef, KEY_VICTIM, victim)
	Actor[] seen = MLWS_Native.WitnessesNear(akTarget, 2048.0)
	bool sneaking = PlayerRef.IsSneaking()
	int count = 0
	int i = 0
	While i < seen.Length
		; the plugin already asks for detection; this keeps an older plugin from naming unseen witnesses
		If !sneaking || PlayerRef.IsDetectedBy(seen[i])
			StorageUtil.SetFloatValue(seen[i], KEY_SAW_AT, now)
			StorageUtil.SetStringValue(seen[i], KEY_SAW_VICTIM, victim)
			count += 1
		EndIf
		i += 1
	EndWhile
	; An awake victim felt the bite.
	If akTarget && !akTarget.IsDead() && akTarget.GetActorBase().IsUnique() && akTarget.GetSleepState() < 3 && !akTarget.IsUnconscious()
		StorageUtil.SetFloatValue(akTarget, KEY_SAW_AT, now)
		StorageUtil.SetStringValue(akTarget, KEY_SAW_VICTIM, "you")
		count += 1
	EndIf
	MLWS_Util.Log("fed on " + victim + ", " + count + " witnesses")
EndFunction

Function RaceSwitched()
	Race now = PlayerRef.GetRace()
	If !now
		Return
	EndIf
	float t = Utility.GetCurrentGameTime()
	Race lord = None
	If MLWS_Util.PluginLoaded("Dawnguard.esm")
		lord = Game.GetFormFromFile(0x00283A, "Dawnguard.esm") as Race  ; DLC1VampireBeastRace
	EndIf
	If now == Game.GetFormFromFile(0x0CDD84, "Skyrim.esm")  ; WerewolfBeastRace
		StorageUtil.SetFloatValue(PlayerRef, KEY_WOLF, t)
	ElseIf lord && now == lord
		Actor[] seen = MLWS_Native.WitnessesNear(None, 2048.0)
		int i = 0
		While i < seen.Length
			StorageUtil.SetFloatValue(seen[i], KEY_SAW_LORD, t)
			i += 1
		EndWhile
		MLWS_Util.Log("became a Vampire Lord, " + seen.Length + " witnesses")
	ElseIf PlayerStage() == 0
		; Not a vampire now: every sighting so far was of the vampire the player was before (a cure). The last feeding
		; belongs to that vampire too.
		StorageUtil.SetFloatValue(PlayerRef, KEY_CURED, t)
		If StorageUtil.GetFloatValue(PlayerRef, KEY_FED_AT, -1.0) >= 0.0
			StorageUtil.UnsetFloatValue(PlayerRef, KEY_FED_AT)
			StorageUtil.UnsetStringValue(PlayerRef, KEY_VICTIM)
			MLWS_Util.Log("cured of vampirism")
		EndIf
	EndIf
EndFunction

; Daylight outdoors, not hidden by storm clouds.
bool Function InSun()
	If PlayerRef.IsInInterior()
		Return false
	EndIf
	float now = Utility.GetCurrentGameTime()
	float hour = (now - (now as int)) * 24.0
	Weather sky = Weather.GetCurrentWeather()
	Return hour >= 7.0 && hour < 19.0 && (!sky || sky.GetClassification() <= 1)
EndFunction

Function WriteFacts(Actor akNpc, string asPath, bool abParty, float afNow)
	int today = afNow as int
	string player = MLWS_Util.PlayerName()
	SelfFacts(akNpc, asPath, abParty, afNow, today)
	PlayerFacts(akNpc, asPath, afNow, today, player)
	float wolf = StorageUtil.GetFloatValue(PlayerRef, KEY_WOLF, -1.0)
	If abParty && wolf >= 0.0 && afNow - wolf <= 1.0
		MLWS_Util.SetFact(asPath, "fact_surv_wolf", wolf as int, (wolf as int) + 1, 2, player + " changed into a werewolf")
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_wolf")
	EndIf
EndFunction

Function SelfFacts(Actor akNpc, string asPath, bool abParty, float afNow, int aiToday)
	If !MLWS_Util.IsVampire(akNpc)
		MLWS_Util.ClearFact(asPath, "fact_surv_v_self")
		MLWS_Util.ClearFact(asPath, "fact_surv_v_self_sun")
		MLWS_Util.ClearFact(asPath, "fact_surv_v_self_hunger")
		Return
	EndIf
	bool pure = MLWS_Util.IsPureBlood(akNpc)
	If pure
		MLWS_Util.SetFact(asPath, "fact_surv_v_self", -1, -1, 2, "You are a pure-blood vampire.")
	Else
		MLWS_Util.SetFact(asPath, "fact_surv_v_self", -1, -1, 2, "You are a vampire.")
	EndIf
	If !pure && InSun()
		MLWS_Util.SetNowFact(asPath, "fact_surv_v_self_sun", aiToday, 3, "You are in daylight, and the sun weakens you.")
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_v_self_sun")
	EndIf
	; Only the party is tracked: other vampires may feed without anyone knowing.
	int days = 0
	If abParty
		days = MLWS_Util.DaysSince(akNpc, KEY_BLOOD_AT, afNow)
	EndIf
	int most = MLWS_Util.SettingInt("follower_hungry_max", 7)
	If days > most && days >= MLWS_Util.SettingInt("vampire_hungry_days", 2)
		MLWS_Util.SetNowFact(asPath, "fact_surv_v_self_hunger", aiToday, 3, "You have not fed in over " + most + " days.")
	ElseIf days >= MLWS_Util.SettingInt("vampire_hungry_days", 2)
		MLWS_Util.SetNowFact(asPath, "fact_surv_v_self_hunger", aiToday, 3, "You have not fed in " + days + " days.")
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_v_self_hunger")
	EndIf
EndFunction

Function PlayerFacts(Actor akNpc, string asPath, float afNow, int aiToday, string asPlayer)
	int stage = PlayerStage()
	; NPCs of one record share one file, so what one of them knows would reach every other: only unique NPCs are told.
	bool unique = akNpc.GetActorBase().IsUnique()
	bool isClose = stage > 0 && unique && MLWS_Util.IsClose(akNpc)
	; A sighting from before the player's last cure is a memory of the old vampire, not knowledge of this one.
	float cured = StorageUtil.GetFloatValue(PlayerRef, KEY_CURED, -1.0)
	float sawAt = StorageUtil.GetFloatValue(akNpc, KEY_SAW_AT, -1.0)
	float lordAt = StorageUtil.GetFloatValue(akNpc, KEY_SAW_LORD, -1.0)
	bool sawFeed = stage > 0 && unique && sawAt >= 0.0 && sawAt >= cured
	bool sawOld = unique && sawAt >= 0.0 && sawAt < cured
	bool sawLord = stage > 0 && unique && lordAt >= 0.0 && lordAt >= cured
	bool witness = sawFeed || sawLord
	bool knows = isClose || witness

	If knows
		MLWS_Util.SetFact(asPath, "fact_surv_v_player", -1, -1, 2, asPlayer + " is a vampire.")
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_v_player")
	EndIf

	If sawFeed || sawOld
		MLWS_Util.SetFact(asPath, "fact_surv_v_saw", sawAt as int, -1, 2, SawText(asPlayer, StorageUtil.GetStringValue(akNpc, KEY_SAW_VICTIM), sawOld))
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_v_saw")
	EndIf

	If sawLord
		MLWS_Util.SetFact(asPath, "fact_surv_v_saw_lord", lordAt as int, -1, 2, "You saw " + asPlayer + " turn into a Vampire Lord")
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_v_saw_lord")
	EndIf

	float fed = PlayerLastFed()
	If isClose && fed >= 0.0
		string victim = StorageUtil.GetStringValue(PlayerRef, KEY_VICTIM)
		If victim != "" && StorageUtil.GetFloatValue(PlayerRef, KEY_FED_AT, -1.0) >= fed
			MLWS_Util.SetFact(asPath, "fact_surv_v_fed", fed as int, -1, 2, asPlayer + " last fed, on " + victim)
		Else
			MLWS_Util.SetFact(asPath, "fact_surv_v_fed", fed as int, -1, 2, asPlayer + " last fed")
		EndIf
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_v_fed")
	EndIf

	If knows && stage >= 3
		MLWS_Util.SetNowFact(asPath, "fact_surv_v_hunger", aiToday, 3, asPlayer + " is hungry for blood.")
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_v_hunger")
	EndIf

	If knows && InSun()
		MLWS_Util.SetNowFact(asPath, "fact_surv_v_sun", aiToday, 3, "The sun weakens " + asPlayer + " here.")
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_v_sun")
	EndIf

	If stage >= MLWS_Util.SettingInt("visible_stage", 4) && !Masked() && !MLWS_Util.FaceHidden(PlayerRef)
		MLWS_Util.SetNowFact(asPath, "fact_surv_v_signs", aiToday, 3, asPlayer + " has burning eyes, sunken skin and fangs.")
	Else
		MLWS_Util.ClearFact(asPath, "fact_surv_v_signs")
	EndIf
EndFunction

; asVictim is "you" when the NPC was the one bitten; abOld when it happened before the player's last cure.
string Function SawText(string asPlayer, string asVictim, bool abOld)
	string past = ""
	If abOld
		past = ", when they were a vampire"
	EndIf
	If asVictim == "you"
		If abOld
			Return asPlayer + " once fed on you" + past
		EndIf
		Return asPlayer + " fed on you"
	EndIf
	string on = ""
	If asVictim != ""
		on = " on " + asVictim
	EndIf
	If abOld
		Return "You once saw " + asPlayer + " feed" + on + past
	EndIf
	Return "You saw " + asPlayer + " feed" + on
EndFunction

; Better Vampires' Mortal's Mask hides the signs; so does a hood or helmet (MLWS_Util.FaceHidden, checked by the caller).
bool Function Masked()
	If !MLWS_Util.PluginLoaded("Better Vampires.esp")
		Return false
	EndIf
	MagicEffect mask = Game.GetFormFromFile(0x02793B, "Better Vampires.esp") as MagicEffect  ; VampireRemoveHate
	Return mask && PlayerRef.HasMagicEffect(mask)
EndFunction
