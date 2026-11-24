import { request } from "../request"

export type Audience = "organization" | "public"
export interface ShareLink { id: string, path: string, audience: Audience, materials: string[] }
export interface Publication extends ShareLink {
  title: string
  body: string
  version: string | null
  protocols: { title: string, version: string, path: string }[]
}
export interface ShareOptions {
  title: string
  body: string
  version: string | null
  versions: string[]
  preview: string
  public_enabled: boolean
  links: ShareLink[]
}

export const sharing = {
  policy: (org: string, enabled?: boolean) => request<{ enabled: boolean }>({
    url: `/sharing/policy/${org}`,
    method: enabled === undefined ? "GET" : "PUT",
    data: enabled === undefined ? undefined : { enabled },
  }),
  reading: (project: string, enabled: boolean) => request<{ enabled: boolean }>({
    url: `/sharing/project/${project}/organization-reading`,
    method: "PUT",
    data: { enabled },
  }),
  options: (project: string, protocol_id?: string, version?: string) => request<ShareOptions>({
    url: `/sharing/manage/${project}`,
    params: { protocol_id, version },
  }),
  materials: (project: string, protocol_id: string, version: string) => request<string[]>({
    url: `/sharing/manage/${project}/materials`,
    params: { protocol_id, version },
  }),
  publish: (project: string, data: { audience: Audience, preview: string, materials: string[] }, protocol_id?: string, version?: string) => request<ShareLink>({
    url: `/sharing/manage/${project}`,
    method: "POST",
    params: { protocol_id, version },
    data,
  }),
  withdraw: (project: string, link: string, protocol_id?: string, version?: string) => request({
    url: `/sharing/manage/${project}/${link}`,
    method: "DELETE",
    params: { protocol_id, version },
  }),
  read: (id: string, signal: AbortSignal) => request<Publication>({
    url: `/sharing/read/${id}`,
    signal,
    metadata: { showError: false },
  }),
  file: (id: string, name: string) => request<Blob, "blob">({
    url: `/sharing/read/${id}/material`,
    params: { name },
    responseType: "blob",
  }),
}
