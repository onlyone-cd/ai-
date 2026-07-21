(() => {
  if (window.__hireinsightBossNetworkProbeInstalled) return;
  window.__hireinsightBossNetworkProbeInstalled = true;

  const MAX_CAPTURE_TEXT = 350000;
  const FILE_URL_MARKERS = ["resume", "attachment", "annex", "file", "download", "pdf", "doc", "简历", "附件"];
  const MARKERS = [
    "resume",
    "geek",
    "candidate",
    "friend",
    "expect",
    "experience",
    "education",
    "job",
    "position",
    "简历",
    "候选人",
    "工作经历",
    "项目经历",
    "教育经历",
    "个人优势",
    "求职期望",
    "期望职位",
    "职位",
    "岗位",
    "招聘"
  ];

  function isBossUrl(input) {
    try {
      const url = new URL(String(input || ""), location.href);
      return url.hostname === "zhipin.com" || url.hostname.endsWith(".zhipin.com");
    } catch (_error) {
      return false;
    }
  }

  function shouldCapture(url, text) {
    if (!isBossUrl(url) || !text || text.length < 40) return false;
    const head = `${url}\n${text.slice(0, 12000)}`;
    return MARKERS.some((marker) => head.includes(marker));
  }

  function emitCapture(payload) {
    const body = String(payload.body || "");
    if (!shouldCapture(payload.url, body)) return;
    window.postMessage({
      type: "hireinsight-boss-api",
      url: payload.url,
      method: payload.method || "GET",
      status: payload.status || 0,
      body: body.slice(0, MAX_CAPTURE_TEXT),
      capturedAt: Date.now()
    }, "*");
  }

  function emitFileUrl(url, contentType) {
    if (!isBossUrl(url)) return;
    const value = String(url || "").toLowerCase();
    if (!FILE_URL_MARKERS.some((marker) => value.includes(marker))) return;
    window.postMessage({
      type: "hireinsight-boss-file",
      url,
      contentType: contentType || "",
      capturedAt: Date.now()
    }, "*");
  }

  const nativeFetch = window.fetch;
  if (typeof nativeFetch === "function") {
    window.fetch = async function hireinsightFetch(input, init) {
      const url = typeof input === "string" ? input : input?.url;
      const method = init?.method || input?.method || "GET";
      const response = await nativeFetch.apply(this, arguments);
      if (isBossUrl(url)) {
        try {
          const clone = response.clone();
          const contentType = clone.headers?.get?.("content-type") || "";
          if (/pdf|msword|officedocument|octet-stream/i.test(contentType) || /\.(pdf|docx?|txt)(\?|$)/i.test(String(url || ""))) {
            emitFileUrl(url, contentType);
          }
          if (/json|text|javascript|html/i.test(contentType) || !contentType) {
            clone.text().then((body) => emitCapture({ url, method, status: response.status, body })).catch(() => {});
          }
        } catch (_error) {}
      }
      return response;
    };
  }

  const NativeXhr = window.XMLHttpRequest;
  if (typeof NativeXhr === "function") {
    const nativeOpen = NativeXhr.prototype.open;
    const nativeSend = NativeXhr.prototype.send;
    NativeXhr.prototype.open = function hireinsightOpen(method, url) {
      this.__hireinsightBossUrl = url;
      this.__hireinsightBossMethod = method || "GET";
      return nativeOpen.apply(this, arguments);
    };
    NativeXhr.prototype.send = function hireinsightSend() {
      this.addEventListener("load", () => {
        try {
          const url = this.responseURL || this.__hireinsightBossUrl;
          if (!isBossUrl(url)) return;
          const contentType = this.getResponseHeader?.("content-type") || "";
          if (/pdf|msword|officedocument|octet-stream/i.test(contentType) || /\.(pdf|docx?|txt)(\?|$)/i.test(String(url || ""))) {
            emitFileUrl(url, contentType);
          }
          if (!/json|text|javascript|html/i.test(contentType) && contentType) return;
          if (typeof this.responseText === "string") {
            emitCapture({ url, method: this.__hireinsightBossMethod, status: this.status, body: this.responseText });
          }
        } catch (_error) {}
      });
      return nativeSend.apply(this, arguments);
    };
  }
})();
