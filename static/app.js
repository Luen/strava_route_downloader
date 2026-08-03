const form = document.getElementById("convert-form");
const statusEl = document.getElementById("status");
const submitBtn = document.getElementById("submit-btn");

const ALLOWED_FORMATS = new Set(["gpx", "tcx"]);

function setStatus(message, type) {
  statusEl.textContent = message;
  statusEl.className = "status" + (type ? " " + type : "");
}

function safeDownloadName(format) {
  const extension = ALLOWED_FORMATS.has(format) ? format : "gpx";
  return `route.${extension}`;
}

function triggerBlobDownload(blob, filename) {
  const objectUrl = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    link.rel = "noopener";
    // Click without inserting into the document to avoid DOM XSS sinks.
    link.click();
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitBtn.disabled = true;
  setStatus("Fetching route...", "loading");

  const url = document.getElementById("url").value.trim();
  const format = document.getElementById("format").value;
  const downloadName = safeDownloadName(format);

  try {
    const response = await fetch("/api/convert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, format }),
    });

    if (!response.ok) {
      let message = "Could not convert route.";
      try {
        const data = await response.json();
        if (typeof data.error === "string") message = data.error;
      } catch (_) {}
      setStatus(message, "error");
      return;
    }

    const blob = await response.blob();
    triggerBlobDownload(blob, downloadName);
    setStatus("Download started.");
  } catch (_) {
    setStatus("Network error. Please try again.", "error");
  } finally {
    submitBtn.disabled = false;
  }
});
