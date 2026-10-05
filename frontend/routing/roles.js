export const roleHome = Object.freeze({
  student: "/student",
  teacher: "/teacher",
  coordinator: "/coordinator",
  admin: "/admin",
});

export const validRoles = new Set(Object.keys(roleHome));
export function isValidSession(session) {
  return Boolean(
    session
    && typeof session === "object"
    && validRoles.has(session.role)
    && typeof session.email === "string"
    && typeof session.name === "string"
  );
}

export function getRoleHome(role) {
  return roleHome[role] || null;
}
