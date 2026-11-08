MLWS_Listener - food and condition reader for Mantella Living World - Survival
Copyright (C) 2026 itsPigeon2000

This program is free software: you can redistribute it and/or modify it under the terms of
the GNU General Public License as published by the Free Software Foundation, either
version 3 of the License, or (at your option) any later version. See LICENSE.txt.

Built against CommonLibSSE-NG (GPL-3.0). Skyrim SE 1.5.97 and AE 1.6.x, needs SKSE and
Address Library. Install as SKSE/Plugins/MLWS_Listener.dll.


What it does
------------
Mod event "MLWS_Ate"
    Event OnAte(string eventName, string itemName, float flags, Form sender)
    sender = the player or a party member (IsPlayerTeammate), itemName = the item's name,
    flags = 1 raw (keyword VendorItemFoodRaw), 2 alcohol (effect FoodDamageStaminaRate),
    4 blood potion.
Source: TESEquipEvent + AlchemyItem::IsFood(), the same check Survival Mode Improved uses. Blood
potions are not flagged as food, so they are matched against a short form list (Dawnguard, Better
Vampires, cckrtsse001_altar.esl, Dynamic Things Alternative; missing plugins are skipped).

Papyrus natives (script MLWS_Native):
  Actor[] PartyNear(float radius)                living teammates in the high process list, nearest first
  Actor[] WitnessesNear(Actor skip, float radius) living NPCs in range with line of sight to the player
  int     FoodCount(Actor)                       food items carried
  Form    PickFood(Actor, bool blood)            one item to eat, never a quest item: cooked before raw,
                                                 no alcohol if avoidable, cheapest first
  int     FoodFlags(Form)                        the flags above for one item
  string  DiseaseNames(Actor)                    active disease spells, comma separated, without
                                                 Sanguinare Vampiris
  bool    KnowsFire(Actor)                       a spell with keyword MagicDamageFire on the NPC's record or
                                                 added since. Leveled spell lists are not read.

Threading: the sink only queues an SKSE task; game reads and the mod event run on the main thread.
No polling and no file writes.

Log: Documents/My Games/Skyrim Special Edition/SKSE/MLWS_Listener.log


Building
--------
  .\build.ps1      (VS 2022 Build Tools, CMake, Ninja, vcpkg; output build\release\MLWS_Listener.dll)
CommonLibSSE-NG is expected in lib\commonlibsse-ng.
