import { useState } from "react";
import { Link } from "react-router-dom";
import type { TokenResponse } from "@/lib/api";
import { setToken } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface AuthFormProps {
  title: string;
  submitLabel: string;
  footerText: string;
  footerLink: string;
  footerHref: string;
  errorFallback: string;
  onSubmit: (username: string, password: string) => Promise<TokenResponse>;
  onSuccess: () => void;
}

export default function AuthForm({
  title,
  submitLabel,
  footerText,
  footerLink,
  footerHref,
  errorFallback,
  onSubmit,
  onSuccess,
}: AuthFormProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const { token } = await onSubmit(username, password);
      setToken(token);
      onSuccess();
    } catch (err: any) {
      setError(err.message || errorFallback);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4 p-6">
        <h1 className="text-2xl font-bold text-center">{title}</h1>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Input placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        <Input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <Button type="submit" className="w-full">
          {submitLabel}
        </Button>
        <p className="text-center text-sm text-muted-foreground">
          {footerText}{" "}
          <Link to={footerHref} className="text-primary underline">
            {footerLink}
          </Link>
        </p>
      </form>
    </div>
  );
}
