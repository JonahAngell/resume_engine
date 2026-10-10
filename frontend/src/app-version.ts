export const RESUME_ENGINE_VERSION = "v0.1.36";

export const RESUME_ENGINE_BUILD =
  (import.meta.env.VITE_BUILD_SHA as string | undefined)?.trim() || "local";
