/**
 * Cloudflare Worker for the Bilibili price dashboard star list.
 * GET /stars returns the public star IDs. POST /stars updates one ID and
 * requires STAR_API_KEY; the GitHub write token stays in Worker secrets.
 */

const JSON_HEADERS = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "no-store",
};

function jsonResponse(body, status, origin) {
  const headers = new Headers(JSON_HEADERS);
  if (origin) {
    headers.set("Access-Control-Allow-Origin", origin);
    headers.set("Vary", "Origin");
  }
  return new Response(JSON.stringify(body), {status, headers});
}

function corsHeaders(origin) {
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

function encodeBase64Utf8(text) {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function decodeBase64Utf8(value) {
  const bytes = Uint8Array.from(atob(value.replace(/\s/g, "")), char => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function githubHeaders(env, json = false) {
  const headers = {
    "Accept": "application/vnd.github+json",
    "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
    "User-Agent": "bilibili-goods-star-api",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  if (json) headers["Content-Type"] = "application/json";
  return headers;
}

function fileEndpoint(env) {
  const repositoryParts = (env.MONITOR_REPOSITORY || "DRAMINGLING/Bilibili_Goods_Price_Monitor").split("/");
  if (repositoryParts.length !== 2 || repositoryParts.some(part => !part)) {
    throw new Error("MONITOR_REPOSITORY must be owner/repository");
  }
  const [owner, repository] = repositoryParts.map(encodeURIComponent);
  const branch = encodeURIComponent(env.MONITOR_BRANCH || "main");
  return `https://api.github.com/repos/${owner}/${repository}/contents/data/starred_products.json?ref=${branch}`;
}

async function readStars(env) {
  const response = await fetch(fileEndpoint(env), {headers: githubHeaders(env)});
  if (!response.ok) throw new Error(`GitHub read failed: ${response.status}`);
  const file = await response.json();
  const data = JSON.parse(decodeBase64Utf8(file.content));
  if (!data || !Array.isArray(data.product_ids)) {
    throw new Error("Star list has an invalid format");
  }
  return {productIds: [...new Set(data.product_ids.map(String))], sha: file.sha};
}

async function updateStars(env, productId, starred) {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const current = await readStars(env);
    const productIds = new Set(current.productIds);
    const alreadyStarred = productIds.has(productId);
    if (alreadyStarred === starred) {
      return {
        productIds: [...productIds].sort((a, b) => a.localeCompare(b, "en", {numeric: true})),
        changed: false,
      };
    }
    if (starred) productIds.add(productId);
    else productIds.delete(productId);
    const sortedIds = [...productIds].sort((a, b) => a.localeCompare(b, "en", {numeric: true}));
    const content = JSON.stringify({product_ids: sortedIds}, null, 2) + "\n";
    const response = await fetch(fileEndpoint(env), {
      method: "PUT",
      headers: githubHeaders(env, true),
      body: JSON.stringify({
        message: `chore: ${starred ? "star" : "unstar"} Bilibili product ${productId}`,
        content: encodeBase64Utf8(content),
        sha: current.sha,
        branch: env.MONITOR_BRANCH || "main",
      }),
    });
    if (response.ok) return {productIds: sortedIds, changed: true};
    if (response.status !== 409 && response.status !== 422) {
      throw new Error(`GitHub write failed: ${response.status}`);
    }
  }
  throw new Error("Star list changed concurrently; retry the request");
}


async function triggerMonitor(env) {
  const [owner, repository] = (env.MONITOR_REPOSITORY || "DRAMINGLING/Bilibili_Goods_Price_Monitor")
    .split("/")
    .map(encodeURIComponent);
  if (!owner || !repository) throw new Error("MONITOR_REPOSITORY must be owner/repository");
  const branch = env.MONITOR_BRANCH || "main";
  const endpoint = `https://api.github.com/repos/${owner}/${repository}/actions/workflows/price-monitor.yml/dispatches`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: githubHeaders(env, true),
    body: JSON.stringify({ref: branch}),
  });
  if (!response.ok) throw new Error(`Workflow dispatch failed: ${response.status}`);
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const allowedOrigin = env.ALLOWED_ORIGIN || "https://dramingling.github.io";
    if (origin && origin !== allowedOrigin) {
      return jsonResponse({error: "origin_not_allowed"}, 403);
    }

    if (request.method === "OPTIONS") {
      return new Response(null, {status: 204, headers: corsHeaders(allowedOrigin)});
    }

    const url = new URL(request.url);
    if (url.pathname !== "/stars") {
      return jsonResponse({error: "not_found"}, 404, origin || allowedOrigin);
    }

    if (request.method === "GET") {
      try {
        const {productIds} = await readStars(env);
        return jsonResponse({product_ids: productIds}, 200, origin || allowedOrigin);
      } catch (error) {
        return jsonResponse({error: "star_list_unavailable"}, 502, origin || allowedOrigin);
      }
    }

    if (request.method !== "POST") {
      return jsonResponse({error: "method_not_allowed"}, 405, origin || allowedOrigin);
    }

    const authorization = request.headers.get("Authorization") || "";
    if (!env.STAR_API_KEY || authorization !== `Bearer ${env.STAR_API_KEY}`) {
      return jsonResponse({error: "unauthorized"}, 401, origin || allowedOrigin);
    }

    let payload;
    try {
      payload = await request.json();
    } catch {
      return jsonResponse({error: "invalid_json"}, 400, origin || allowedOrigin);
    }
    const productId = typeof payload?.product_id === "string" ? payload.product_id.trim() : "";
    if (!/^\d{1,20}$/.test(productId) || typeof payload?.starred !== "boolean") {
      return jsonResponse({error: "invalid_request"}, 400, origin || allowedOrigin);
    }

    try {
      const saved = await updateStars(env, productId, payload.starred);
      let monitorDispatched = null;
      if (saved.changed) {
        try {
          await triggerMonitor(env);
          monitorDispatched = true;
        } catch (dispatchError) {
          console.error("Star saved, but immediate monitor dispatch failed", dispatchError);
          monitorDispatched = false;
        }
      }
      return jsonResponse({
        product_ids: saved.productIds,
        monitor_dispatched: monitorDispatched,
      }, 200, origin || allowedOrigin);
    } catch (error) {
      return jsonResponse({error: "star_update_failed"}, 502, origin || allowedOrigin);
    }
  },
};
