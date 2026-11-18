# Changelog

Every change to Mantella Living World - Survival. The Nexus page lists only the main changes for each version.

## 1.0.1 (2026-11-18)

### Changed
- EatThis is now a choice of ShareFood (player_eats): the same check and the same eating, one action less sent to the model on every reply. The old EatThis action still works for one version, so a talk running across the update is not broken.
- Shorter action descriptions.
- Two NPCs of one kind joining together no longer wipe each other's facts; facts are written after the action's reply is on its way; the facts no longer ask the Integration Hub to rewrite the whole file; while Survival Mode is off the 30 second check slows to every 5 minutes, so switching Survival Mode on brings the warnings back without a reload.

### Fixed
- The critical warning (for example starving) no longer goes into a talk between two other NPCs; it waits for a talk you are in, or starts one, instead of being spent where you never hear it.
- ShareFood without advanced actions no longer tells the NPC to use it when you give them food (that direction only works with advanced actions).
- Followers no longer say they have not eaten (or a vampire follower fed) in days while Survival Mode is off.
- Facts are gathered faster when an NPC joins a talk.

## 1.0.0 (2026-11-09)

First release.

### New
- With Survival Mode Improved, NPCs notice how you are getting by: hunger, cold and tiredness, what you ate and where you slept.
- Actions: eat this, share food, warm you.
- NPCs notice vampirism, and a cure.

### Fixed (before release)
- Disease names with more than one word were cut up, so the disease ignore list never matched.
- Generic NPCs of the same kind shared their wounded, drunk and diseased facts.
- Days since something happened could come out wrong early in a new game.
