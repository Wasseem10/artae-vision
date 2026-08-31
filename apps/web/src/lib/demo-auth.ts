export const LOCAL_DEMO_EMAIL = "demo@artae.ai";
export const LOCAL_DEMO_PASSWORD = "demo1234";

export function isLocalDemoHost(hostname: string): boolean {
  return hostname === "127.0.0.1" || hostname === "localhost";
}

export function isLocalDemoLogin(email: string, password: string, hostname: string): boolean {
  return (
    isLocalDemoHost(hostname) &&
    email.trim().toLowerCase() === LOCAL_DEMO_EMAIL &&
    password === LOCAL_DEMO_PASSWORD
  );
}
