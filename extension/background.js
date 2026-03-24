function sendToServer(url) {
  fetch("http://localhost:6767/api/get_tiktok_link", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: "url=" + encodeURIComponent(url),
  })
    .then((response) => response.text())
    .then((data) => {
      console.log("Server response:", data);
    })
    .catch((error) => {
      console.error("Error sending to server:", error);
    });
}



chrome.commands.onCommand.addListener((command) => {
  // get tiktok url
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0] && tabs[0].url && tabs[0].url.includes('tiktok.com')) {
      chrome.tabs.sendMessage(tabs[0].id, "url", (response) => {
        if (chrome.runtime.lastError) {
          console.log("Error: " + chrome.runtime.lastError.message);
        } else {
          console.log("we got this back: " + response);
          sendToServer(response);
        }
      });
    } else {
      console.log("Not on a TikTok page");
    }
  });
});

