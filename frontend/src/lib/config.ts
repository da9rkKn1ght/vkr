export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";
export const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000/api/v1/ws";

export function backendOrigin(): string {
  try {
    const url = new URL(API_BASE_URL);
    return `${url.protocol}//${url.host}`;
  } catch {
    return "http://localhost:8000";
  }
}

export function resolveImageUrl(imagePath: string): string {
  if (!imagePath) {
    return "";
  }
  if (imagePath.startsWith("http://") || imagePath.startsWith("https://")) {
    return imagePath;
  }
  return `${backendOrigin()}${imagePath.startsWith("/") ? imagePath : `/${imagePath}`}`;
}

