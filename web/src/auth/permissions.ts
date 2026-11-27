/**
 * What each role may do. The roles themselves (and their labels) are rows in
 * the `roles` table; what they allow lives here, in code, so a change is
 * reviewed and tested. A role this table doesn't know gets no permissions.
 *
 * Ported unchanged from auth.py ROLE_PERMISSIONS (21 Nov).
 */
export const PERMISSIONS = [
  "generate",
  "paste_input",
  "edit_roster",
  "view_groups",
  "view_hk_tab",
  "view_insp_tab",
  "manage_users",
  "view_dashboard",
  "delete_data",
  "view_frontdesk",
] as const;

export type Permission = (typeof PERMISSIONS)[number];

const FLOOR: readonly Permission[] = ["view_groups", "view_hk_tab"];

const ROLE_PERMISSIONS: Readonly<Record<string, ReadonlySet<Permission>>> = {
  admin: new Set(PERMISSIONS),
  rqs: new Set<Permission>([
    "generate",
    "paste_input",
    "view_groups",
    "view_hk_tab",
    "view_insp_tab",
    "view_dashboard",
  ]),
  housekeeper: new Set(FLOOR),
  houseperson: new Set(FLOOR),
  frontdesk: new Set<Permission>(["view_frontdesk"]),
};

export function can(role: string, permission: Permission): boolean {
  return ROLE_PERMISSIONS[role]?.has(permission) ?? false;
}

export function permissionsOf(role: string): Permission[] {
  return PERMISSIONS.filter((p) => can(role, p));
}
