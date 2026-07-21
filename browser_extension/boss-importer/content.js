const RESUME_MARKERS = [
  "工作经历",
  "项目经历",
  "教育经历",
  "期望职位",
  "求职期望",
  "个人优势",
  "资格证书",
  "自我评价",
  "求职状态",
  "专业技能"
];

const JOB_LIST_MARKERS = [
  "职位管理",
  "岗位管理",
  "我的职位",
  "招聘职位",
  "职位列表",
  "岗位列表",
  "发布职位",
  "在招职位",
  "招聘中"
];

async function collectResumeText() {
  const resumeRoot = findResumeRoot();
  const target = findScrollTarget(resumeRoot);
  const bounds = findResumeColumnBounds(resumeRoot);
  const chunks = new Set();
  const originalTop = target.scrollTop || 0;
  const originalWindowTop = window.scrollY || 0;
  const maxScroll = Math.max(target.scrollHeight - target.clientHeight, 0);
  const step = Math.max(Math.floor((target.clientHeight || window.innerHeight) * 0.68), 360);

  try {
    for (let top = 0; top <= maxScroll + step; top += step) {
      scrollElement(target, Math.min(top, maxScroll));
      await sleep(240);
      const text = collectVisibleResumeLines(resumeRoot, bounds).join("\n");
      if (text) chunks.add(text);
    }
  } finally {
    scrollElement(target, originalTop);
    window.scrollTo(0, originalWindowTop);
  }

  const rawText = normalizeResumeText([...chunks].join("\n"));
  if (!hasResumeSignal(rawText)) {
    throw new Error("未识别到简历正文，请打开 BOSS 候选人简历详情页，并确保中间简历区域可见");
  }
  return {
    raw_text: rawText,
    chunk_count: chunks.size,
    text_length: rawText.length,
    page_url: location.href,
    title: document.title
  };
}

function findResumeRoot() {
  const selectors = [
    "[class*='resume']",
    "[class*='geek']",
    "[class*='detail']",
    "[class*='dialog']",
    "[class*='modal']",
    "main",
    "section",
    "article",
    "div"
  ];
  const nodes = [...document.querySelectorAll(selectors.join(","))];
  let best = null;
  let bestScore = -Infinity;

  for (const node of nodes) {
    if (!isVisibleElement(node)) continue;
    const rect = node.getBoundingClientRect();
    if (rect.width < 320 || rect.height < 180) continue;
    const text = (node.innerText || "").trim();
    if (text.length < 80) continue;
    const score = scoreResumeRoot(text, rect);
    if (score > bestScore) {
      best = node;
      bestScore = score;
    }
  }
  return best || document.body;
}

function scoreResumeRoot(text, rect) {
  const includeHits = countTextHits(text, RESUME_MARKERS);
  const noiseHits = countMatches(text, /(BOSS直聘|职位管理|推荐牛人|账号权益|续费VIP|我的客服|招聘规范|招聘数据|道具|工具管理|意向沟通|互动|收藏|转发|举报|不合适|发消息|继续沟通)/g);
  const dateHits = countMatches(text, /\d{4}[./-]\d{1,2}\s*[-至]\s*(\d{4}[./-]\d{1,2}|至今|今)/g);
  const contactHits = countMatches(text, /(1[3-9]\d{9}|[\w.+-]+@[\w.-]+)/g);
  const geometryPenalty = rect.left < 100 || rect.width > Math.min(window.innerWidth * 0.84, 1080) ? 8 : 0;
  return includeHits * 10 + dateHits * 5 + contactHits * 4 + Math.min(text.length / 240, 10) - noiseHits * 6 - geometryPenalty;
}

function findResumeColumnBounds(root) {
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1200;
  let fallbackLeft = Math.max(170, viewportWidth * 0.13);
  let fallbackRight = Math.min(viewportWidth - 210, viewportWidth * 0.78);
  const rightActionLeft = findPanelBoundary(/(继续沟通|发消息|不合适|交换微信|收藏|转发|举报|打招呼|立即沟通)/);
  if (rightActionLeft) fallbackRight = Math.min(fallbackRight, rightActionLeft - 16);

  const candidates = [...document.querySelectorAll("main,section,article,div")]
    .filter(isVisibleElement)
    .map((node) => ({ node, rect: node.getBoundingClientRect(), text: (node.innerText || "").trim() }))
    .filter((item) => item.text.length >= 120 && item.rect.width >= 360 && item.rect.height >= 160)
    .filter((item) => countTextHits(item.text, RESUME_MARKERS) >= 2)
    .filter((item) => item.rect.left >= 80 && item.rect.right <= viewportWidth - 80)
    .filter((item) => !/(职位管理|推荐牛人|账号权益|续费VIP|我的客服|招聘数据)/.test(item.text.slice(0, 500)));

  if (candidates.length) {
    candidates.sort((a, b) => scoreResumeRoot(b.text, b.rect) - scoreResumeRoot(a.text, a.rect));
    const rect = candidates[0].rect;
    return {
      left: Math.max(0, rect.left - 12),
      right: Math.min(viewportWidth, rect.right + 12),
      top: Math.max(0, rect.top - 20),
      bottom: Math.min(window.innerHeight || 900, rect.bottom + 20)
    };
  }

  const rootRect = root?.getBoundingClientRect?.();
  if (rootRect && rootRect.width >= 360 && rootRect.left >= 80 && rootRect.right <= viewportWidth - 80) {
    return {
      left: Math.max(0, rootRect.left - 12),
      right: Math.min(viewportWidth, rootRect.right + 12),
      top: 0,
      bottom: window.innerHeight || 900
    };
  }

  return { left: fallbackLeft, right: fallbackRight, top: 0, bottom: window.innerHeight || 900 };
}

function findPanelBoundary(pattern) {
  const rects = collectVisibleTextRects(document.body, (line) => pattern.test(line));
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1200;
  const rightRects = rects.filter((rect) => rect.left > viewportWidth * 0.58);
  if (!rightRects.length) return null;
  return Math.min(...rightRects.map((rect) => rect.left));
}

function collectVisibleResumeLines(root, bounds) {
  const lines = [];
  const seen = new Set();
  const walker = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const value = node.nodeValue.replace(/\s+/g, " ").trim();
      if (!value || value.length < 2) return NodeFilter.FILTER_REJECT;
      const parent = node.parentElement;
      if (!parent || !isVisibleElement(parent)) return NodeFilter.FILTER_REJECT;
      if (isInsideControl(parent)) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    }
  });

  while (walker.nextNode()) {
    const node = walker.currentNode;
    const rects = getTextNodeRects(node);
    if (!rects.some((rect) => isRectInBounds(rect, bounds))) continue;
    for (const line of splitCleanLines(node.nodeValue)) {
      if (isBossNavigationLine(line) || isActionOnlyLine(line)) continue;
      const key = line.replace(/\s+/g, "");
      if (seen.has(key)) continue;
      seen.add(key);
      lines.push(line);
    }
  }
  return lines;
}

function collectVisibleTextRects(root, predicate) {
  const rects = [];
  const walker = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    const text = node.nodeValue.replace(/\s+/g, " ").trim();
    if (!text || !predicate(text)) continue;
    rects.push(...getTextNodeRects(node).filter(isVisibleRect));
  }
  return rects;
}

function getTextNodeRects(node) {
  try {
    const range = document.createRange();
    range.selectNodeContents(node);
    const rects = [...range.getClientRects()];
    range.detach();
    return rects;
  } catch (_error) {
    return [];
  }
}

function isRectInBounds(rect, bounds) {
  if (!isVisibleRect(rect)) return false;
  const centerX = rect.left + rect.width / 2;
  const centerY = rect.top + rect.height / 2;
  return centerX >= bounds.left && centerX <= bounds.right && centerY >= bounds.top - 40 && centerY <= bounds.bottom + 40;
}

function splitCleanLines(text) {
  return String(text || "")
    .replace(/\r/g, "\n")
    .split(/\n| {2,}|\t+/)
    .map((line) => line.replace(/\s+/g, " ").trim())
    .filter(Boolean);
}

function normalizeResumeText(text) {
  const seen = new Set();
  return splitCleanLines(text)
    .filter((line) => !isBossNavigationLine(line))
    .filter((line) => !isActionOnlyLine(line))
    .filter((line) => {
      const key = line.replace(/\s+/g, "");
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .join("\n");
}

function isBossNavigationLine(line) {
  const compact = line.replace(/\s+/g, "");
  if (/^(BOSS直聘|职位管理|推荐牛人|搜索|沟通|意向沟通|互动|牛人管理|道具|工具管理|更多|附件简历|不合适|发消息|收藏|转发|举报)$/.test(compact)) return true;
  if (/^(未处理|已处理|待沟通|已沟通|新招呼|看过我|对我感兴趣|我的客服|招聘数据|账号权益|续费VIP)/.test(compact)) return true;
  if (/(招聘规范|隐私保护|平台相关提交|在线浏览牛人简历|下载APP|扫码登录|开聊|换一批|筛选|排序|刷新)/.test(compact)) return true;
  if (/^继续沟通/.test(compact)) return true;
  return false;
}

function isActionOnlyLine(line) {
  const compact = line.replace(/\s+/g, "");
  return /^(查看联系方式|获取联系方式|立即沟通|继续沟通|打招呼|交换微信|约面试|发面试邀请|发送|开聊|收藏|转发|举报|不合适|备注|标记)$/.test(compact);
}

async function collectBossCandidates() {
  const target = findScrollTarget();
  const seen = new Map();
  const maxScroll = Math.max(target.scrollHeight - target.clientHeight, 0);
  const step = Math.max(Math.floor((target.clientHeight || window.innerHeight) * 0.8), 520);

  for (let top = 0; top <= maxScroll + step; top += step) {
    scrollElement(target, Math.min(top, maxScroll));
    await sleep(300);
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
  assertBossJobListPage();
  const target = findScrollTarget();
  const seen = new Map();
  const maxScroll = Math.max(target.scrollHeight - target.clientHeight, 0);
  const step = Math.max(Math.floor((target.clientHeight || window.innerHeight) * 0.8), 520);

  for (let top = 0; top <= maxScroll + step; top += step) {
    scrollElement(target, Math.min(top, maxScroll));
    await sleep(300);
    for (const text of collectJobBlocks()) {
      const key = normalizeJobKey(text);
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

function assertBossJobListPage() {
  const pageText = (document.body.innerText || "").slice(0, 6000);
  const pageSignal = `${location.href}\n${document.title}\n${pageText}`;
  const resumeSignals = countTextHits(pageSignal, ["工作经历", "教育经历", "期望职位", "求职期望", "个人优势", "项目经历"]);
  const jobSignals = countTextHits(pageSignal, JOB_LIST_MARKERS) + countMatches(pageSignal, /(招聘中|待开放|已关闭|职位名称|招聘人数|发布职位|刷新职位|编辑职位)/g);
  if (resumeSignals >= 3 && jobSignals < 2) {
    throw new Error("当前是候选人简历页。同步岗位请打开 BOSS 职位管理/岗位列表页，不能采集候选人的期望职位");
  }
  if (jobSignals < 2 && !/\/job|\/position|position|job/i.test(location.href)) {
    throw new Error("未识别到 BOSS 岗位列表。请先打开 BOSS 职位管理/岗位列表页后再同步岗位");
  }
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
    .map((node) => normalizeResumeText(node.innerText || ""))
    .filter((text) => text.length >= 30 && text.length <= 4000)
    .filter((text) => /(简历|求职|经验|本科|专科|硕士|博士|岁|离职|应届|电话|邮箱|@)/.test(text))
    .filter((text) => !looksLikeJobBlock(text));
  if (blocks.length) return blocks;
  return normalizeResumeText(document.body.innerText || "")
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
    .map((node) => normalizeJobText(node.innerText || ""))
    .filter((text) => text.length >= 12 && text.length <= 3000)
    .filter((text) => looksLikeJobBlock(text))
    .filter((text) => !looksLikeResumeDetailBlock(text))
    .filter((text) => !/(招聘规范|账号权益|续费VIP|我的客服|推荐牛人|道具|工具管理|期望职位|求职期望)/.test(text));
}

function normalizeJobText(text) {
  const seen = new Set();
  return splitCleanLines(text)
    .filter((line) => !isBossNavigationLine(line))
    .filter((line) => !/(期望职位|求职期望|个人优势|工作经历|教育经历|项目经历|资格证书)/.test(line))
    .filter((line) => {
      const key = line.replace(/\s+/g, "");
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .join("\n");
}

function looksLikeJobBlock(text) {
  const hasJobTitle = /(工程师|开发|前端|后端|Java|Python|测试|产品|运营|会计|财务|销售|客服|人事|行政|经理|主管|总监|架构师|分析师|专员)/.test(text);
  const hasJobFields = /(薪资|月薪|年薪|经验|学历|本科|大专|招聘|岗位|职位|职责|任职要求|职位描述|JD|k|K|元\/月)/.test(text);
  return hasJobTitle && hasJobFields;
}

function looksLikeResumeDetailBlock(text) {
  return countTextHits(text, ["工作经历", "教育经历", "期望职位", "求职期望", "个人优势", "项目经历", "资格证书", "离职", "随时到岗"]) >= 2;
}

function normalizeJobKey(text) {
  return text
    .replace(/\s+/g, " ")
    .replace(/\d{4}[./-]\d{1,2}.*$/g, "")
    .slice(0, 120);
}

function guessName(text) {
  const firstLine = text.split(/\n/).map((line) => line.trim()).find(Boolean) || "BOSS 候选人";
  return firstLine.replace(/[|·].*$/, "").slice(0, 16) || "BOSS 候选人";
}

function guessTitle(text) {
  const line = text.split(/\n/).find((item) => /(开发|工程师|产品|运营|会计|财务|销售|设计|测试|人事|行政|经理|主管|分析师)/.test(item));
  return (line || "BOSS 候选人").trim().slice(0, 32);
}

function guessJobTitle(text) {
  const line = text
    .split(/\n/)
    .map((item) => item.trim())
    .find((item) => /(开发|工程师|产品|运营|会计|财务|销售|设计|测试|人事|行政|经理|主管|总监|架构师|分析师|客服|专员)/.test(item) && !/(期望职位|求职期望)/.test(item));
  return (line || text.split(/\n/)[0] || "BOSS 岗位").replace(/[|·].*$/, "").slice(0, 32);
}

function guessCity(text) {
  const match = text.match(/(北京|上海|广州|深圳|杭州|南京|苏州|成都|重庆|武汉|西安|郑州|长沙|合肥|厦门|青岛|天津|宁波|无锡|佛山|东莞)/);
  return match?.[1] || "";
}

function hasResumeSignal(text) {
  return countTextHits(text, RESUME_MARKERS) >= 1 && !looksLikeOnlyNavigation(text);
}

function looksLikeOnlyNavigation(text) {
  const lines = splitCleanLines(text);
  if (!lines.length) return true;
  const noise = lines.filter((line) => isBossNavigationLine(line) || isActionOnlyLine(line)).length;
  return noise / lines.length > 0.45;
}

function countTextHits(text, words) {
  return words.reduce((count, word) => count + (String(text || "").includes(word) ? 1 : 0), 0);
}

function countMatches(text, pattern) {
  return ((text || "").match(pattern) || []).length;
}

function isVisibleElement(node) {
  const rect = node.getBoundingClientRect();
  const style = window.getComputedStyle(node);
  return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden" && style.opacity !== "0";
}

function isVisibleRect(rect) {
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 900;
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1200;
  return rect.width > 0 && rect.height > 0 && rect.bottom >= 0 && rect.top <= viewportHeight && rect.right >= 0 && rect.left <= viewportWidth;
}

function isInsideControl(node) {
  return Boolean(node.closest("button,input,textarea,select,nav,aside,[role='button'],[role='navigation']"));
}

function findScrollTarget(root = document.body) {
  const candidates = [root, document.scrollingElement, document.documentElement, document.body, ...document.querySelectorAll("main, section, div")]
    .filter(Boolean)
    .filter((el, index, list) => list.indexOf(el) === index)
    .filter((el) => el.scrollHeight - el.clientHeight > 80);
  if (!candidates.length) return document.scrollingElement || document.documentElement;
  return candidates.reduce((best, el) => {
    const text = el.innerText || "";
    const score = (el.scrollHeight - el.clientHeight) + countTextHits(text, RESUME_MARKERS) * 600 + Math.min(text.length / 20, 500);
    const bestText = best.innerText || "";
    const bestScore = (best.scrollHeight - best.clientHeight) + countTextHits(bestText, RESUME_MARKERS) * 600 + Math.min(bestText.length / 20, 500);
    return score > bestScore ? el : best;
  }, candidates[0]);
}

function scrollElement(target, top) {
  if (target === document.scrollingElement || target === document.documentElement || target === document.body) {
    window.scrollTo(0, top);
    return;
  }
  target.scrollTop = top;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
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
