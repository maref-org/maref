import { randomBytes } from "crypto";

const NONCE_KEY = "maref-csp-nonce";

export function generateNonce(): string {
  return randomBytes(16).toString("base64");
}

export function getNonce(): string {
  let nonce = sessionStorage.getItem(NONCE_KEY);
  if (!nonce) {
    nonce = generateNonce();
    sessionStorage.setItem(NONCE_KEY, nonce);
  }
  return nonce;
}

export function generateCspHeader(nonce: string): string {
  return [
    "default-src 'self'",
    "script-src 'self' 'nonce-" + nonce + "'",
    "style-src 'self' 'nonce-" + nonce + "'",
    "img-src 'self' data: asset:",
    "font-src 'self' data:",
    "connect-src 'self' http://localhost:5173 ws://localhost:5173 http://localhost:8000",
    "frame-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join("; ");
}

export function injectNonce(): void {
  const nonce = getNonce();

  // 注入 meta tag
  let meta = document.querySelector('meta[name="csp-nonce"]') as HTMLMetaElement | null;
  if (!meta) {
    meta = document.createElement("meta");
    meta.name = "csp-nonce";
    document.head.appendChild(meta);
  }
  meta.content = nonce;

  // 为所有内联 style 添加 nonce
  document.querySelectorAll("style:not([nonce])").forEach((el) => {
    el.setAttribute("nonce", nonce);
  });

  // 为所有内联 script 添加 nonce
  document.querySelectorAll("script:not([nonce])").forEach((el) => {
    el.setAttribute("nonce", nonce);
  });
}
