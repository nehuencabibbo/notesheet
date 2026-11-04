const CAPTURE_COMMAND = "capture-hotmart-with-notesheet";
const NATIVE_HOST = "com.notesheet.capture";
const HIDE_STYLE_ID = "notesheet-hide-hotmart-controls";

async function setHotmartControlsHidden(tabId, hidden) {
  const results = await chrome.scripting.executeScript({
    target: { tabId, allFrames: true },
    args: [hidden, HIDE_STYLE_ID],
    func: async (shouldHide, styleId) => {
      const player = document.querySelector('[data-vjs-player="true"]');
      let style = document.getElementById(styleId);

      if (shouldHide) {
        const overlay = player?.querySelector('[data-testid="active-overlay"]');
        if (!overlay) return false;

        if (!style) {
          style = document.createElement("style");
          style.id = styleId;
          style.textContent = `
            [data-vjs-player="true"] [data-testid="active-overlay"] {
              display: none !important;
            }
          `;
          (document.head || document.documentElement).appendChild(style);
        }

        await new Promise(resolve =>
          requestAnimationFrame(() => requestAnimationFrame(resolve))
        );
        return true;
      }

      style?.remove();
      return Boolean(player);
    }
  });

  return results.some(frame => frame.result === true);
}

async function captureHotmartTab() {
  const [tab] = await chrome.tabs.query({
    active: true,
    lastFocusedWindow: true
  });
  if (!tab?.id) return;

  let overlayHidden = false;
  try {
    overlayHidden = await setHotmartControlsHidden(tab.id, true);
    if (!overlayHidden) {
      console.warn("Notesheet capture skipped: Hotmart player overlay not found.");
      return;
    }

    const response = await chrome.runtime.sendNativeMessage(NATIVE_HOST, {
      action: "capture"
    });
    if (!response?.ok) {
      throw new Error(response?.error || "Notesheet capture failed.");
    }
  } catch (error) {
    console.error("Notesheet Hotmart capture failed:", error);
  } finally {
    if (overlayHidden) {
      try {
        await setHotmartControlsHidden(tab.id, false);
      } catch (error) {
        console.error("Could not restore Hotmart video controls:", error);
      }
    }
  }
}

chrome.commands.onCommand.addListener(command => {
  if (command === CAPTURE_COMMAND) {
    void captureHotmartTab();
  }
});
