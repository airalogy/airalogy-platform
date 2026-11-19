import { documentRequest } from "./research-documents"

export interface ProjectPerson {
  id: string
  project_id: string
  name: string
  organization: string
  user_id: string | null
  revision: number
  display_name?: string
  assigned_count?: number
}
export function listProjectPeople(projectId: string) {
  return documentRequest<{ people: ProjectPerson[], can_manage_accounts: boolean, can_write: boolean }>({ url: "/project-people", params: { project_id: projectId } })
}
export function createProjectPerson(projectId: string, id: string, name: string, organization: string) {
  return documentRequest<ProjectPerson>({ url: "/project-people", method: "POST", data: { project_id: projectId, id, name, organization } })
}
export function associateProjectPerson(person: ProjectPerson, userId: string | null) {
  return documentRequest<ProjectPerson>({ url: `/project-people/${person.id}`, method: "PUT", data: { name: person.name, organization: person.organization, user_id: userId, expected_revision: person.revision } })
}

export interface ProjectTeam {
  additional_members: { id: string, name: string, username: string, display_name?: string }[]
  participants: Pick<ProjectPerson, "id" | "name" | "organization">[]
}

export function getProjectTeam(projectId: string) {
  return documentRequest<ProjectTeam>({ url: "/project-people/team", params: { project_id: projectId } })
}
