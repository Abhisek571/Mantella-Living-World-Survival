Scriptname MLWS_PlayerAlias extends ReferenceAlias
{Player alias on every Survival quest: re-registers the quest's events on each game load and passes the player's
sleep, sitting, feeding and race changes on.}

Event OnInit()
	RegisterSleep()
EndEvent

Event OnPlayerLoadGame()
	MLWS_Job job = GetOwningQuest() as MLWS_Job
	If job
		job.Register()
	EndIf
	RegisterSleep()
EndEvent

Function RegisterSleep()
	MLWS_Job job = GetOwningQuest() as MLWS_Job
	If job && job.WantsSleep()
		RegisterForSleep()
	EndIf
EndFunction

Event OnSleepStart(float afSleepStartTime, float afDesiredSleepEndTime)
	MLWS_Job job = GetOwningQuest() as MLWS_Job
	If job
		job.SleepStart(afSleepStartTime, afDesiredSleepEndTime)
	EndIf
EndEvent

Event OnSleepStop(bool abInterrupted)
	MLWS_Job job = GetOwningQuest() as MLWS_Job
	If job
		job.SleepStop(abInterrupted)
	EndIf
EndEvent

Event OnSit(ObjectReference akFurniture)
	MLWS_Job job = GetOwningQuest() as MLWS_Job
	If job
		job.Sat(akFurniture)
	EndIf
EndEvent

Event OnVampireFeed(Actor akTarget)
	MLWS_Job job = GetOwningQuest() as MLWS_Job
	If job
		job.Fed(akTarget)
	EndIf
EndEvent

Event OnRaceSwitchComplete()
	MLWS_Job job = GetOwningQuest() as MLWS_Job
	If job
		job.RaceSwitched()
	EndIf
EndEvent
