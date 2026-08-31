import type { Metadata } from "next";

import { LoginPage } from "@/components/login-page";

export const metadata: Metadata = {
  title: "Log in · Artae Vision",
  description: "Log in to your Artae Vision monitoring workspace.",
};

export default function Login() {
  return <LoginPage />;
}
