export function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;

  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js")
      .then((registration) => {
        registration.addEventListener("updatefound", () => {
          const installing = registration.installing;
          if (installing) {
            installing.addEventListener("statechange", () => {
              if (installing.state === "installed") {
                if (navigator.serviceWorker.controller) {
                  console.log("[SW] New version available");
                } else {
                  console.log("[SW] Content cached for offline use");
                }
              }
            });
          }
        });
      })
      .catch((err) => {
        console.error("[SW] Registration failed:", err);
      });
  });
}
