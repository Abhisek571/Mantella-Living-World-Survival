Scriptname MLWS_SMI Hidden
{The only script that calls Survival Mode Improved's API, so nothing else names a script that may not be installed.
Call it after MLWS_Util.SmiLoaded().}

Function RestoreHunger(float afAmount) global
	SurvivalModeImprovedApi.RestoreHungerLevel(afAmount)
EndFunction

Function RestoreCold(float afAmount) global
	SurvivalModeImprovedApi.RestoreColdLevel(afAmount)
EndFunction
