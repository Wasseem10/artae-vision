export const LOGIN_RETURN_KEY = "artae_login_return";

// Never accept arbitrary redirect URLs from a query string or browser storage.
export function loginDestination(search: string): "/demo" | "/app" {
  return new URLSearchParams(search).get("next") === "demo" ? "/demo" : "/app";
}
