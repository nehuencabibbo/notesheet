const NATIVE_HOST = "com.notesheet.capture";
const ALLOWED_HOSTS = new Set(["learn.cantrill.io", "player.hotmart.com"]);

function isAllowedPageUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && ALLOWED_HOSTS.has(url.hostname);
  } catch {
    return false;
  }
}

function isAllowedContentScript(sender) {
  return Boolean(
    sender.tab?.id !== undefined &&
    [sender.url, sender.origin, sender.tab.url].some(isAllowedPageUrl)
  );
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "get-shortcut" && message?.type !== "capture-course") {
    return false;
  }
  if (!isAllowedContentScript(sender)) {
    sendResponse({ ok: false, error: "Request is not from an allowed course or player page." });
    return false;
  }

  const action = message.type === "get-shortcut" ? "get-shortcut" : "capture";
  chrome.runtime.sendNativeMessage(NATIVE_HOST, { action })
    .then(response => sendResponse(response || { ok: false, error: "Notesheet returned no response." }))
    .catch(error => sendResponse({ ok: false, error: error.message }));
  return true;
});
