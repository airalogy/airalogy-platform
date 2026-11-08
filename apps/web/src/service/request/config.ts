// Keep request configuration independent of stores and request interceptors.
// Both regular and streaming clients are loaded by the application shell.
// @ts-expect-error - env.config is built separately in tsconfig.node.json
import { createProxyPattern, createServiceConfig } from "../../../env.config"

const { baseURL: rawBaseURL } = createServiceConfig(import.meta.env as Env.ImportMeta)
export const baseURL = import.meta.env.VITE_HTTP_PROXY === "Y" ? createProxyPattern() : rawBaseURL
