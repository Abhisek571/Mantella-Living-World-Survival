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

#include "Survival.h"

namespace MLWS::Survival
{
	namespace
	{
		constexpr RE::FormID kKeywordFoodRaw = 0x0A0E56;      // VendorItemFoodRaw
		constexpr RE::FormID kEffectAlcohol = 0x10C645;       // FoodDamageStaminaRate: every vanilla ale, mead and wine has it
		constexpr RE::FormID kKeywordFire = 0x01CEAD;         // MagicDamageFire
		constexpr RE::FormID kDiseaseSanguinare = 0x0B8780;   // DiseaseSanguinareVampiris: never named, it would give a vampire away

		constexpr std::int32_t kFlagRaw = 1;
		constexpr std::int32_t kFlagAlcohol = 2;
		constexpr std::int32_t kFlagBlood = 4;

		std::unordered_set<RE::FormID> g_bloodPotions;  // filled once at kDataLoaded
		std::string                    g_sanguinareName;  // vampirism's disease name in the game's language

		RE::PlayerCharacter* Player() { return RE::PlayerCharacter::GetSingleton(); }

		// Summons and raised thralls count as teammates but are not party members.
		bool IsPartyMember(RE::Actor* a_actor)
		{
			return a_actor && a_actor->IsPlayerTeammate() && !a_actor->IsCommandedActor();
		}

		// Blood potions are not flagged as food, so SMI's IsFood check and ours would both miss them.
		void FindBloodPotions()
		{
			struct Entry
			{
				RE::FormID       id;
				std::string_view file;
			};
			constexpr Entry entries[] = {
				{ 0x018EF3, "Dawnguard.esm"sv },         // DLC1BloodPotion
				{ 0x50AF47, "Better Vampires.esp"sv },   // Stale Blood Potion
				{ 0x6C2A37, "Better Vampires.esp"sv },   // Harkon's Blood
				{ 0x6C2A38, "Better Vampires.esp"sv },   // Miraak's Blood
				{ 0x000811, "cckrtsse001_altar.esl"sv }, // Potion of Blood
				{ 0x00088B, "Dynamic Things Alternative.esp"sv },
			};
			auto* data = RE::TESDataHandler::GetSingleton();
			if (!data) {
				return;
			}
			for (const auto& entry : entries) {
				if (auto* form = data->LookupForm(entry.id, entry.file)) {
					g_bloodPotions.insert(form->GetFormID());
				}
			}
		}

		bool HasEffect(const RE::MagicItem* a_item, RE::FormID a_effect)
		{
			for (const auto* effect : a_item->effects) {
				if (effect && effect->baseEffect && effect->baseEffect->GetFormID() == a_effect) {
					return true;
				}
			}
			return false;
		}

		bool IsFood(RE::TESBoundObject& a_obj)
		{
			auto* item = a_obj.As<RE::AlchemyItem>();
			return item && item->IsFood();
		}

		std::int32_t Flags(RE::AlchemyItem* a_item)
		{
			std::int32_t flags = 0;
			if (a_item->HasKeywordID(kKeywordFoodRaw)) {
				flags |= kFlagRaw;
			}
			if (HasEffect(a_item, kEffectAlcohol)) {
				flags |= kFlagAlcohol;
			}
			if (g_bloodPotions.contains(a_item->GetFormID())) {
				flags |= kFlagBlood;
			}
			return flags;
		}

		void OnEquip(RE::NiPointer<RE::TESObjectREFR> a_actor, RE::FormID a_base)
		{
			auto* actor = a_actor ? a_actor->As<RE::Actor>() : nullptr;
			auto* item = RE::TESForm::LookupByID<RE::AlchemyItem>(a_base);
			if (!actor || !item) {
				return;
			}
			const auto flags = Flags(item);
			if (!item->IsFood() && !(flags & kFlagBlood)) {
				return;
			}
			if (actor != Player() && !IsPartyMember(actor)) {
				return;  // only the player and the party are tracked
			}
			const char* name = item->GetName();
			SKSE::ModCallbackEvent event{ "MLWS_Ate", name ? name : "", static_cast<float>(flags), actor };
			SKSE::GetModCallbackEventSource()->SendEvent(&event);
			logger::info("{:08X} ate {} (flags {})", actor->GetFormID(), name ? name : "", flags);
		}

		class EquipSink final : public RE::BSTEventSink<RE::TESEquipEvent>
		{
		public:
			RE::BSEventNotifyControl ProcessEvent(const RE::TESEquipEvent* a_event, RE::BSTEventSource<RE::TESEquipEvent>*) override
			{
				if (a_event && a_event->equipped && a_event->actor) {
					SKSE::GetTaskInterface()->AddTask([actor = a_event->actor, base = a_event->baseObject]() { OnEquip(actor, base); });
				}
				return RE::BSEventNotifyControl::kContinue;
			}
		};

		// Natives

		// Living party members in the player's process range, nearest first.
		std::vector<RE::Actor*> PartyNear(RE::StaticFunctionTag*, float a_radius)
		{
			std::vector<std::pair<float, RE::Actor*>> found;
			auto*                                     player = Player();
			auto*                                     lists = RE::ProcessLists::GetSingleton();
			if (player && lists) {
				const auto here = player->GetPosition();
				for (auto& handle : lists->highActorHandles) {
					auto actor = handle.get();
					if (!actor || actor->IsDead() || !IsPartyMember(actor.get()) || actor->GetParentCell() == nullptr) {
						continue;
					}
					const float distance = actor->GetPosition().GetDistance(here);
					if (distance <= a_radius && actor->GetWorldspace() == player->GetWorldspace()) {
						found.emplace_back(distance, actor.get());
					}
				}
			}
			std::sort(found.begin(), found.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
			std::vector<RE::Actor*> out;
			out.reserve(found.size());
			for (auto& [distance, actor] : found) {
				out.push_back(actor);
			}
			return out;
		}

		// Living, awake NPCs within range who can see the player and have detected them (as crime witnesses do), leaving
		// out a_skip (the feeding victim).
		std::vector<RE::Actor*> WitnessesNear(RE::StaticFunctionTag*, RE::Actor* a_skip, float a_radius)
		{
			std::vector<RE::Actor*> out;
			auto*                   player = Player();
			auto*                   lists = RE::ProcessLists::GetSingleton();
			if (!player || !lists) {
				return out;
			}
			const auto here = player->GetPosition();
			for (auto& handle : lists->highActorHandles) {
				auto actor = handle.get();
				if (!actor || actor.get() == a_skip || actor->IsDead() || actor->GetPosition().GetDistance(here) > a_radius) {
					continue;
				}
				// Sleepers and the unconscious see nothing, whatever the line of sight says.
				const auto* state = actor->AsActorState();
				if (state && (state->GetSitSleepState() >= RE::SIT_SLEEP_STATE::kWantToSleep || state->IsUnconscious())) {
					continue;
				}
				bool ignored = false;
				if (actor->HasLineOfSight(player, ignored) && actor->RequestDetectionLevel(player) > 0) {
					out.push_back(actor.get());
				}
			}
			return out;
		}

		std::int32_t FoodCount(RE::StaticFunctionTag*, RE::Actor* a_actor)
		{
			std::int32_t total = 0;
			if (a_actor) {
				for (auto& [obj, count] : a_actor->GetInventoryCounts(IsFood)) {
					if (count > 0) {  // an item taken out of the base container counts below 0
						total += count;
					}
				}
			}
			return total;
		}

		// One item to eat, never a quest item. Food: cooked before raw, sober before alcohol, then the cheapest,
		// so a player's best food is the last to go. Blood: any blood potion.
		RE::TESForm* PickFood(RE::StaticFunctionTag*, RE::Actor* a_actor, bool a_blood)
		{
			if (!a_actor) {
				return nullptr;
			}
			RE::TESForm* best = nullptr;
			std::int64_t bestRank = 0;
			auto         inventory = a_actor->GetInventory([a_blood](RE::TESBoundObject& a_obj) {
                auto* item = a_obj.As<RE::AlchemyItem>();
                return item && (a_blood ? g_bloodPotions.contains(item->GetFormID()) : item->IsFood());
            });
			for (auto& [obj, data] : inventory) {
				auto& entry = data.second;
				if (data.first <= 0 || (entry && entry->IsQuestObject())) {
					continue;
				}
				auto*              item = obj->As<RE::AlchemyItem>();
				const auto         flags = Flags(item);
				const std::int64_t rank = (flags & kFlagRaw ? 1'000'000 : 0) + (flags & kFlagAlcohol ? 2'000'000 : 0) + item->GetGoldValue();
				if (!best || rank < bestRank) {
					best = item;
					bestRank = rank;
				}
			}
			return best;
		}

		// Bits for an item: 1 raw, 2 alcohol, 4 blood. 0 for anything else.
		std::int32_t FoodFlags(RE::StaticFunctionTag*, RE::TESForm* a_item)
		{
			auto* item = a_item ? a_item->As<RE::AlchemyItem>() : nullptr;
			return item ? Flags(item) : 0;
		}

		// Names of the diseases on an actor, comma separated; vampirism's disease is left out.
		RE::BSFixedString DiseaseNames(RE::StaticFunctionTag*, RE::Actor* a_actor)
		{
			auto* target = a_actor ? a_actor->AsMagicTarget() : nullptr;
			auto* effects = target ? target->GetActiveEffectList() : nullptr;
			if (!effects) {
				return "";
			}
			std::vector<RE::FormID> seen;
			std::string             names;
			for (auto* effect : *effects) {
				auto* spell = effect ? effect->spell : nullptr;
				if (!spell || spell->GetSpellType() != RE::MagicSystem::SpellType::kDisease || spell->GetFormID() == kDiseaseSanguinare) {
					continue;
				}
				// Copies of it (Dawnguard's trap version, other mods' own) share its name.
				const char* name = spell->GetName();
				if (name && !g_sanguinareName.empty() && g_sanguinareName == name) {
					continue;
				}
				if (std::find(seen.begin(), seen.end(), spell->GetFormID()) != seen.end()) {
					continue;
				}
				seen.push_back(spell->GetFormID());
				if (name && *name) {
					if (!names.empty()) {
						names += ", ";
					}
					names += name;
				}
			}
			return names;
		}

		bool IsFireSpell(const RE::SpellItem* a_spell)
		{
			if (!a_spell || a_spell->GetSpellType() != RE::MagicSystem::SpellType::kSpell) {
				return false;
			}
			for (const auto* effect : a_spell->effects) {
				if (effect && effect->baseEffect && effect->baseEffect->HasKeywordID(kKeywordFire)) {
					return true;
				}
			}
			return false;
		}

		// True when the actor really has a fire spell: on their record or added since.
		bool KnowsFire(RE::StaticFunctionTag*, RE::Actor* a_actor)
		{
			if (!a_actor) {
				return false;
			}
			for (const auto* spell : a_actor->GetActorRuntimeData().addedSpells) {
				if (IsFireSpell(spell)) {
					return true;
				}
			}
			auto* base = a_actor->GetActorBase();
			auto* list = base ? base->GetSpellList() : nullptr;
			if (list && list->spells) {
				for (std::uint32_t i = 0; i < list->numSpells; ++i) {
					if (IsFireSpell(list->spells[i])) {
						return true;
					}
				}
			}
			return false;
		}
	}

	void Register()
	{
		FindBloodPotions();
		if (auto* sanguinare = RE::TESForm::LookupByID<RE::SpellItem>(kDiseaseSanguinare); sanguinare && sanguinare->GetName()) {
			g_sanguinareName = sanguinare->GetName();
		}
		auto* holder = RE::ScriptEventSourceHolder::GetSingleton();
		if (!holder) {
			logger::error("event source missing; food is not tracked");
			return;
		}
		static EquipSink equip;
		holder->AddEventSink<RE::TESEquipEvent>(&equip);
		logger::info("equip listener registered ({} blood potions known)", g_bloodPotions.size());
	}

	bool RegisterFunctions(RE::BSScript::IVirtualMachine* a_vm)
	{
		a_vm->RegisterFunction("PartyNear", "MLWS_Native", PartyNear);
		a_vm->RegisterFunction("WitnessesNear", "MLWS_Native", WitnessesNear);
		a_vm->RegisterFunction("FoodCount", "MLWS_Native", FoodCount);
		a_vm->RegisterFunction("PickFood", "MLWS_Native", PickFood);
		a_vm->RegisterFunction("FoodFlags", "MLWS_Native", FoodFlags);
		a_vm->RegisterFunction("DiseaseNames", "MLWS_Native", DiseaseNames);
		a_vm->RegisterFunction("KnowsFire", "MLWS_Native", KnowsFire);
		return true;
	}
}
