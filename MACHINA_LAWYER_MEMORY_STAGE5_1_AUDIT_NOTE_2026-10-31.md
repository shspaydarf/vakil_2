# Stage 5.1 baseline audit note

The Stage 4.5 archive contains schema groundwork for profile status and lifecycle change types, but does not contain implemented activate/deactivate/restore/delete service methods or corresponding API routes. It does contain bounded history listing and AI context gating on `status == active`.

A critical deletion detail was verified: `lawyer_preference_versions.user_id` has a foreign key to `users(user_id)`, not to `lawyer_preference_profiles(user_id)`. Therefore deleting the profile row alone does not remove version snapshots. A confirmed hard-delete operation must delete the owner's version rows and profile row explicitly in one transaction.

This note corrects the overstatement in the earlier conversational roadmap that implied all lifecycle controls already had implementation support. The status column and enum values are groundwork only.
