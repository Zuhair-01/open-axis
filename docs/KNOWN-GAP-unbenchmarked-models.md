# Known gap: the 7 free OpenCode models are currently unroutable

Correct-but-inconvenient consequence of the "never assume an unbenchmarked
model meets a floor" rule: `opencode/big-pickle` and friends have
`capability_tier: "UNKNOWN"` in `registry/models/model_registry.json`, so
`model_selector.py` excludes them from **every** floor, including D
(high-volume/cheap). Right now, with 0 authenticated providers, the router
will BLOCK on literally any task rather than silently using an unrated model.

This is intentional per the hard safety rule, but it means nothing is
routable yet. Two ways to close this, your call:

1. **Benchmark them** - run a handful of real Tier-D tasks (simple
   edits/formatting) through each free model, judge the output, then set
   `capability_tier: "D"` in the registry for the ones that hold up. This is
   the honest way - I won't do it silently since it's a quality judgment.
2. **Authenticate a real provider** (`opencode auth login`) - once Claude or
   GPT is wired into OpenCode with a verified tier, routing works immediately
   for A/B/C floors, and you can still choose to leave D-floor tasks blocked
   until (1) is done, or benchmark just enough to unblock D.
