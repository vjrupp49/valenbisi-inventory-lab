// Cloudflare Worker: a reliable 10-minute timer that starts the GitHub "ingest" workflow.
// GitHub's own cron was running this repo about once every 7 hours, so we trigger it from outside.
// The secret GITHUB_TOKEN (fine-grained token, this repo only, Actions: read/write) is set in the
// Cloudflare dashboard, never in this file.

const REPO = "vjrupp49/valenbisi-inventory-lab";
const WORKFLOW = "ingest.yml";

async function dispatch(env) {
  const res = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "valenbisi-inventory-lab-timer",
      },
      body: JSON.stringify({ ref: "main" }),
    }
  );
  // GitHub answers 204 No Content on success.
  if (res.status !== 204) {
    throw new Error(`dispatch failed: ${res.status} ${await res.text()}`);
  }
  return res.status;
}

export default {
  // Runs on the cron schedule configured in Cloudflare.
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatch(env));
  },
  // Visiting the worker URL does nothing except show it is alive (no way to trigger runs by browsing).
  async fetch() {
    return new Response("valenbisi timer: alive. Triggers only on schedule.\n");
  },
};
