const form = document.getElementById("convert-form");
const statusEl = document.getElementById("status");
const submitBtn = document.getElementById("submit-btn");

function setStatus(message, type) {
  statusEl.textContent = message;
  statusEl.className = "status" + (type ? " " + type : "");
}

function filenameFromDisposition(header, fallback) {
  const match = /filename="([^"]+)"/i.exec(header || "");
  const raw = match ? match[1] : fallback;
  const base = raw.split(/[\\/]/).pop() || fallback;
  return base.replace(/[^\w.\-]+/g, "_").slice(0, 120) || fallback;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitBtn.disabled = true;
  setStatus("Fetching route...", "loading");

  const url = document.getElementById("url").value.trim();
  const format = document.getElementById("format").value;

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
        if (data.error) message = data.error;
      } catch (_) {}
      setStatus(message, "error");
      return;
    }

    const blob = await response.blob();
    const filename = filenameFromDisposition(
      response.headers.get("Content-Disposition"),
      `route.${format}`
    );
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
    setStatus("Download started.");
  } catch (_) {
    setStatus("Network error. Please try again.", "error");
  } finally {
    submitBtn.disabled = false;
  }
});
