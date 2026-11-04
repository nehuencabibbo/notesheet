const NATIVE_HOST = "com.notesheet.capture";

function isHotmartUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" &&
      (url.hostname === "hotmart.com" || url.hostname.endsWith(".hotmart.com"));
  } catch {
    return false;
  }
}

function isHotmartContentScript(sender) {
  return Boolean(sender.tab?.id !== undefined && isHotmartUrl(sender.url));
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "get-shortcut" && message?.type !== "capture-hotmart") {
    return false;
  }
  if (!isHotmartContentScript(sender)) {
    sendResponse({ ok: false, error: "Request is not from a Hotmart page." });
    return false;
  }

  const action = message.type === "get-shortcut" ? "get-shortcut" : "capture";
  chrome.runtime.sendNativeMessage(NATIVE_HOST, { action })
    .then(response => sendResponse(response || { ok: false, error: "Notesheet returned no response." }))
    .catch(error => sendResponse({ ok: false, error: error.message }));
  return true;
});
