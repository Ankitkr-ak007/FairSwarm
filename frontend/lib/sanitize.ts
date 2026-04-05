import DOMPurify from "dompurify";

export function sanitizeText(value: unknown): string {
  const input = String(value ?? "");

  if (typeof window === "undefined") {
    return input.replace(/<[^>]*>/g, "").trim();
  }

  return DOMPurify.sanitize(input, {
    ALLOWED_TAGS: [],
    ALLOWED_ATTR: [],
  }).trim();
}
