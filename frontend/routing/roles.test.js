import test from "node:test";
import assert from "node:assert/strict";
import { getRoleHome, isValidSession, roleHome } from "./roles.js";

test("all supported roles have a stable home route", () => {
  assert.deepEqual(roleHome, {
    student: "/student",
    teacher: "/teacher",
    coordinator: "/coordinator",
    admin: "/admin",
  });
  for (const role of Object.keys(roleHome)) assert.equal(getRoleHome(role), roleHome[role]);
});

test("persisted sessions require a known role and identity strings", () => {
  for (const role of Object.keys(roleHome)) {
    assert.equal(isValidSession({ role, email: `${role}@example.com`, name: "Example User" }), true);
  }
  assert.equal(isValidSession({ role: "unknown", email: "x@example.com", name: "X" }), false);
  // Role authority comes from the active Supabase profile, not a client-side
  // email-to-role allowlist. The session shape helper only validates shape.
  assert.equal(isValidSession({ role: "admin", email: "student@example.com", name: "Aarav Sharma" }), true);
  assert.equal(isValidSession({ role: "student", email: 42, name: "X" }), false);
  assert.equal(isValidSession(null), false);
  assert.equal(getRoleHome("unknown"), null);
});
