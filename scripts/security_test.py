# Quick-exit button — server component, no JS required.
# On a single click → opens a neutral page (Google) in a new tab and replaces
# the current tab with it. This is the standard pattern for safety UX on
# domestic-violence / LGBTQ+ helplines.
#
# Esc key: handled by the small inline script in <head> of root layout (Esc
# → bfcache redirect to google.com).
#
# We do NOT replace the history entry — out of scope for v1 (would require
# client component with router.push).
</content>