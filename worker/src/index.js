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
    "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
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
      return [...productIds].sort((a, b) => a.localeCompare(b, "en", {numeric: true}));
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
    if (response.ok) return sortedIds;
    if (response.status !== 409 && response.status !== 422) {
      throw new Error(`GitHub write failed: ${response.status}`);
    }
  }
  throw new Error("Star list changed concurrently; retry the request");
}




function configFileEndpoint(env) {
  const repositoryParts = (env.MONITOR_REPOSITORY || "DRAMINGLING/Bilibili_Goods_Price_Monitor").split("/");
  if (repositoryParts.length !== 2 || repositoryParts.some(part => !part)) {
    throw new Error("MONITOR_REPOSITORY must be owner/repository");
  }
  const [owner, repository] = repositoryParts.map(encodeURIComponent);
  const branch = encodeURIComponent(env.MONITOR_BRANCH || "main");
  return "https://api.github.com/repos/" + owner + "/" + repository +
    "/contents/config/products.yaml?ref=" + branch;
}

function isAuthorized(request, env) {
  const authorization = request.headers.get("Authorization") || "";
  return Boolean(env.STAR_API_KEY && authorization === "Bearer " + env.STAR_API_KEY);
}

function yamlScalar(raw) {
  const value = raw.trim();
  if (value.startsWith('"')) {
    try {
      return JSON.parse(value);
    } catch {
      throw new Error("Invalid quoted YAML value");
    }
  }
  if (value.startsWith("'") && value.endsWith("'")) {
    return value.slice(1, -1).replace(/''/g, "'");
  }
  return value.replace(/\s+#.*$/, "").trim();
}

function inspectProductsYaml(source) {
  const lines = source.replace(/^\uFEFF/, "").split(/\r?\n/);
  const sectionStart = lines.findIndex(line => /^products\s*:\s*(?:#.*)?$/.test(line));
  if (sectionStart < 0) throw new Error("Products section is missing");

  let sectionEnd = lines.length;
  for (let index = sectionStart + 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (line && !/^\s/.test(line) && !line.startsWith("#")) {
      sectionEnd = index;
      break;
    }
  }

  const starts = [];
  for (let index = sectionStart + 1; index < sectionEnd; index += 1) {
    if (/^  - name:\s*/.test(lines[index])) starts.push(index);
  }

  const blocks = starts.map((start, index) => {
    const end = index + 1 < starts.length ? starts[index + 1] : sectionEnd;
    const content = lines.slice(start, end);
    const nameMatch = content[0].match(/^  - name:\s*(.*)$/);
    const read = pattern => {
      for (const line of content) {
        const match = line.match(pattern);
        if (match) return yamlScalar(match[1]);
      }
      return null;
    };
    const name = nameMatch ? yamlScalar(nameMatch[1]) : "";
    const clusterId = read(/^ {4}cluster_id:\s*(.*)$/);
    const enabledValue = read(/^ {4}enabled:\s*(.*)$/);
    const conditionType = read(/^ {6}type:\s*(.*)$/) || "lte";
    const priceValue = read(/^ {6}price:\s*(.*)$/);
    const minValue = read(/^ {6}min:\s*(.*)$/);
    const maxValue = read(/^ {6}max:\s*(.*)$/);

    if (typeof name !== "string" || !name.trim() ||
        typeof clusterId !== "string" || !/^\d{1,20}$/.test(clusterId)) {
      throw new Error("A monitored product has an invalid name or cluster_id");
    }
    const enabled = enabledValue === null ? true : enabledValue === "true";
    if (enabledValue !== null && enabledValue !== "true" && enabledValue !== "false") {
      throw new Error("A monitored product has an invalid enabled value");
    }

    let condition;
    if (conditionType === "range") {
      const min = Number(minValue);
      const max = Number(maxValue);
      if (!Number.isFinite(min) || !Number.isFinite(max) || min < 0 || max < min) {
        throw new Error("A monitored product has an invalid price range");
      }
      condition = {type: conditionType, min, max};
    } else {
      const price = Number(priceValue);
      if (!["lte", "lt", "gte", "gt"].includes(conditionType) ||
          !Number.isFinite(price) || price < 0) {
        throw new Error("A monitored product has an invalid price condition");
      }
      condition = {type: conditionType, price};
    }

    return {
      start,
      end,
      product: {name: name.trim(), cluster_id: clusterId, enabled, condition},
    };
  });

  const ids = blocks.map(block => block.product.cluster_id);
  if (new Set(ids).size !== ids.length) throw new Error("Duplicate cluster_id in product config");
  return {lines, sectionEnd, blocks};
}

function normalizeManagedProduct(value) {
  const name = typeof value?.name === "string" ? value.name.trim() : "";
  const clusterId = typeof value?.cluster_id === "string" ? value.cluster_id.trim() : "";
  const condition = value?.condition;
  const type = typeof condition?.type === "string" ? condition.type : "lte";
  if (!name || name.length > 160 || /[\u0000-\u001f\u007f]/.test(name) ||
      !/^\d{1,20}$/.test(clusterId) || typeof value.enabled !== "boolean") {
    throw new Error("Invalid product name, cluster_id, or enabled value");
  }
  if (type === "range") {
    const min = condition.min;
    const max = condition.max;
    if (typeof min !== "number" || typeof max !== "number" ||
        !Number.isFinite(min) || !Number.isFinite(max) || min < 0 || max < min || max > 10000000) {
      throw new Error("Invalid product price range");
    }
    return {name, cluster_id: clusterId, enabled: value.enabled, condition: {type, min, max}};
  }
  const price = condition?.price;
  if (!["lte", "lt", "gte", "gt"].includes(type) ||
      typeof price !== "number" || !Number.isFinite(price) || price < 0 || price > 10000000) {
    throw new Error("Invalid product price condition");
  }
  return {name, cluster_id: clusterId, enabled: value.enabled, condition: {type, price}};
}

function conditionYamlLines(condition) {
  const lines = ["      type: " + JSON.stringify(condition.type)];
  if (condition.type === "range") {
    lines.push("      min: " + String(condition.min));
    lines.push("      max: " + String(condition.max));
  } else {
    lines.push("      price: " + String(condition.price));
  }
  return lines;
}

function updateProductBlock(content, product) {
  const block = [...content];
  block[0] = "  - name: " + JSON.stringify(product.name);

  let clusterIndex = block.findIndex(line => /^ {4}cluster_id:\s*/.test(line));
  if (clusterIndex < 0) throw new Error("Product cluster_id is missing");

  const enabledIndex = block.findIndex(line => /^ {4}enabled:\s*/.test(line));
  if (enabledIndex >= 0) {
    block[enabledIndex] = "    enabled: " + String(product.enabled);
  } else {
    block.splice(clusterIndex + 1, 0, "    enabled: " + String(product.enabled));
  }

  let conditionIndex = block.findIndex(line => /^ {4}condition:\s*(?:#.*)?$/.test(line));
  if (conditionIndex < 0) {
    clusterIndex = block.findIndex(line => /^ {4}cluster_id:\s*/.test(line));
    block.splice(clusterIndex + 1, 0, "    condition:", ...conditionYamlLines(product.condition));
    return block;
  }

  const conditionField = /^ {6}(?:type|price|min|max):\s*/;
  const firstField = block.findIndex((line, index) => index > conditionIndex && conditionField.test(line));
  const insertIndex = firstField >= 0 ? firstField : conditionIndex + 1;
  for (let index = block.length - 1; index > conditionIndex; index -= 1) {
    if (conditionField.test(block[index])) block.splice(index, 1);
  }
  block.splice(insertIndex, 0, ...conditionYamlLines(product.condition));
  return block;
}

function newProductBlock(product) {
  const url = "https://mall.bilibili.com/neul-next/resell/detail.html?clusterId=" +
    encodeURIComponent(product.cluster_id) + "&noTitleBar=1";
  return [
    "  - name: " + JSON.stringify(product.name),
    "    enabled: " + String(product.enabled),
    "    url: " + JSON.stringify(url),
    "    cluster_id: " + JSON.stringify(product.cluster_id),
    "    condition:",
    ...conditionYamlLines(product.condition),
    '    price_type: "displayed"',
    "    cooldown_hours: 1",
  ];
}

function applyManagedProducts(source, products) {
  const inspected = inspectProductsYaml(source);
  const updates = new Map(products.map(product => [product.cluster_id, product]));
  const existingIds = new Set(inspected.blocks.map(block => block.product.cluster_id));
  const lines = [...inspected.lines];

  for (let index = inspected.blocks.length - 1; index >= 0; index -= 1) {
    const block = inspected.blocks[index];
    const product = updates.get(block.product.cluster_id);
    if (!product) continue;
    const replacement = updateProductBlock(lines.slice(block.start, block.end), product);
    lines.splice(block.start, block.end - block.start, ...replacement);
  }

  const newProducts = products.filter(product => !existingIds.has(product.cluster_id));
  if (newProducts.length) {
    const refreshed = inspectProductsYaml(lines.join("\n"));
    const addition = [];
    for (const product of newProducts) addition.push("", ...newProductBlock(product));
    lines.splice(refreshed.sectionEnd, 0, ...addition);
  }

  return lines.join("\n");
}

async function readProductsConfig(env) {
  const response = await fetch(configFileEndpoint(env), {headers: githubHeaders(env)});
  if (!response.ok) throw new Error("GitHub config read failed: " + response.status);
  const file = await response.json();
  const source = decodeBase64Utf8(file.content);
  const inspected = inspectProductsYaml(source);
  return {sha: file.sha, source, products: inspected.blocks.map(block => block.product)};
}

async function updateProductsConfig(env, products) {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const current = await readProductsConfig(env);
    const source = applyManagedProducts(current.source, products);
    if (source === current.source) return current.products;

    const response = await fetch(configFileEndpoint(env), {
      method: "PUT",
      headers: githubHeaders(env, true),
      body: JSON.stringify({
        message: "chore: update Bilibili monitor config from dashboard",
        content: encodeBase64Utf8(source),
        sha: current.sha,
        branch: env.MONITOR_BRANCH || "main",
      }),
    });
    if (response.ok) {
      return inspectProductsYaml(source).blocks.map(block => block.product);
    }
    if (response.status !== 409 && response.status !== 422) {
      throw new Error("GitHub config write failed: " + response.status);
    }
  }
  throw new Error("Monitor config changed concurrently; retry the request");
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
    if (url.pathname === "/config") {
      if (!isAuthorized(request, env)) {
        return jsonResponse({error: "unauthorized"}, 401, origin || allowedOrigin);
      }
      if (request.method === "GET") {
        try {
          const products = await readProductsConfig(env);
          return jsonResponse({products: products.products}, 200, origin || allowedOrigin);
        } catch (error) {
          console.error("GET /config failed:", error instanceof Error ? error.message : String(error));
          return jsonResponse({error: "monitor_config_unavailable"}, 502, origin || allowedOrigin);
        }
      }
      if (request.method !== "PUT") {
        return jsonResponse({error: "method_not_allowed"}, 405, origin || allowedOrigin);
      }

      let payload;
      try {
        const body = await request.text();
        if (body.length > 65536) return jsonResponse({error: "payload_too_large"}, 413, origin || allowedOrigin);
        payload = JSON.parse(body);
      } catch {
        return jsonResponse({error: "invalid_json"}, 400, origin || allowedOrigin);
      }
      if (!Array.isArray(payload?.products) || payload.products.length > 200) {
        return jsonResponse({error: "invalid_request"}, 400, origin || allowedOrigin);
      }

      let products;
      try {
        products = payload.products.map(normalizeManagedProduct);
        if (new Set(products.map(product => product.cluster_id)).size !== products.length) {
          return jsonResponse({error: "duplicate_cluster_id"}, 400, origin || allowedOrigin);
        }
      } catch (error) {
        return jsonResponse({error: "invalid_product", detail: error.message}, 400, origin || allowedOrigin);
      }

      try {
        const savedProducts = await updateProductsConfig(env, products);
        return jsonResponse({products: savedProducts}, 200, origin || allowedOrigin);
      } catch (error) {
        console.error("PUT /config failed:", error instanceof Error ? error.message : String(error));
        return jsonResponse({error: "monitor_config_update_failed"}, 502, origin || allowedOrigin);
      }
    }

    if (url.pathname !== "/stars") {
      return jsonResponse({error: "not_found"}, 404, origin || allowedOrigin);
    }

    if (request.method === "GET") {
      try {
        const {productIds} = await readStars(env);
        return jsonResponse({product_ids: productIds}, 200, origin || allowedOrigin);
      } catch (error) {
        // Keep read failure details in Worker logs without exposing secrets.
        console.error("GET /stars GitHub read failed:", error instanceof Error ? error.message : String(error));
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
      const productIds = await updateStars(env, productId, payload.starred);
      return jsonResponse({product_ids: productIds}, 200, origin || allowedOrigin);
    } catch (error) {
      return jsonResponse({error: "star_update_failed"}, 502, origin || allowedOrigin);
    }
  },
};
