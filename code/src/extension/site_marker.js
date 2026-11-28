// Runs only on https://memorylane.site/* so the website can tell the extension
// is installed (it hides "Get the extension") and which id to message.
// Sets two attributes; reads nothing.
document.documentElement.dataset.memorylaneExtension = "installed";
// The website messages the extension by id for pages kept on this device.
document.documentElement.dataset.memorylaneExtensionId = chrome.runtime.id;
