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

namespace
{
	void OpenLog()
	{
		auto dir = logger::log_directory();
		if (!dir) {
			return;
		}
		auto path = *dir / "MLWS_Listener.log";
		auto sink = std::make_shared<spdlog::sinks::basic_file_sink_mt>(path.string(), true);
		auto log = std::make_shared<spdlog::logger>("global", std::move(sink));
		log->set_level(spdlog::level::info);
		log->flush_on(spdlog::level::info);
		log->set_pattern("[%Y-%m-%d %H:%M:%S] [%l] %v");
		spdlog::set_default_logger(std::move(log));
	}

	// A log that cannot be opened (for example a Documents path the ANSI code page cannot hold)
	// must not stop the plugin from loading: it then runs without its log.
	void SetupLog() noexcept
	{
		try {
			OpenLog();
		} catch (...) {
		}
	}

	void OnMessage(SKSE::MessagingInterface::Message* a_msg)
	{
		if (a_msg->type == SKSE::MessagingInterface::kDataLoaded) {
			MLWS::Survival::Register();
		}
	}
}

SKSE_PLUGIN_LOAD(const SKSE::LoadInterface* a_skse)
{
	SetupLog();
	SKSE::Init(a_skse, false);
	logger::info("MLWS_Listener {} loading", SKSE::PluginDeclaration::GetSingleton()->GetVersion().string());
	SKSE::GetMessagingInterface()->RegisterListener(OnMessage);
	if (!SKSE::GetPapyrusInterface()->Register(MLWS::Survival::RegisterFunctions)) {
		logger::error("Papyrus natives not registered");
	}
	return true;
}
