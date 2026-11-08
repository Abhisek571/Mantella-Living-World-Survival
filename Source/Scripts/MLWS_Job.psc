Scriptname MLWS_Job extends Quest
{Base of every Mantella Living World - Survival quest. Register() runs from OnInit and again on every game load (the
quest's player alias calls it), so a save made before a registration existed still gets it.}

Actor Property PlayerRef Auto

Event OnInit()
	Register()
EndEvent

; Each job registers its mod events here. Safe to call any number of times.
Function Register()
EndFunction

; Writes or clears this job's facts in the NPC's file. Called once when the NPC joins a talk; the caller saves.
Function WriteFacts(Actor akNpc, string asPath, bool abParty, float afNow)
EndFunction

; Only the quest that tracks beds asks for sleep events.
bool Function WantsSleep()
	Return false
EndFunction

; Player alias events.
Function SleepStart(float afStart, float afDesiredEnd)
EndFunction

Function SleepStop(bool abInterrupted)
EndFunction

Function Sat(ObjectReference akFurniture)
EndFunction

Function Fed(Actor akTarget)
EndFunction

Function RaceSwitched()
EndFunction
