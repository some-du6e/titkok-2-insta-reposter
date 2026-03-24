console.log("TT2IG content script loaded!")

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("i got this btw " + message)
  console.log(sender)
  // get tiktok url
    let tiktokurl = window.location.href
    if (tiktokurl.toString()=="https://www.tiktok.com/") {
        alert("buddy please open the comments for it to work")
        return
    }
  sendResponse(tiktokurl)
  alert("sentt!!!!!")
  return true  // Required for async sendResponse in Manifest V3
})
