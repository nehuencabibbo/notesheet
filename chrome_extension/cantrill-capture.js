const HIDE_STYLE_ID = "notesheet-hide-course-controls";
const OVERLAY_SELECTOR = '[data-vjs-player="true"] [data-testid="active-overlay"]';
let configuredShortcut = null;
let captureInProgress = false;

const SPECIAL_KEYS = {
  ",": "Comma",
  ".": "Period",
  " ": "Space",
  ArrowUp: "Up",
  ArrowDown: "Down",
  ArrowLeft: "Left",
  ArrowRight: "Right",
  MediaNextTrack: "MediaNextTrack",
  MediaPrevTrack: "MediaPrevTrack",
  MediaTrackNext: "MediaNextTrack",
  MediaPlayPause: "MediaPlayPause",
  MediaTrackPrevious: "MediaPrevTrack",
  MediaStop: "MediaStop"
};

function keyForEvent(event) {
  if (/^Key[A-Z]$/.test(event.code)) return event.code.slice(3);
  if (/^Digit[0-9]$/.test(event.code)) return event.code.slice(5);

  const codeKeys = {
    Comma: "Comma",
    Period: "Period",
    Home: "Home",
    End: "End",
    PageUp: "PageUp",
    PageDown: "PageDown",
    Space: "Space",
    Insert: "Insert",
    Delete: "Delete",
    ArrowUp: "Up",
    ArrowDown: "Down",
    ArrowLeft: "Left",
    ArrowRight: "Right"
  };
  if (codeKeys[event.code]) return codeKeys[event.code];
  return SPECIAL_KEYS[event.key] || null;
}

function matchesShortcut(event, shortcut) {
  if (!shortcut || event.repeat || event.isComposing || event.metaKey) return false;

  const parts = shortcut.split("+");
  const key = parts.at(-1);
  if (keyForEvent(event) !== key) return false;

  return event.ctrlKey === parts.includes("Ctrl") &&
    event.altKey === parts.includes("Alt") &&
    event.shiftKey === parts.includes("Shift");
}

function hideOverlay() {
  if (!document.querySelector(OVERLAY_SELECTOR)) return null;

  let style = document.getElementById(HIDE_STYLE_ID);
  if (!style) {
    style = document.createElement("style");
    style.id = HIDE_STYLE_ID;
    style.textContent = `${OVERLAY_SELECTOR} { display: none !important; }`;
    (document.head || document.documentElement).appendChild(style);
  }
  return style;
}

function nextPaint() {
  return new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
}

async function captureWithOverlayHidden(event) {
  if (captureInProgress) return;
  const style = hideOverlay();
  if (!style) return;

  event.preventDefault();
  event.stopPropagation();
  event.stopImmediatePropagation();
  captureInProgress = true;

  try {
    await nextPaint();
    const response = await chrome.runtime.sendMessage({ type: "capture-course" });
    if (!response?.ok) {
      throw new Error(response?.error || "Notesheet capture failed.");
    }
  } catch (error) {
    console.error("Notesheet course capture failed:", error);
  } finally {
    style.remove();
    captureInProgress = false;
  }
}

chrome.runtime.sendMessage({ type: "get-shortcut" })
  .then(response => {
    if (response?.ok && typeof response.binding === "string") {
      configuredShortcut = response.binding;
    } else {
      console.error("Could not read the Notesheet Chrome shortcut:", response?.error);
    }
  })
  .catch(error => console.error("Could not connect to Notesheet:", error));

document.addEventListener("keydown", event => {
  if (!matchesShortcut(event, configuredShortcut)) return;
  if (captureInProgress) {
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    return;
  }
  void captureWithOverlayHidden(event);
}, true);
