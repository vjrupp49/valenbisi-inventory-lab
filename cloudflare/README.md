# Outside timer for the collector (Cloudflare Worker)

Why: GitHub's built-in scheduler ran `ingest.yml` about once every 7 hours instead of every 10 minutes.
This Worker calls GitHub every 10 minutes to start the same workflow. Nothing about the collector changes.

Setup (dashboard only, no installs):
1. GitHub token: github.com > Settings > Developer settings > Fine-grained tokens > Generate.
   Repository access: only `valenbisi-inventory-lab`. Permissions: Actions = Read and write (nothing else).
   Expiration: the longest offered. Copy the token once.
2. Cloudflare: free account > Workers & Pages > Create > Create Worker > name `valenbisi-timer` > Deploy,
   then Edit code, paste `worker.js`, Deploy.
3. Worker > Settings > Variables and Secrets > Add: type Secret, name `GITHUB_TOKEN`, paste the token.
4. Worker > Settings > Triggers > Cron Triggers > Add: `*/10 * * * *`.
5. Check: GitHub > Actions > ingest should show runs labelled `workflow_dispatch` about every 10 minutes.

When the token expires the timer stops and the daily `health` workflow opens an issue. Create a new token
and replace the secret.
