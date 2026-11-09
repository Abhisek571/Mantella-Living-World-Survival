// MLWS_Listener - food and condition reader for Mantella Living World - Survival
// Copyright (C) 2026 itsPigeon2000
//
// This program is free software: you can redistribute it and/or modify it under the terms
// of the GNU General Public License as published by the Free Software Foundation, either
// version 3 of the License, or (at your option) any later version.
//
// This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
// without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
// See the GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License along with this program.
// If not, see <https://www.gnu.org/licenses/>.

#pragma once

namespace MLWS::Survival
{
	// Registers the equip sink that reports what the player and party members eat. Call at kDataLoaded.
	void Register();

	// Papyrus natives (script MLWS_Native).
	bool RegisterFunctions(RE::BSScript::IVirtualMachine* a_vm);
}
