# Changelog

Every change to Mantella Living World - Survival. The Nexus page lists only the main changes for each version.

## Unreleased

### Changed
- EatThis is now a choice of ShareFood (player_eats): the same check and the same eating, one action less sent to the model on every reply. The old EatThis action still works for one version, so a talk running across the update is not broken.
- Shorter action descriptions.
- Two NPCs of one kind joining together no longer wipe each other's facts; facts are written after the action's reply is on its way; the facts no longer ask the Integration Hub to rewrite the whole file; the 30 second check stops while Survival Mode is off (it starts again on the next load).

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
