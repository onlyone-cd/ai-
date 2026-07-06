async function collectResumeText() {
  const chunks = new Set();
  const target = findScrollTarget();
  const maxScroll = Math.max(target.scrollHeight - target.clientHeight, 0);
  const step = Math.max(Math.floor(target.clientHeight * 0.75), 420);

  for (let top = 0; top <= maxScroll + step; top += step) {
    target.scrollTop = Math.min(top, maxScroll);
    window.scrollTo(0, Math.min(top, document.documentElement.scrollHeight));
    await new Promise((resolve) => setTimeout(resolve, 260));
    const text = (target.innerText || document.body.innerText || "").trim();
    if (text) chunks.add(text);
  }

  return {
    raw_text: [...chunks].join("\n\n"),
    chunk_count: chunks.size,
    text_length: [...chunks].join("").length,
    page_url: location.href,
    title: document.title
  };
}

async function collectBossCandidates() {
  const target = findScrollTarget();
  const seen = new Map();
  const maxScroll = Math.max(target.scrollHeight - target.clientHeight, 0);
  const step = Math.max(Math.floor(target.clientHeight * 0.8), 520);

  for (let top = 0; top <= maxScroll + step; top += step) {
    target.scrollTop = Math.min(top, maxScroll);
    window.scrollTo(0, Math.min(top, document.documentElement.scrollHeight));
    await new Promise((resolve) => setTimeout(resolve, 300));
    for (const text of collectCandidateBlocks()) {
      const key = text.replace(/\s+/g, " ").slice(0, 80);
      if (!seen.has(key)) seen.set(key, text);
    }
  }

  const items = [...seen.values()].slice(0, 80).map((text, index) => ({
    external_id: `boss-${Date.now()}-${index}`,
    name: guessName(text),
    title: guessTitle(text),
    summary: text.slice(0, 260),
    raw_text: text,
    page_url: location.href
  }));
  return { items, count: items.length, page_url: location.href, title: document.title };
}

async function collectBossJobs() {
  const target = findScrollTarget();
  const seen = new Map();
  const maxScroll = Math.max(target.scrollHeight - target.clientHeight, 0);
  const step = Math.max(Math.floor(target.clientHeight * 0.8), 520);

  for (let top = 0; top <= maxScroll + step; top += step) {
    target.scrollTop = Math.min(top, maxScroll);
    window.scrollTo(0, Math.min(top, document.documentElement.scrollHeight));
    await new Promise((resolve) => setTimeout(resolve, 300));
    for (const text of collectJobBlocks()) {
      const key = text.replace(/\s+/g, " ").slice(0, 100);
      if (!seen.has(key)) seen.set(key, text);
    }
  }

  const items = [...seen.values()].slice(0, 80).map((text, index) => ({
    external_id: `boss-job-${Date.now()}-${index}`,
    title: guessJobTitle(text),
    city: guessCity(text),
    summary: text.slice(0, 500),
    jd_text: text,
    page_url: location.href
  }));
  return { items, count: items.length, page_url: location.href, title: document.title };
}

function collectCandidateBlocks() {
  const selectors = [
    "[class*='geek']",
    "[class*='card']",
    "[class*='item']",
    "[class*='resume']",
    "li"
  ];
  const nodes = [...document.querySelectorAll(selectors.join(","))];
  const blocks = nodes
    .map((node) => (node.innerText || "").trim())
    .filter((text) => text.length >= 30 && text.length <= 4000)
    .filter((text) => /(简历|求职|经验|本科|专科|硕士|博士|年|岁|沟通|在职|离职|应届|电话|邮箱|@)/.test(text));
  if (blocks.length) return blocks;
  return (document.body.innerText || "")
    .split(/\n{2,}/)
    .map((text) => text.trim())
    .filter((text) => text.length >= 30);
}

function collectJobBlocks() {
  const selectors = [
    "[class*='job']",
    "[class*='position']",
    "[class*='card']",
    "[class*='item']",
    "li"
  ];
  return [...document.querySelectorAll(selectors.join(","))]
    .map((node) => (node.innerText || "").trim())
    .filter((text) => text.length >= 12 && text.length <= 3000)
    .filter((text) => /(招聘|岗位|职位|薪资|经验|学历|本科|大专|Java|前端|后端|产品|运营|会计|销售|工程师|经理|主管|分析师)/.test(text))
    .filter((text) => !/(招聘规范|账号权益|续费VIP|我的客服|推荐牛人|道具|工具箱)/.test(text));
}

function guessName(text) {
  const firstLine = text.split(/\n/).map((line) => line.trim()).find(Boolean) || "BOSS 候选人";
  return firstLine.replace(/[|｜].*$/, "").slice(0, 16) || "BOSS 候选人";
}

function guessTitle(text) {
  const line = text.split(/\n/).find((item) => /(开发|工程师|产品|运营|会计|财务|销售|设计|测试|人事|行政|经理|主管|分析师)/.test(item));
  return (line || "BOSS 候选人").trim().slice(0, 32);
}

function guessJobTitle(text) {
  const line = text.split(/\n/).map((item) => item.trim()).find((item) => /(开发|工程师|产品|运营|会计|财务|销售|设计|测试|人事|行政|经理|主管|分析师|客服)/.test(item));
  return (line || text.split(/\n/)[0] || "BOSS 岗位").replace(/[|｜].*$/, "").slice(0, 32);
}

function guessCity(text) {
  const match = text.match(/(北京|上海|广州|深圳|杭州|南京|苏州|成都|重庆|武汉|西安|郑州|长沙|合肥|厦门|青岛|天津|宁波|无锡|佛山|东莞)/);
  return match?.[1] || "";
}

function findScrollTarget() {
  const elements = [document.scrollingElement, document.documentElement, document.body, ...document.querySelectorAll("main, section, div")].filter(Boolean);
  return elements.reduce((best, el) => {
    const score = (el.scrollHeight - el.clientHeight) + ((el.innerText || "").length / 20);
    const bestScore = (best.scrollHeight - best.clientHeight) + ((best.innerText || "").length / 20);
    return score > bestScore ? el : best;
  }, document.scrollingElement || document.documentElement);
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "collect-resume") {
    collectResumeText().then(sendResponse).catch((error) => sendResponse({ error: error.message }));
    return true;
  }
  if (message?.type === "collect-boss-candidates") {
    collectBossCandidates().then(sendResponse).catch((error) => sendResponse({ error: error.message }));
    return true;
  }
  if (message?.type === "collect-boss-jobs") {
    collectBossJobs().then(sendResponse).catch((error) => sendResponse({ error: error.message }));
    return true;
  }
  return false;
});
